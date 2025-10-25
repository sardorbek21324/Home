"""Background scheduler for recurring bot tasks."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from ..config import settings
from ..db.models import TaskFrequency, TaskInstance, TaskStatus, TaskTemplate, User, Vote
from ..db.repo import (
    add_score_event,
    create_instance,
    list_users,
    open_dispute,
    session_scope,
    votes_summary,
)
from ..domain.constants import CLAIM_REMINDER_MINUTES, VOTE_SECOND_WAIT_MINUTES
from ..services.notifications import task_announce_keyboard
from ..services.scoring import missed_penalty, reward_for_completion
from ..utils.time import (
    in_quiet_hours,
    next_allowed_moment,
    now_tz,
    parse_quiet_hours,
)


log = logging.getLogger(__name__)


class BotScheduler:
    """High level orchestrator for timed events."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.TZ))
        self.quiet_hours = parse_quiet_hours(settings.QUIET_HOURS)

    def start(self) -> None:
        self.scheduler.start()
        self.scheduler.add_job(self.generate_today_tasks, CronTrigger(hour=4, minute=0))
        self.scheduler.add_job(self.check_missed_tasks, "interval", minutes=5)
        self.scheduler.add_job(self.check_vote_deadlines, "interval", minutes=5)
        log.info("Scheduler started")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

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
            replace_existing=True,
        )
        log.info("Vote deadline scheduled for instance %s at %s", instance_id, run_date.isoformat())

    async def generate_today_tasks(self) -> None:
        await self.generate_tasks_for_day(date.today())

    async def generate_tasks_for_day(self, day: date) -> None:
        new_instances: list[int] = []
        with session_scope() as session:
            templates = session.query(TaskTemplate).all()
            for template in templates:
                if not self._should_generate(template, day):
                    continue
                slots = template.max_per_day or 1
                for slot in range(1, slots + 1):
                    exists = (
                        session.query(TaskInstance)
                        .filter(
                            TaskInstance.template_id == template.id,
                            TaskInstance.day == day,
                            TaskInstance.slot == slot,
                        )
                        .one_or_none()
                    )
                    if exists:
                        continue
                    instance = create_instance(session, template, day=day, slot=slot)
                    new_instances.append(instance.id)
                    log.info(
                        "Generated instance %s for template %s (%s)",
                        instance.id,
                        template.code,
                        day,
                    )
        for instance_id in new_instances:
            await self.announce_instance(instance_id, penalize=False)

    async def announce_instance(self, instance_id: int, penalize: bool, *, note: str | None = None) -> None:
        now = now_tz(settings.TZ)
        if in_quiet_hours(now, self.quiet_hours):
            run_at = next_allowed_moment(now, self.quiet_hours)
            trigger = DateTrigger(run_date=run_at)
            self.scheduler.add_job(
                self.announce_instance,
                trigger=trigger,
                args=[instance_id, penalize],
                kwargs={"note": note},
                id=self._job_id("announce", instance_id),
                replace_existing=True,
            )
            log.info(
                "Delayed announcement for instance %s to %s because of quiet hours",
                instance_id,
                run_at.isoformat(),
            )
            return

        await self._deliver_announcement(instance_id, penalize=penalize, note=note)

    async def _deliver_announcement(self, instance_id: int, *, penalize: bool, note: str | None) -> None:
        with session_scope() as session:
            instance = session.get(TaskInstance, instance_id)
            if not instance or instance.status != TaskStatus.open:
                return
            template = instance.template
            template_title = template.title
            base_points = template.base_points
            claim_timeout = template.claim_timeout_minutes
            penalty_value = template.nobody_claimed_penalty if penalize else 0
            users = list(list_users(session))
            recipients = [(user.tg_id, user.name) for user in users]
            if not users:
                log.info("No users to notify for instance %s", instance_id)
                return
            penalty_reason = None
            if penalty_value:
                penalty_reason = f"{template_title}: никто не взял вовремя"
                for user in users:
                    add_score_event(
                        session,
                        user,
                        -penalty_value,
                        penalty_reason,
                        task_instance=instance,
                    )
            instance.last_announce_at = datetime.utcnow()
            session.flush()

        text = (
            f"🧹 Задача: {template_title}\n"
            f"Награда: +{base_points} баллов."
        )
        if note:
            text += f"\n{note}"
        if penalty_value:
            text += f"\n⚠️ Никто не взял вовремя — штраф {penalty_value} баллов."

        markup = task_announce_keyboard(instance_id, can_defer=True)
        for tg_id, _ in recipients:
            try:
                await self.bot.send_message(tg_id, text, reply_markup=markup)
            except Exception as exc:
                log.warning("Failed to announce task to %s: %s", tg_id, exc)
        self.schedule_claim_deadline(instance_id, claim_timeout)
        log.info("Announcement sent for instance %s", instance_id)

    def schedule_claim_deadline(self, instance_id: int, claim_timeout: int) -> None:
        run_date = datetime.utcnow() + timedelta(minutes=claim_timeout)
        trigger = DateTrigger(run_date=run_date)
        self.scheduler.add_job(
            self._claim_timeout_job,
            trigger=trigger,
            args=[instance_id],
            id=self._job_id("claim_timeout", instance_id),
            replace_existing=True,
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
            users = list(list_users(session))
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
            replace_existing=True,
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
                    notifications.append(
                        (
                            performer.tg_id,
                            f"⏰ Срок по задаче «{title}» истёк. {abs(penalty_value)} баллов за просрочку.",
                        )
                    )
                inst.status = TaskStatus.open
                inst.assigned_to = None
                inst.reserved_until = None
                inst.deferrals_used = 0
                inst.last_announce_at = None
                inst.created_at = datetime.utcnow()
                reopen_ids.append(inst.id)
        for tg_id, text in notifications:
            try:
                await self.bot.send_message(tg_id, text)
            except Exception as exc:
                log.warning("Failed to notify missed deadline to %s: %s", tg_id, exc)
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
                if yes + no == 0 or yes + no >= 2:
                    continue
                first_vote = (
                    session.query(Vote)
                    .filter(Vote.task_instance_id == inst.id)
                    .order_by(Vote.voted_at.asc())
                    .first()
                )
                if not first_vote or first_vote.voted_at > deadline:
                    continue
                await self.finalize_vote_job(inst.id)

    async def finalize_vote_job(self, instance_id: int) -> None:
        performer_tg_id = None
        message = None
        with session_scope() as session:
            instance = session.get(TaskInstance, instance_id)
            if not instance or instance.status != TaskStatus.report_submitted:
                self.cancel_vote_deadline(instance_id)
                return
            yes, no = votes_summary(session, instance)
            if yes == 0 and no == 0:
                self.cancel_vote_deadline(instance_id)
                return
            performer = session.get(User, instance.assigned_to) if instance.assigned_to else None
            template_title = instance.template.title
            if yes > no:
                reward = reward_for_completion(instance.template, instance.deferrals_used)
                if performer:
                    add_score_event(
                        session,
                        performer,
                        reward,
                        f"{template_title}: подтверждено",
                        task_instance=instance,
                    )
                instance.status = TaskStatus.approved
                message = f"✅ {template_title} подтверждено. +{reward} баллов."
            else:
                instance.status = TaskStatus.rejected
                if performer:
                    open_dispute(session, instance, performer, note="Автоотклонение по голосованию")
                message = f"❌ {template_title} отклонено."
            performer_tg_id = performer.tg_id if performer else None
        self.cancel_vote_deadline(instance_id)
        log.info(
            "Vote finalized for instance %s (yes=%s, no=%s, decision=%s)",
            instance_id,
            yes,
            no,
            "approved" if yes > no else "rejected",
        )
        if performer_tg_id and message:
            try:
                await self.bot.send_message(performer_tg_id, message)
            except Exception as exc:
                log.warning("Failed to send vote result to %s: %s", performer_tg_id, exc)

    def _should_generate(self, template: TaskTemplate, day: date) -> bool:
        if template.frequency == TaskFrequency.daily:
            return True
        if template.frequency == TaskFrequency.weekly:
            return day.weekday() == 0
        if template.frequency == TaskFrequency.every_2days:
            return day.toordinal() % 2 == 0
        return False


def load_seed_templates() -> Iterable[dict[str, object]]:
    data_path = Path(__file__).resolve().parent.parent / "data" / "task_templates.json"
    if not data_path.exists():
        return []
    with data_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
