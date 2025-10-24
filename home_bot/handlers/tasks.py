from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from ..db.repo import get_session, list_users, create_instance, get_instance, save_history, get_user_by_tid
from ..db.models import Task, TaskInstance, InstanceState, User, Task as TaskModel
from ..services.notifications import task_take_keyboard, task_proof_keyboard, verification_keyboard
from ..services.rules import compute_reward, reward_done, penalty_late_cancel
from ..config import settings

router = Router()

@router.message(Command("announce"))
async def announce(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("Только админ.")
        return
    with get_session() as s:
        task = s.query(TaskModel).order_by(TaskModel.id.asc()).first()
        if not task:
            await message.answer("Нет задач в базе.")
            return
        inst = create_instance(s, task)
        users = list_users(s)
        chat_ids = [u.telegram_id for u in users]
    from ..main import scheduler  # initialized in main
    await scheduler._announce_job(chat_ids, task, inst.id)

@router.callback_query(F.data.startswith("take_now:"))
async def take_now(cb: CallbackQuery):
    instance_id = int(cb.data.split(":")[1])
    with get_session() as s:
        inst = get_instance(s, instance_id)
        if not inst or inst.state != InstanceState.announced:
            await cb.answer("Увы, уже занято.")
            return
        user = get_user_by_tid(s, cb.from_user.id)
        if not user:
            await cb.answer("Сначала /start")
            return
        inst.assignee_id = user.id
        inst.state = InstanceState.awaiting_proof
        s.commit()
    await cb.message.edit_text(f"Задача закреплена за {cb.from_user.full_name}. Отправь фото-доказательство в этот чат.",
                               reply_markup=task_proof_keyboard(instance_id))
    await cb.answer("Ты взял задачу 'сейчас'. Удачи!")

@router.callback_query(F.data.startswith("take_later:"))
async def take_later(cb: CallbackQuery):
    instance_id = int(cb.data.split(":")[1])
    with get_session() as s:
        inst = get_instance(s, instance_id)
        if not inst or inst.state != InstanceState.announced:
            await cb.answer("Увы, уже занято.")
            return
        user = get_user_by_tid(s, cb.from_user.id)
        if not user:
            await cb.answer("Сначала /start")
            return
        inst.assignee_id = user.id
        inst.state = InstanceState.awaiting_proof
        inst.defer_count = min(2, (inst.defer_count or 0) + 1)
        s.commit()
    await cb.message.edit_text(f"Задача забронирована {cb.from_user.full_name} с отсрочкой (#{inst.defer_count}). Отправь фото по готовности.",
                               reply_markup=task_proof_keyboard(instance_id))
    await cb.answer("Принято, у тебя отсрочка. Награда будет меньше.")

@router.callback_query(F.data.startswith("cancel_task:"))
async def cancel_task(cb: CallbackQuery):
    instance_id = int(cb.data.split(":")[1])
    with get_session() as s:
        inst = get_instance(s, instance_id)
        if not inst or inst.assignee_id is None:
            await cb.answer("Некорректно")
            return
        user = get_user_by_tid(s, cb.from_user.id)
        if not user or user.id != inst.assignee_id:
            await cb.answer("Эта задача не на тебе.")
            return
        penalty_late_cancel(s, user, inst.id)
        inst.state = InstanceState.announced
        inst.assignee_id = None
        s.commit()
    await cb.message.edit_text("Отмена принята. Задача снова доступна всем.")
    await cb.answer()

@router.callback_query(F.data.startswith("send_photo:"))
async def ask_photo(cb: CallbackQuery):
    await cb.message.answer("Пришли фото как ответ на это сообщение. 📸")
    await cb.answer()

@router.message(F.photo)
async def receive_photo(message: Message):
    from ..db.models import Verification
    with get_session() as s:
        user = get_user_by_tid(s, message.from_user.id)
        if not user:
            await message.answer("Сначала /start")
            return
        inst = s.query(TaskInstance).filter(TaskInstance.assignee_id == user.id, TaskInstance.state == "awaiting_proof").order_by(TaskInstance.id.desc()).first()
        if not inst:
            await message.answer("Нет задач в ожидании фото.")
            return
        file_id = message.photo[-1].file_id
        ver = Verification(task_instance_id=inst.id, photo_file_id=file_id, votes_yes=0, votes_no=0)
        s.add(ver)
        inst.state = "awaiting_check"
        s.commit(); s.refresh(ver)
        all_users = s.query(User).all()
        others = [u for u in all_users if u.id != user.id]
        kb = verification_keyboard(inst.id)
        for u in others:
            try:
                await message.bot.send_photo(u.telegram_id, photo=file_id, caption=f"Проверка: {user.nickname or user.name} — выполнил(а) задачу. Подтвердите?",
                                             reply_markup=kb)
            except Exception:
                pass
    await message.answer("Фото получено. Ждём проверки остальных.")

@router.callback_query(F.data.startswith("verify:"))
async def verify(cb: CallbackQuery):
    _, inst_id_str, vote = cb.data.split(":")
    instance_id = int(inst_id_str)
    from ..db.models import Verification, Task, User
    with get_session() as s:
        ver = s.query(Verification).filter_by(task_instance_id=instance_id).one_or_none()
        inst = s.query(TaskInstance).get(instance_id)
        if not ver or not inst:
            await cb.answer("Просрочено.")
            return
        voter = get_user_by_tid(s, cb.from_user.id)
        if not voter:
            await cb.answer("Сначала /start")
            return
        if voter.id == inst.assignee_id:
            await cb.answer("Исполнитель не голосует.")
            return
        # save vote
        if ver.voter1_id is None:
            ver.voter1_id = voter.id
            ver.voter1_vote = vote
            from ..utils.time import now_tz
            from ..config import settings
            ver.first_vote_at = ver.first_vote_at or now_tz(settings.TZ)
        elif ver.voter2_id is None and voter.id != ver.voter1_id:
            ver.voter2_id = voter.id
            ver.voter2_vote = vote
        else:
            await cb.answer("Ваш голос учтён ранее.")
            return
        yes = (1 if ver.voter1_vote == "yes" else 0) + (1 if ver.voter2_vote == "yes" else 0)
        no = (1 if ver.voter1_vote == "no" else 0) + (1 if ver.voter2_vote == "no" else 0)
        s.commit()
        # finalize if both voted
        if (ver.voter1_id and ver.voter2_id):
            await finalize_verification(cb, s, inst, ver, yes, no)
            return
    await cb.answer("Голос учтён.")

async def finalize_verification(cb: CallbackQuery, s, inst: TaskInstance, ver, yes: int, no: int):
    from ..db.models import User, Task
    task = s.query(Task).get(inst.task_id)
    assignee = s.query(User).get(inst.assignee_id) if inst.assignee_id else None
    if yes >= 2:
        reward = compute_reward(task, inst.defer_count, repeats_penalty_steps=0)
        reward_done(s, assignee, inst.id, reward)
        assignee.monthly_points += reward
        inst.state = "done"; inst.reward_points_final = reward
        s.commit()
        try:
            await cb.message.edit_caption((cb.message.caption or "") + f"\n✅ Подтверждено. +{reward} баллов.")
        except Exception:
            pass
    elif no >= 2:
        inst.state = "failed"
        s.commit()
        try:
            await cb.message.edit_caption((cb.message.caption or "") + "\n❌ Отклонено двумя участниками. Баллы не начислены.")
        except Exception:
            pass
    else:
        await cb.message.answer("Спорная ситуация (1 Да / 1 Нет). Видео-перепроверка может быть добавлена позже в коде.")
