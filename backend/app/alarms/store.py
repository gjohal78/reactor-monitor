"""Alarm persistence.

All writes go through a single worker thread, so they reach the database in the order
they happened: an occurrence's INSERT always lands before its UPDATEs, even though the
simulator loop never waits for them. Each write is an upsert of the whole record.
"""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.alarms.manager import AlarmRecord
from app.alarms.states import AlarmState
from app.db.models import Alarm

_RECORD_FIELDS = [f.name for f in fields(AlarmRecord)]


def _to_row(record: AlarmRecord) -> Alarm:
    values = {name: getattr(record, name) for name in _RECORD_FIELDS}
    values["state"] = record.state.value
    return Alarm(**values)


def to_record(row: Alarm) -> AlarmRecord:
    values = {name: getattr(row, name) for name in _RECORD_FIELDS}
    values["state"] = AlarmState(row.state)
    return AlarmRecord(**values)


class AlarmStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="alarm-store")

    async def save(self, record: AlarmRecord) -> None:
        await asyncio.get_running_loop().run_in_executor(self._executor, self._save, record)

    async def load_open(self) -> list[AlarmRecord]:
        return await asyncio.get_running_loop().run_in_executor(self._executor, self._load_open)

    async def exists(self, alarm_id: uuid.UUID) -> bool:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._exists, alarm_id
        )

    def close(self) -> None:
        """Finish queued writes, then stop the worker thread."""
        self._executor.shutdown(wait=True)

    def _save(self, record: AlarmRecord) -> None:
        with self._session_factory() as session, session.begin():
            session.merge(_to_row(record))

    def _load_open(self) -> list[AlarmRecord]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(Alarm).where(Alarm.state != AlarmState.NORMAL.value)
            ).all()
            return [to_record(row) for row in rows]

    def _exists(self, alarm_id: uuid.UUID) -> bool:
        with self._session_factory() as session:
            return session.get(Alarm, alarm_id) is not None
