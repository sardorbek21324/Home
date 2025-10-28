import os
import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("BOT_TOKEN", "test-token")

from home_bot.db.models import (  # noqa: E402
    Base,
    TaskFrequency,
    TaskInstance,
    TaskKind,
    TaskStatus,
    TaskTemplate,
    User,
)
from home_bot.db.repo import ensure_ai_settings  # noqa: E402
from home_bot.services.ai_controller import AIController  # noqa: E402


class AIControllerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        Base.metadata.create_all(bind=engine)
        self.controller = AIController(session_factory=self.Session)
        with self.Session() as session:
            ensure_ai_settings(session)
            user = User(tg_id=101, name="Tester", username=None)
            session.add(user)
            session.flush()
            template = TaskTemplate(
                code="demo",
                title="Demo task",
                base_points=25,
                frequency=TaskFrequency.daily,
                max_per_day=None,
                sla_minutes=30,
                claim_timeout_minutes=15,
                kind=TaskKind.house,
            )
            session.add(template)
            session.flush()
            session.add_all(
                [
                    TaskInstance(
                        template=template,
                        day=date.today(),
                        slot=1,
                        status=TaskStatus.approved,
                        assigned_to=user.id,
                        effective_points=template.base_points,
                        progress=100,
                    ),
                    TaskInstance(
                        template=template,
                        day=date.today() + timedelta(days=1),
                        slot=2,
                        status=TaskStatus.rejected,
                        assigned_to=user.id,
                        effective_points=template.base_points,
                        progress=50,
                    ),
                ]
            )
            session.flush()
            session.commit()

    def test_coefficients_reflect_history(self) -> None:
        with self.Session() as session:
            stats = self.controller.get_user_stats(session)
        self.assertEqual(len(stats), 1)
        stat = stats[0]
        self.assertEqual(stat.taken, 2)
        self.assertEqual(stat.completed, 1)
        self.assertEqual(stat.skipped, 1)
        self.assertAlmostEqual(stat.coefficient, 1.02, places=2)

    def test_apply_to_points_uses_average(self) -> None:
        with self.Session() as session:
            effective = self.controller.apply_to_points(session, 25)
        self.assertEqual(effective, 26)


if __name__ == "__main__":
    unittest.main()
