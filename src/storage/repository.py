"""Repository: đọc/ghi kết quả đối soát + checkpoint vào SQLite."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..domain import (
    CargoType,
    LinehaulLeg,
    ReconciliationResult,
    ReconciliationStatus,
    TOSubType,
)
from .models import LegCheckpointRow, ReconciliationResultRow, ScanStateRow

OPEN_STATUSES = {ReconciliationStatus.PENDING_GRACE.value, ReconciliationStatus.MISSING.value}
_LAST_SCAN_KEY = "last_scan_at"


class ReconciliationRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def upsert_result(self, result: ReconciliationResult) -> None:
        with self._session_factory() as session:
            row = session.execute(
                select(ReconciliationResultRow).where(
                    ReconciliationResultRow.order_code == result.order_code,
                    ReconciliationResultRow.lt_code == result.lt_code,
                    ReconciliationResultRow.leg_id == result.leg_id,
                )
            ).scalar_one_or_none()
            if row is None:
                row = ReconciliationResultRow(
                    order_code=result.order_code,
                    lt_code=result.lt_code,
                    leg_id=result.leg_id,
                )
                session.add(row)

            row.to_code = result.to_code
            row.cargo_type = result.cargo_type.value
            row.to_subtype = result.to_subtype.value
            row.sender_location = result.sender_location
            row.dispatched_at = result.dispatched_at
            row.leg_actual_arrival = result.leg_actual_arrival
            row.status = result.status.value
            row.detected_at = result.detected_at
            row.resolved_at = result.resolved_at
            row.updated_at = datetime.now(timezone.utc)
            session.commit()

    def get_open_results(self) -> list[ReconciliationResult]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(ReconciliationResultRow).where(
                        ReconciliationResultRow.status.in_(OPEN_STATUSES)
                    )
                )
                .scalars()
                .all()
            )
            return [_row_to_result(r) for r in rows]

    def upsert_checkpoint(self, leg: LinehaulLeg, now: datetime) -> None:
        with self._session_factory() as session:
            row = session.get(LegCheckpointRow, (leg.lt_code, leg.leg_id))
            if row is None:
                session.add(
                    LegCheckpointRow(
                        lt_code=leg.lt_code,
                        leg_id=leg.leg_id,
                        actual_arrival=leg.actual_arrival,
                        first_checked_at=now,
                        last_checked_at=now,
                    )
                )
            else:
                row.last_checked_at = now
            session.commit()

    def get_last_scan_checkpoint(self) -> datetime | None:
        with self._session_factory() as session:
            row = session.get(ScanStateRow, _LAST_SCAN_KEY)
            if row is None:
                return None
            return datetime.fromisoformat(row.value)

    def set_last_scan_checkpoint(self, value: datetime) -> None:
        with self._session_factory() as session:
            row = session.get(ScanStateRow, _LAST_SCAN_KEY)
            if row is None:
                session.add(ScanStateRow(key=_LAST_SCAN_KEY, value=value.isoformat()))
            else:
                row.value = value.isoformat()
            session.commit()


def _row_to_result(row: ReconciliationResultRow) -> ReconciliationResult:
    return ReconciliationResult(
        order_code=row.order_code,
        lt_code=row.lt_code,
        leg_id=row.leg_id,
        to_code=row.to_code,
        cargo_type=CargoType(row.cargo_type),
        to_subtype=TOSubType(row.to_subtype),
        sender_location=row.sender_location,
        dispatched_at=row.dispatched_at,
        leg_actual_arrival=row.leg_actual_arrival,
        status=ReconciliationStatus(row.status),
        detected_at=row.detected_at,
        resolved_at=row.resolved_at,
    )
