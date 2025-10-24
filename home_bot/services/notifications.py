from aiogram.utils.keyboard import InlineKeyboardBuilder

def task_take_keyboard(instance_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Беру сейчас", callback_data=f"take_now:{instance_id}")
    kb.button(text="⏰ Беру через 30 мин", callback_data=f"take_later:{instance_id}")
    kb.adjust(1)
    return kb.as_markup()

def task_proof_keyboard(instance_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📸 Отправить фото", callback_data=f"send_photo:{instance_id}")
    kb.button(text="❌ Отменить (5 мин)", callback_data=f"cancel_task:{instance_id}")
    kb.adjust(1)
    return kb.as_markup()

def verification_keyboard(instance_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да", callback_data=f"verify:{instance_id}:yes")
    kb.button(text="❌ Нет", callback_data=f"verify:{instance_id}:no")
    kb.adjust(2)
    return kb.as_markup()
