"""Cấu hình bot, đọc từ biến môi trường (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Thiếu biến môi trường bắt buộc: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    api_base_url: str
    api_token: str
    bda_code: str

    db_path: str

    google_credentials_path: str | None
    google_spreadsheet_id: str | None
    google_worksheet_name: str

    poll_interval_seconds: int
    initial_lookback: timedelta
    grace_period: timedelta
    confirm_horizon: timedelta

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_base_url=_get("SOURCE_API_BASE_URL", required=True),
            api_token=_get("SOURCE_API_TOKEN", required=True),
            bda_code=_get("BDA_HUB_CODE", default="BDA"),
            db_path=_get("SQLITE_DB_PATH", default="data/reconciliation.db"),
            google_credentials_path=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or None,
            google_spreadsheet_id=os.environ.get("GOOGLE_SPREADSHEET_ID") or None,
            google_worksheet_name=_get("GOOGLE_WORKSHEET_NAME", default="MissingOrders"),
            poll_interval_seconds=int(_get("POLL_INTERVAL_SECONDS", default="120")),
            initial_lookback=timedelta(hours=int(_get("INITIAL_LOOKBACK_HOURS", default="6"))),
            grace_period=timedelta(minutes=int(_get("GRACE_PERIOD_MINUTES", default="60"))),
            confirm_horizon=timedelta(hours=int(_get("CONFIRM_HORIZON_HOURS", default="24"))),
        )
