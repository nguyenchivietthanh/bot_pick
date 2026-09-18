"""Helper thuần port từ bot_deli_ver1 (normalize field, đọc field JSON linh hoạt)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def first_value(data: dict | None, keys: list[str]):
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def normalize_text(value) -> str:
    return str(value or "").strip().lower()


def to_int(value, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def extract_order_id(row: dict) -> str | None:
    """Port từ bot_deli_ver1 export_LT_unit_to_BQ.extract_order_id."""
    return first_value(
        row,
        [
            "fleet_order_id",
            "spx_tracking_number",
            "tracking_number",
            "shipment_id",
            "order_id",
            "order_number",
            "scan_number",
        ],
    )


def parse_fms_timestamp(value) -> datetime | None:
    """Port từ bot_deli_ver1 timestamp_to_datetime, trả về datetime UTC-aware."""
    if value in (None, "", 0, "0", "-"):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000
        return datetime.fromtimestamp(number, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        pass
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def to_epoch_seconds(dt: datetime) -> int:
    return int(dt.timestamp())
