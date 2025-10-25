"""Background scheduler for recurring bot tasks."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from ..config import settings
from ..db.models import TaskFrequency, TaskInstance, TaskStatus, TaskTemplate, User, Vote
from ..db.repo import add_score_event, create_instance, list_users, session_scope, votes_summary
from ..domain.constants import CLAIM_REMINDER_MINUTES, VOTE_SECOND_WAIT_MINUTES
from ..services.notifications import task_announce_keyboard
from ..services.scoring import missed_penalty, reward_for_completion
from ..utils.time import in_quiet_hours, now_tz, parse_quiet_hours


log = logging.getLogger(__name__)


class BotScheduler:
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.TZ))
        self.quiet_hours = parse_quiet_hours(settings.QUIET_HOURS)

    def start(self) -> None:
        self.scheduler.start()
        self.scheduler.add_job(self.generate_today_tasks, "cron", hour=4, minute=0)
        self.scheduler.add_job(self.remind_open_tasks, "interval", minutes=CLAIM_REMINDER_MINUTES)
        self.scheduler.add_job(self.check_missed_tasks, "interval", minutes=10)
        self.scheduler.add_job(self.check_vote_deadlines, "interval", minutes=5)
        log.info("Scheduler started")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def schedule_vote_deadline(self, instance_id: int) -> None:
        run_date = now_tz(settings.TZ) + timedelta(minutes=VOTE_SECOND_WAIT_MINUTES)
        trigger = DateTrigger(run_date=run_date)
        self.scheduler.add_job(self.finalize_vote_job, trigger=trigger, args=[instance_id], id=f"vote:{instance_id}", replace_existing=True)

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

        for instance_id in new_instances:
            await self.announce_instance(instance_id, penalize=False)

    async def announce_instance(self, instance_id: int, penalize: bool) -> None:
        if in_quiet_hours(now_tz(settings.TZ), self.quiet_hours):
            return

        with session_scope() as session:
            instance = session.get(TaskInstance, instance_id)
            if not instance:
                return
            template = instance.template
            template_title = template.title
            base_points = template.base_points
            penalty_value = template.nobody_claimed_penalty
            user_objects = list_users(session)
            users = [(u.tg_id, u.name) for u in user_objects]
            instance.last_announce_at = datetime.utcnow()
            session.flush()
            penalty_reason = None
            if penalize and penalty_value:
                penalty_reason = f"{template_title}: никто не взял"
                for user in user_objects:
                    add_score_event(session, user, -penalty_value, penalty_reason, task_instance=instance)

        text = (
            f"🧹 Задача: {template_title}\n"
            f"Награда: +{base_points} баллов."
        )
        if penalize and penalty_reason:
            text += f"\n⚠️ Никто не взял вовремя — штраф {penalty_value} баллов."
        markup = task_announce_keyboard(instance_id, can_defer=True)
        for tg_id, _ in users:
            try:
                await self.bot.send_message(tg_id, text, reply_markup=markup)
            except Exception as exc:
                log.warning("Failed to announce task to %s: %s", tg_id, exc)

    async def remind_open_tasks(self) -> None:
        now = datetime.utcnow()
        with session_scope() as session:
            stale_ids = [
                inst.id
                for inst in session.query(TaskInstance)
                .filter(
                    TaskInstance.status == TaskStatus.open,
                    (TaskInstance.last_announce_at.is_(None))
                    | (TaskInstance.last_announce_at < now - timedelta(minutes=CLAIM_REMINDER_MINUTES)),
                )
                .all()
            ]
        for instance_id in stale_ids:
            await self.announce_instance(instance_id, penalize=True)

    async def check_missed_tasks(self) -> None:
        now = datetime.utcnow()
        reopen_ids: list[tuple[int, int, str]] = []
        reannounce_ids: list[int] = []
        with session_scope() as session:
            reserved = session.query(TaskInstance).filter(TaskInstance.status == TaskStatus.reserved).all()
            for inst in reserved:
                start = inst.reserved_until or inst.created_at
                if now > start + timedelta(minutes=inst.template.sla_minutes):
                    performer = session.get(User, inst.assigned_to) if inst.assigned_to else None
                    if performer:
                        penalty = missed_penalty(inst.template)
                        add_score_event(session, performer, penalty, f"{inst.template.title}: просрочено", task_instance=inst)
                        reopen_ids.append((performer.tg_id, penalty, inst.template.title))
                    inst.status = TaskStatus.open
                    inst.assigned_to = None
                    inst.reserved_until = None
                    inst.deferrals_used = 0
                    inst.last_announce_at = None
                    inst.created_at = datetime.utcnow()
                    reannounce_ids.append(inst.id)

        for tg_id, penalty, title in reopen_ids:
            try:
                await self.bot.send_message(tg_id, f"⏰ Срок {title} вышел. {penalty} баллов за просрочку.")
            except Exception:
                pass

        for inst_id in reannounce_ids:
            await self.announce_instance(inst_id, penalize=False)

    async def check_vote_deadlines(self) -> None:
        deadline = datetime.utcnow() - timedelta(minutes=VOTE_SECOND_WAIT_MINUTES)
        notifications: list[tuple[int, str]] = []
        with session_scope() as session:
            pending = session.query(TaskInstance).filter(TaskInstance.status == TaskStatus.report_submitted).all()
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
                if first_vote and first_vote.voted_at <= deadline:
                    performer = session.get(User, inst.assigned_to) if inst.assigned_to else None
                    template_title = inst.template.title
                    if yes > no:
                        reward = reward_for_completion(inst.template, inst.deferrals_used)
                        if performer:
                            add_score_event(
                                session,
                                performer,
                                reward,
                                f"{template_title}: автоподтверждение",
                                task_instance=inst,
                            )
                        inst.status = TaskStatus.approved
                        if performer:
                            notifications.append((performer.tg_id, f"✅ {template_title} одобрено автоматически. +{reward} баллов."))
                    else:
                        inst.status = TaskStatus.rejected
                        if performer:
                            notifications.append((performer.tg_id, f"❌ {template_title} отклонено автоматически."))

        for tg_id, text in notifications:
            try:
                await self.bot.send_message(tg_id, text)
            except Exception:
                pass

    async def finalize_vote_job(self, instance_id: int) -> None:
        performer_tg_id = None
        text = None
        with session_scope() as session:
            instance = session.get(TaskInstance, instance_id)
            if not instance or instance.status != TaskStatus.report_submitted:
                return
            yes, no = votes_summary(session, instance)
            if yes + no >= 2:
                return
            if yes == 0 and no == 0:
                return
            performer = session.get(User, instance.assigned_to) if instance.assigned_to else None
            performer_tg_id = performer.tg_id if performer else None
            template_title = instance.template.title
            if yes > no:
                reward = reward_for_completion(instance.template, instance.deferrals_used)
                if performer:
                    add_score_event(
                        session,
                        performer,
                        reward,
                        f"{template_title}: автоподтверждение",
                        task_instance=instance,
                    )
                instance.status = TaskStatus.approved
                text = f"✅ {template_title} одобрено автоматически. +{reward} баллов."
            else:
                instance.status = TaskStatus.rejected
                text = f"❌ {template_title} отклонено автоматически."

        if performer_tg_id and text:
            try:
                await self.bot.send_message(performer_tg_id, text)
            except Exception:
                pass

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
