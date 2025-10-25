from __future__ import annotations

"""Handlers responsible for peer verification of reports."""

import logging
from typing import TYPE_CHECKING

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from ..db.models import TaskInstance, TaskStatus, User, Vote, VoteValue
from ..db.repo import add_score_event, open_dispute, register_vote, session_scope, votes_summary
from ..services.scoring import reward_for_completion

if TYPE_CHECKING:
    from ..services.scheduler import BotScheduler


router = Router()
log = logging.getLogger(__name__)


def _get_scheduler(bot: Bot) -> "BotScheduler | None":
    try:
        return bot["lifecycle"]
    except KeyError:
        return None


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
    feedback = "Голос учтён."
    decision = None

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
        register_vote(session, instance, voter, VoteValue(value))
        yes, no = votes_summary(session, instance)
        template_title = instance.template.title
        performer = session.get(User, instance.assigned_to) if instance.assigned_to else None
        performer_tg_id = performer.tg_id if performer else None
        total_votes = yes + no

        lifecycle = _get_scheduler(cb.bot)
        if lifecycle:
            if total_votes == 1:
                lifecycle.schedule_vote_deadline(instance.id)
            elif total_votes >= 2:
                lifecycle.cancel_vote_deadline(instance.id)

        if yes >= 2:
            decision = "approved"
        elif no >= 2 or (yes + no == 2 and yes <= no):
            decision = "rejected"

        if decision and performer:
            if decision == "approved":
                reward = reward_for_completion(instance.template, instance.deferrals_used)
                add_score_event(
                    session,
                    performer,
                    reward,
                    f"{template_title}: выполнено",
                    task_instance=instance,
                )
                instance.status = TaskStatus.approved
                feedback = f"✅ {template_title} подтверждено. +{reward} баллов."
            else:
                open_dispute(
                    session,
                    instance,
                    voter,
                    note="Отклонено голосованием",
                )
                feedback = (
                    f"❌ {template_title} отклонено. Решение отправлено в споры."
                )
        else:
            feedback = "Голос принят. Ждём остальных."

    if performer_tg_id and decision:
        try:
            await cb.bot.send_message(performer_tg_id, feedback)
        except Exception as exc:
            log.warning("Failed to deliver vote result to %s: %s", performer_tg_id, exc)
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
