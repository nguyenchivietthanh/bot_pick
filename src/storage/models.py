"""SQLAlchemy ORM models cho SQLite (có thể đổi sang Postgres/MySQL sau này
bằng cách chỉ đổi connection string trong `db.py`)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ReconciliationResultRow(Base):
    """1 dòng = 1 đơn thiếu (hoặc đã resolve) trên 1 chặng LT."""

    __tablename__ = "reconciliation_results"
    __table_args__ = (
        UniqueConstraint("order_code", "lt_code", "leg_id", name="uq_result_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_code: Mapped[str] = mapped_column(String(64), index=True)
    lt_code: Mapped[str] = mapped_column(String(64), index=True)
    leg_id: Mapped[str] = mapped_column(String(64))
    to_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cargo_type: Mapped[str] = mapped_column(String(32))
    to_subtype: Mapped[str] = mapped_column(String(32))
    sender_location: Mapped[str] = mapped_column(String(128))
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    leg_actual_arrival: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LegCheckpointRow(Base):
    """Theo dõi chặng LT nào đã được xử lý — hỗ trợ chạy 'cuốn chiếu' 24/7."""

    __tablename__ = "leg_checkpoints"

    lt_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    leg_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actual_arrival: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScanStateRow(Base):
    """Key-value đơn giản để lưu checkpoint thời gian quét gần nhất."""

    __tablename__ = "scan_state"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[str] = mapped_column(String(64))
