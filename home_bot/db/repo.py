from . import SessionLocal, engine, Base
from .models import *
from sqlalchemy.orm import Session
from typing import Iterable, Optional

def init_db():
    Base.metadata.create_all(bind=engine)

def get_session() -> Session:
    return SessionLocal()

def upsert_user(session: Session, telegram_id: int, name: str, nickname: str | None, role: Role) -> User:
    u = session.query(User).filter_by(telegram_id=telegram_id).one_or_none()
    if u is None:
        u = User(telegram_id=telegram_id, name=name, nickname=nickname, role=role)
        session.add(u)
        session.commit()
        session.refresh(u)
    else:
        u.name = name
        if nickname is not None:
            u.nickname = nickname
        session.commit()
    return u

def list_users(session: Session) -> list[User]:
    return session.query(User).all()

def get_user_by_tid(session: Session, telegram_id: int) -> Optional[User]:
    return session.query(User).filter_by(telegram_id=telegram_id).one_or_none()

def get_or_create_tasks_from_seed(session: Session, seed: Iterable[dict]):
    name_to_task = {t.name: t for t in session.query(Task).all()}
    for d in seed:
        if d["name"] not in name_to_task:
            t = Task(
                name=d["name"], kind=TaskKind(d["kind"]), base_points=d["base_points"],
                freq=d["freq"], response_window_minutes=d["response_window_minutes"],
                execution_window_minutes=d["execution_window_minutes"],
                min_points=d["min_points"], max_points=d["max_points"]
            )
            session.add(t)
    session.commit()

def create_instance(session: Session, task: Task) -> TaskInstance:
    inst = TaskInstance(task_id=task.id, state=InstanceState.announced)
    session.add(inst); session.commit(); session.refresh(inst)
    return inst

def find_task_by_name(session: Session, name: str) -> Optional[Task]:
    return session.query(Task).filter(Task.name == name).one_or_none()

def get_task(session: Session, task_id: int) -> Task | None:
    return session.query(Task).get(task_id)

def get_instance(session: Session, instance_id: int) -> TaskInstance | None:
    return session.query(TaskInstance).get(instance_id)

def save_history(session: Session, user_id: int, instance_id: int | None, delta: int, reason: str):
    h = History(user_id=user_id, task_instance_id=instance_id, delta=delta, reason=reason)
    session.add(h)
    session.commit()
