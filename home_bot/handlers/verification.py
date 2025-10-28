from __future__ import annotations

"""Handlers responsible for peer verification of reports."""

import logging
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..db.models import TaskInstance, TaskStatus, User, Vote, VoteValue
from ..db.repo import (
    add_score_event,
    family_users,
    pop_task_broadcasts,
    register_vote,
    session_scope,
    votes_summary,
)
from ..services.scoring import reward_for_completion
from ..services.notifications import update_verification_messages
from ..services.scheduler import get_lifecycle_controller

if TYPE_CHECKING:
    from ..services.scheduler import BotScheduler


router = Router()
log = logging.getLogger(__name__)


def _get_scheduler() -> "BotScheduler | None":
    return get_lifecycle_controller()


@router.callback_query(F.data.startswith("vote:"))
async def handle_vote(cb: CallbackQuery) -> None:
    if cb.from_user is None:
        return
    parts = cb.data.split(":")
    if len(parts) != 3:
        await cb.answer()
        return
    _, inst_id_str, value = parts
    instance_id = int(inst_id_str)

    performer_tg_id = None
    performer_name = ""
    feedback = "Голос учтён."
    decision = None
    broadcasts: list | tuple = []
    verdict_text = ""

    with session_scope() as session:
        instance = session.get(TaskInstance, instance_id)
        if not instance or instance.status != TaskStatus.report_submitted:
            await cb.answer("Проверка уже завершена.", show_alert=True)
            return
        voter = session.query(User).filter(User.tg_id == cb.from_user.id).one_or_none()
        if not voter:
            await cb.answer("Сначала /start", show_alert=True)
            return
        if instance.assigned_to == voter.id:
            await cb.answer("Исполнитель не голосует.", show_alert=True)
            return
        already = (
            session.query(Vote)
            .filter(Vote.task_instance_id == instance.id, Vote.voter_id == voter.id)
            .one_or_none()
        )
        if already:
            await cb.answer("Голос уже учтён.")
            return
        performer = session.get(User, instance.assigned_to) if instance.assigned_to else None
        performer_tg_id = performer.tg_id if performer else None
        performer_name = performer.name if performer else ""
        family = family_users(session)
        expected_votes = instance.round_no or len([u for u in family if not performer or u.id != performer.id])
        if instance.round_no != expected_votes:
            instance.round_no = expected_votes
        register_vote(session, instance, voter, VoteValue(value))
        yes, no = votes_summary(session, instance)
        template_title = instance.template.title
        total_votes = yes + no

        lifecycle = _get_scheduler()
        if lifecycle and expected_votes:
            if total_votes >= expected_votes:
                lifecycle.cancel_vote_deadline(instance.id)

        if expected_votes and total_votes >= expected_votes and performer:
            if yes > no:
                reward = reward_for_completion(instance)
                add_score_event(
                    session,
                    performer,
                    reward,
                    f"{template_title}: выполнено",
                    task_instance=instance,
                )
                instance.status = TaskStatus.approved
                instance.progress = 100
                feedback = f"✅ {template_title} подтверждено. +{reward} баллов."
                verdict_text = "Отчёт принят ✅"
                decision = "approved"
            else:
                session.query(Vote).filter(Vote.task_instance_id == instance.id).delete(synchronize_session=False)
                instance.attempts += 1
                instance.status = TaskStatus.reserved
                instance.progress = 50
                instance.round_no = 0
                if instance.report:
                    session.delete(instance.report)
                    instance.report = None
                feedback = f"❌ {template_title} отклонено. Попробуй ещё раз!"
                verdict_text = "Отчёт отклонён ❌"
                decision = "retry"
            broadcasts = pop_task_broadcasts(session, instance.id)
        else:
            feedback = "Голос принят. Ждём остальных."

    if performer_tg_id and decision:
        try:
            await cb.bot.send_message(performer_tg_id, feedback)
        except Exception as exc:
            log.warning("Failed to deliver vote result to %s: %s", performer_tg_id, exc)
    if decision and broadcasts:
        await update_verification_messages(
            cb.bot,
            broadcasts=broadcasts,
            template_title=template_title,
            performer_name=performer_name or cb.from_user.full_name,
            verdict_text=verdict_text or feedback,
        )
    await cb.answer(feedback if decision else "Голос учтён. Ждём остальных.")
    log.info(
        "Vote %s recorded for instance %s by %s (yes=%s, no=%s, decision=%s)",
        value,
        instance_id,
        cb.from_user.full_name,
        yes,
        no,
        decision,
    )
