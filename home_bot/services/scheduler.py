"""Background scheduler for recurring bot tasks."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from sqlalchemy import func

from ..config import settings
from ..db.models import TaskFrequency, TaskInstance, TaskStatus, TaskTemplate, User, Vote
from ..db.repo import (
    add_score_event,
    create_instance,
    family_users,
    pop_task_broadcasts,
    session_scope,
    votes_summary,
)
from ..domain.constants import CLAIM_REMINDER_MINUTES, VOTE_SECOND_WAIT_MINUTES
from ..services.notifications import announce_task, update_verification_messages
from ..services.scoring import calc_task_reward, missed_penalty, reward_for_completion
from ..utils.telegram import safe_send_message
from ..utils.text import escape_html
from ..utils.time import (
    in_quiet_hours,
    next_allowed_moment,
    now_tz,
    parse_quiet_hours,
)


_scheduler: AsyncIOScheduler | None = None
_lifecycle_controller: "BotScheduler | None" = None


def get_scheduler() -> AsyncIOScheduler:
    """Lazily create or return the shared AsyncIO scheduler instance."""

    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            timezone=ZoneInfo(settings.TZ),
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 120,
            },
        )
    return _scheduler


def start_scheduler() -> None:
    """Start the shared scheduler if it is not already running."""

    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()


def shutdown_scheduler() -> None:
    """Shutdown the shared scheduler without waiting for jobs."""

    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)


def set_lifecycle_controller(controller: "BotScheduler | None") -> None:
    """Remember the lifecycle controller for handlers access."""

    global _lifecycle_controller
    _lifecycle_controller = controller


def get_lifecycle_controller() -> "BotScheduler | None":
    """Return previously registered lifecycle controller if any."""

    return _lifecycle_controller


log = logging.getLogger(__name__)


COMMON_JOB_OPTIONS = {
    "coalesce": True,
    "misfire_grace_time": 120,
    "max_instances": 1,
    "replace_existing": True,
}


PENDING_QUEUE_JOB_ID = "announce_pending_queue"


class BotScheduler:
    """High level orchestrator for timed events."""

    MAX_ACTIVE_TASKS = 3

    def __init__(self, bot=None, scheduler: AsyncIOScheduler | None = None) -> None:
        self.bot = bot
        self.scheduler = scheduler or get_scheduler()
        self.quiet_hours = parse_quiet_hours(settings.QUIET_HOURS)

    def attach_bot(self, bot) -> None:
        self.bot = bot

    def start(self) -> None:
        if self.bot is None:  # pragma: no cover - configuration guard
            raise RuntimeError("Bot instance must be attached before starting the scheduler")
        start_scheduler()
        from .lifecycle import schedule_daily_jobs

        schedule_daily_jobs(self.bot)
        log.info("Scheduler started")

    def shutdown(self) -> None:
        shutdown_scheduler()

    def _job_id(self, kind: str, instance_id: int) -> str:
        return f"{kind}:{instance_id}"

    def _remove_job(self, job_id: str) -> None:
        try:
            self.scheduler.remove_job(job_id)
        except JobLookupError:
            return

    def cancel_open_jobs(self, instance_id: int) -> None:
        for prefix in ("claim_timeout", "reannounce", "announce"):
            self._remove_job(self._job_id(prefix, instance_id))

    def cancel_vote_deadline(self, instance_id: int) -> None:
        self._remove_job(self._job_id("vote", instance_id))

    def schedule_vote_deadline(self, instance_id: int) -> None:
        run_date = datetime.utcnow() + timedelta(minutes=VOTE_SECOND_WAIT_MINUTES)
        trigger = DateTrigger(run_date=run_date)
        self.scheduler.add_job(
            self.finalize_vote_job,
            trigger=trigger,
            args=[instance_id],
            id=self._job_id("vote", instance_id),
            **COMMON_JOB_OPTIONS,
        )
        log.info("Vote deadline scheduled for instance %s at %s", instance_id, run_date.isoformat())

    def _schedule_pending_after_quiet(self, now_local: datetime) -> None:
        run_at = next_allowed_moment(now_local, self.quiet_hours)
        trigger = DateTrigger(run_date=run_at)
        self.scheduler.add_job(
            self.announce_pending_tasks,
            trigger=trigger,
            id=PENDING_QUEUE_JOB_ID,
            **COMMON_JOB_OPTIONS,
        )
        log.info("Delayed pending announcements until %s", run_at.isoformat())

    async def announce_pending_tasks(self) -> None:
        if self.bot is None:
            return
        now_local = now_tz(settings.TZ)
        if in_quiet_hours(now_local, self.quiet_hours):
            self._schedule_pending_after_quiet(now_local)
            return
        self._remove_job(PENDING_QUEUE_JOB_ID)
        while True:
            with session_scope() as session:
                today = date.today()
                active_count = (
                    session.query(TaskInstance)
                    .filter(
                        TaskInstance.day <= today,
                        TaskInstance.status == TaskStatus.open,
                        TaskInstance.announced.is_(True),
                    )
                    .count()
                )
                if active_count >= self.MAX_ACTIVE_TASKS:
                    break
                next_instance = (
                    session.query(TaskInstance)
                    .filter(
                        TaskInstance.day <= today,
                        TaskInstance.status == TaskStatus.open,
                        TaskInstance.announced.is_(False),
                    )
                    .order_by(TaskInstance.day.asc(), TaskInstance.created_at.asc())
                    .first()
                )
                if not next_instance:
                    break
                instance_id = next_instance.id
                penalize = next_instance.announcement_penalize
                note = next_instance.announcement_note
                next_instance.announced = True
                next_instance.announcement_penalize = False
                next_instance.announcement_note = None
                session.flush()
            await asyncio.sleep(1)
            sent = await self._deliver_announcement(
                instance_id,
                penalize=penalize,
                note=note,
            )
            if not sent:
                with session_scope() as session:
                    instance = session.get(TaskInstance, instance_id)
                    if instance and instance.status == TaskStatus.open:
                        instance.announced = False
                        instance.announcement_penalize = penalize
                        instance.announcement_note = note
                break

    async def on_task_claimed(self, instance_id: int | None = None) -> None:
        await self.announce_pending_tasks()

    async def ensure_today_tasks(self, *, announce: bool = True) -> int:
        """Generate tasks for today if they are missing."""

        today = date.today()
        with session_scope() as session:
            exists = (
                session.query(TaskInstance)
                .filter(TaskInstance.day == today)
                .first()
            )
        if exists:
            log.debug("Tasks for %s already exist, skipping generation", today)
            if announce:
                await self.announce_pending_tasks()
            return 0
        created = await self.generate_tasks_for_day(today, announce=announce)
        log.info("Ensured tasks for %s (created=%s)", today, created)
        return created

    async def regenerate_today(self) -> int:
        """Drop today's tasks and regenerate them."""

        today = date.today()
        with session_scope() as session:
            removed = (
                session.query(TaskInstance)
                .filter(TaskInstance.day == today)
                .delete(synchronize_session=False)
            )
        created = await self.generate_tasks_for_day(today)
        log.info("Regenerated tasks for %s (removed=%s, created=%s)", today, removed, created)
        return created

    async def generate_today_tasks(self) -> int:
        return await self.generate_tasks_for_day(date.today())

    async def generate_tasks_for_day(self, day: date, *, announce: bool = True) -> int:
        new_instances: list[int] = []
        with session_scope() as session:
            templates = session.query(TaskTemplate).all()
            stats = self._collect_scoring_stats(session, [tpl.id for tpl in templates])
            for template in templates:
                if not self._should_generate(template, day):
                    continue
                already_exists = (
                    session.query(TaskInstance)
                    .filter(
                        TaskInstance.template_id == template.id,
                        TaskInstance.day == day,
                    )
                    .first()
                )
                if already_exists:
                    continue
                template._scoring_stats = stats.get(template.id, {})
                instance = create_instance(
                    session,
                    template,
                    day=day,
                    slot=1,
                    effective_points=calc_task_reward(template),
                )
                new_instances.append(instance.id)
                log.info(
                    "Generated instance %s for template %s (%s)",
                    instance.id,
                    template.code,
                    day,
                )
            for template in templates:
                if hasattr(template, "_scoring_stats"):
                    delattr(template, "_scoring_stats")
        if announce:
            for instance_id in new_instances:
                await self.announce_instance(instance_id, penalize=False)
        return len(new_instances)

    def _collect_scoring_stats(
        self, session, template_ids: list[int]
    ) -> dict[int, dict[str, object]]:
        if not template_ids:
            return {}
        stats: dict[int, dict[str, object]] = {tid: {} for tid in template_ids}
        recent_cutoff = datetime.utcnow() - timedelta(days=2)
        recent_rows = (
            session.query(TaskInstance.template_id, func.count())
            .filter(
                TaskInstance.template_id.in_(template_ids),
                TaskInstance.status == TaskStatus.approved,
                TaskInstance.created_at >= recent_cutoff,
            )
            .group_by(TaskInstance.template_id)
            .all()
        )
        for template_id, count in recent_rows:
            stats.setdefault(int(template_id), {})["recent_completions"] = int(count or 0)
        last_completed_rows = (
            session.query(TaskInstance.template_id, func.max(TaskInstance.created_at))
            .filter(
                TaskInstance.template_id.in_(template_ids),
                TaskInstance.status == TaskStatus.approved,
            )
            .group_by(TaskInstance.template_id)
            .all()
        )
        for template_id, ts in last_completed_rows:
            if ts:
                stats.setdefault(int(template_id), {})["last_completed"] = ts
        oldest_open_rows = (
            session.query(TaskInstance.template_id, func.min(TaskInstance.created_at))
            .filter(
                TaskInstance.template_id.in_(template_ids),
                TaskInstance.status == TaskStatus.open,
            )
            .group_by(TaskInstance.template_id)
            .all()
        )
        for template_id, ts in oldest_open_rows:
            if ts:
                stats.setdefault(int(template_id), {})["oldest_open"] = ts
        return stats

    async def announce_instance(self, instance_id: int, penalize: bool, *, note: str | None = None) -> None:
        with session_scope() as session:
            instance = session.get(TaskInstance, instance_id)
            if not instance:
                return
            if instance.status != TaskStatus.open:
                return
            instance.announcement_penalize = penalize
            instance.announcement_note = note
            instance.announced = False
            instance.last_announce_at = None
            session.flush()
        await self.announce_pending_tasks()

    async def _deliver_announcement(
        self,
        instance_id: int,
        *,
        penalize: bool | None = None,
        note: str | None,
    ) -> bool:
        if self.bot is None:
            return False
        if not settings.FAMILY_IDS:
            log.info("No family members to notify.")
            return True
        recipients: list[tuple[int, int]] = []
        allow_first = True
        allow_second = True
        with session_scope() as session:
            instance = session.get(TaskInstance, instance_id)
            if not instance or instance.status != TaskStatus.open:
                return False
            if penalize is None:
                penalize = instance.announcement_penalize
            if note is None:
                note = instance.announcement_note
            now = datetime.utcnow()
            cutoff = timedelta(minutes=settings.ANNOUNCE_CUTOFF_MINUTES)
            if instance.round_no == 0 and now - instance.created_at > cutoff:
                log.info(
                    "Skip backlog announcement for task %s (age=%s)",
                    instance_id,
                    (now - instance.created_at),
                )
                return True
            template = instance.template
            template_title = template.title
            safe_title = escape_html(template_title)
            base_points = instance.effective_points or template.base_points
            claim_timeout = template.claim_timeout_minutes
            penalty_value = template.nobody_claimed_penalty if penalize else 0
            family = [user for user in family_users(session) if user.tg_id]
            recipients = [(user.id, int(user.tg_id)) for user in family]
            if not recipients:
                log.info("No family members to notify for instance %s", instance_id)
                return
            if penalty_value:
                penalty_reason = f"{template_title}: никто не взял вовремя"
                for user in family:
                    add_score_event(
                        session,
                        user,
                        -penalty_value,
                        penalty_reason,
                        task_instance=instance,
                    )
            instance.last_announce_at = now
            instance.round_no = instance.round_no + 1
            allow_first = instance.deferrals_used < 1
            allow_second = instance.deferrals_used < 2
            session.flush()

        text = (
            f"🧹 Задача: <b>{safe_title}</b> (+{base_points}). "
            "Первый, кто нажмёт «Беру», забирает слот!"
        )
        if note:
            text = f"{text}\n{escape_html(note)}"
        if penalty_value:
            text = f"{text}\n⚠️ Никто не взял вовремя — штраф {penalty_value} баллов."

        try:
            await announce_task(
                self.bot,
                task_id=instance_id,
                template_title=template_title,
                text=text,
                recipients=recipients,
                allow_first_postpone=allow_first,
                allow_second_postpone=allow_second,
            )
        except Exception as exc:
            log.warning("Failed to announce task %s: %s", instance_id, exc)
            return False
        self.schedule_claim_deadline(instance_id, claim_timeout)
        log.info("Announcement sent for instance %s", instance_id)
        return True

    def schedule_claim_deadline(self, instance_id: int, claim_timeout: int) -> None:
        run_date = datetime.utcnow() + timedelta(minutes=claim_timeout)
        trigger = DateTrigger(run_date=run_date)
        self.scheduler.add_job(
            self._claim_timeout_job,
            trigger=trigger,
            args=[instance_id],
            id=self._job_id("claim_timeout", instance_id),
            **COMMON_JOB_OPTIONS,
        )
        log.debug("Claim deadline scheduled for instance %s at %s", instance_id, run_date.isoformat())

    async def _claim_timeout_job(self, instance_id: int) -> None:
        note: str | None = None
        with session_scope() as session:
            instance = session.get(TaskInstance, instance_id)
            if not instance or instance.status != TaskStatus.open:
                return
            template = instance.template
            penalty = template.nobody_claimed_penalty
            users = [user for user in family_users(session) if user.tg_id]
            if penalty:
                reason = f"{template.title}: никто не забрал"
                for user in users:
                    add_score_event(
                        session,
                        user,
                        -penalty,
                        reason,
                        task_instance=instance,
                    )
                note = f"⚠️ Никто не взял вовремя — штраф {penalty} баллов."
            instance.last_announce_at = None
            instance.round_no = 0
            instance.created_at = datetime.utcnow()
            instance.announced = False
            session.flush()
        log.info("Claim timeout reached for instance %s", instance_id)
        self.schedule_reannounce(instance_id, note=note)

    def schedule_reannounce(self, instance_id: int, *, note: str | None) -> None:
        run_date = now_tz(settings.TZ) + timedelta(minutes=CLAIM_REMINDER_MINUTES)
        trigger = DateTrigger(run_date=run_date)
        self.scheduler.add_job(
            self._reannounce_job,
            trigger=trigger,
            args=[instance_id, note],
            id=self._job_id("reannounce", instance_id),
            **COMMON_JOB_OPTIONS,
        )
        log.info("Reannounce for instance %s scheduled at %s", instance_id, run_date.isoformat())

    async def _reannounce_job(self, instance_id: int, note: str | None) -> None:
        await self.announce_instance(instance_id, penalize=False, note=note)

    async def check_missed_tasks(self) -> None:
        now = datetime.utcnow()
        reopen_ids: list[int] = []
        notifications: list[tuple[int, str]] = []
        with session_scope() as session:
            reserved = (
                session.query(TaskInstance)
                .filter(TaskInstance.status == TaskStatus.reserved)
                .all()
            )
            for inst in reserved:
                deadline = inst.reserved_until
                if not deadline:
                    continue
                if now <= deadline:
                    continue
                performer = session.get(User, inst.assigned_to) if inst.assigned_to else None
                title = inst.template.title
                penalty_value = missed_penalty(inst.template)
                if performer:
                    add_score_event(
                        session,
                        performer,
                        penalty_value,
                        f"{title}: просрочено",
                        task_instance=inst,
                    )
                    safe_title = escape_html(title)
                    notifications.append(
                        (
                            performer.tg_id,
                            (
                                f"⏰ Срок по задаче «{safe_title}» истёк."
                                f" {abs(penalty_value)} баллов за просрочку."
                            ),
                        )
                    )
                inst.status = TaskStatus.open
                inst.assigned_to = None
                inst.reserved_until = None
                inst.deferrals_used = 0
                inst.last_announce_at = None
                inst.created_at = datetime.utcnow()
                inst.round_no = 0
                inst.progress = 0
                inst.announced = False
                inst.announcement_note = None
                inst.announcement_penalize = False
                reopen_ids.append(inst.id)
        for tg_id, text in notifications:
            if self.bot:
                await safe_send_message(self.bot, tg_id, text)
        for instance_id in reopen_ids:
            await self.announce_instance(instance_id, penalize=False)
            log.info("Reopened missed instance %s", instance_id)

    async def check_vote_deadlines(self) -> None:
        deadline = datetime.utcnow() - timedelta(minutes=VOTE_SECOND_WAIT_MINUTES)
        with session_scope() as session:
            pending = (
                session.query(TaskInstance)
                .filter(TaskInstance.status == TaskStatus.report_submitted)
                .all()
            )
            for inst in pending:
                yes, no = votes_summary(session, inst)
                performer = session.get(User, inst.assigned_to) if inst.assigned_to else None
                family = family_users(session)
                expected_votes = inst.round_no or len([u for u in family if not performer or u.id != performer.id])
                if expected_votes and yes + no >= expected_votes:
                    continue
                if yes + no == 0:
                    first_vote = None
                else:
                    first_vote = (
                        session.query(Vote)
                        .filter(Vote.task_instance_id == inst.id)
                        .order_by(Vote.voted_at.asc())
                        .first()
                    )
                    if first_vote and first_vote.voted_at <= deadline:
                        await self.finalize_vote_job(inst.id)
                        continue
                if yes + no == 0:
                    submitted_at = inst.report.submitted_at if inst.report else inst.created_at
                    if submitted_at and submitted_at <= deadline:
                        await self.finalize_vote_job(inst.id)
                elif first_vote is None or first_vote.voted_at > deadline:
                    continue
                else:
                    await self.finalize_vote_job(inst.id)

    async def finalize_vote_job(self, instance_id: int) -> None:
        performer_tg_id: int | None = None
        performer_name = ""
        template_title = ""
        message = None
        verdict_text = ""
        broadcasts: list = []
        yes = no = 0
        with session_scope() as session:
            instance = session.get(TaskInstance, instance_id)
            if not instance or instance.status != TaskStatus.report_submitted:
                self.cancel_vote_deadline(instance_id)
                return
            yes, no = votes_summary(session, instance)
            performer = session.get(User, instance.assigned_to) if instance.assigned_to else None
            performer_tg_id = performer.tg_id if performer else None
            performer_name = performer.name if performer else ""
            template_title = instance.template.title
            safe_title = escape_html(template_title)
            family = family_users(session)
            expected_votes = instance.round_no or len([u for u in family if not performer or u.id != performer.id])
            missing = max(expected_votes - (yes + no), 0)
            effective_no = no + missing
            if yes > effective_no:
                reward = reward_for_completion(instance)
                if performer:
                    add_score_event(
                        session,
                        performer,
                        reward,
                        f"{template_title}: подтверждено",
                        task_instance=instance,
                    )
                instance.status = TaskStatus.approved
                instance.progress = 100
                message = f"✅ {safe_title} подтверждено. +{reward} баллов."
                verdict_text = "Отчёт принят ✅"
            else:
                session.query(Vote).filter(Vote.task_instance_id == instance.id).delete(synchronize_session=False)
                instance.attempts += 1
                instance.status = TaskStatus.reserved
                instance.progress = 50
                instance.round_no = 0
                if instance.report:
                    session.delete(instance.report)
                    instance.report = None
                message = f"❌ {safe_title} отклонено. Попробуй ещё раз!"
                verdict_text = "Отчёт отклонён ❌"
            broadcasts = list(pop_task_broadcasts(session, instance.id))
        self.cancel_vote_deadline(instance_id)
        log.info(
            "Vote finalized for instance %s (yes=%s, no=%s, decision=%s)",
            instance_id,
            yes,
            no,
            "approved" if message and message.startswith("✅") else "rejected",
        )
        if performer_tg_id and message and self.bot:
            await safe_send_message(self.bot, performer_tg_id, message)
        if broadcasts and message:
            await update_verification_messages(
                self.bot,
                broadcasts=broadcasts,
                template_title=template_title,
                performer_name=performer_name,
                verdict_text=verdict_text,
            )
        await self.announce_pending_tasks()

    def _should_generate(self, template: TaskTemplate, day: date) -> bool:
        if template.frequency == TaskFrequency.daily:
            return True
        if template.frequency == TaskFrequency.weekly:
            return day.weekday() == 0
        if template.frequency == TaskFrequency.every_2days:
            return day.toordinal() % 2 == 0
        if template.frequency == TaskFrequency.monthly:
            return day.day == 1
        return False


def load_seed_templates() -> Iterable[dict[str, object]]:
    data_path = Path(__file__).resolve().parent.parent / "data" / "task_templates.json"
    if not data_path.exists():
        return []
    with data_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


shared_scheduler = BotScheduler()
