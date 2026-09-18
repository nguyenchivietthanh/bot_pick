"""Cấu hình bot, đọc từ biến môi trường (.env).

Lưu ý: các biến điều khiển Chrome/FMS session (BOT_DELI_CHROME_*,
BOT_DELI_BROWSER_*) được `src/fms/browser_fetch.py` tự đọc thẳng từ
`os.environ`, không đi qua `Settings` ở đây — xem `.env.example`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta

from dotenv import load_dotenv

from .fms.constants import BDA_STATION_ID, BDA_STATION_NAME

load_dotenv()


def _get(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Thiếu biến môi trường bắt buộc: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    # Tên trạm BDA trong FMS (dùng để chọn role Chrome đăng nhập + so khớp
    # trip_station trả về từ API) và id trạm (dùng để lọc trip theo
    # middle_station). Mặc định lấy theo giá trị đã xác nhận từ bot_deli_ver1.
    bda_code: str
    bda_station_id: str

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
            bda_code=_get("BDA_HUB_CODE", default=BDA_STATION_NAME),
            bda_station_id=_get("BDA_STATION_ID", default=BDA_STATION_ID),
            db_path=_get("SQLITE_DB_PATH", default="data/reconciliation.db"),
            google_credentials_path=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or None,
            google_spreadsheet_id=os.environ.get("GOOGLE_SPREADSHEET_ID") or None,
            google_worksheet_name=_get("GOOGLE_WORKSHEET_NAME", default="MissingOrders"),
            poll_interval_seconds=int(_get("POLL_INTERVAL_SECONDS", default="120")),
            initial_lookback=timedelta(hours=int(_get("INITIAL_LOOKBACK_HOURS", default="6"))),
            grace_period=timedelta(minutes=int(_get("GRACE_PERIOD_MINUTES", default="60"))),
            confirm_horizon=timedelta(hours=int(_get("CONFIRM_HORIZON_HOURS", default="24"))),
        )
