import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from ..utils.time import now_tz, in_quiet_hours, parse_quiet_hours
from ..config import settings
from ..db.repo import get_session, list_users
from ..db.models import Task
from aiogram import Bot
from .notifications import task_take_keyboard

log = logging.getLogger(__name__)

class BotScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.sched = AsyncIOScheduler(timezone=settings.TZ)
        self.quiet = parse_quiet_hours(settings.QUIET_HOURS)

    def start(self):
        self.sched.start()

    def schedule_announce(self, when: datetime, chat_ids: list[int], task: Task, instance_id: int):
        self.sched.add_job(self._announce_job, "date", run_date=when, args=[chat_ids, task, instance_id])

    async def _announce_job(self, chat_ids: list[int], task: Task, instance_id: int):
        now = now_tz(settings.TZ)
        if in_quiet_hours(now, self.quiet):
            log.info("Quiet hours; skip announce")
            return
        kb = task_take_keyboard(instance_id)
        for cid in chat_ids:
            try:
                await self.bot.send_message(cid, f"🧩 Задание: {task.name} (+{task.base_points})\nКто первый возьмет?", reply_markup=kb)
            except Exception as e:
                log.warning("Send announce failed to %s: %s", cid, e)
