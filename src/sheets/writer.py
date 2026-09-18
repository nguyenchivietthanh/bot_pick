"""Đồng bộ kết quả đối soát sang Google Sheet.

Lưu ý khả năng mở rộng: `upsert_results` đọc toàn bộ sheet mỗi lần để dò
key trùng — phù hợp cho báo cáo vài nghìn dòng. Nếu số dòng lớn hơn nhiều,
cân nhắc chuyển sang giữ index key->row trong bộ nhớ/DB thay vì đọc lại sheet.
"""

from __future__ import annotations

import logging

import gspread
from google.oauth2.service_account import Credentials

from ..domain import ReconciliationResult

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_HEADERS = [
    "order_code",
    "lt_code",
    "leg_id",
    "to_code",
    "cargo_type",
    "to_subtype",
    "sender_location",
    "dispatched_at",
    "leg_actual_arrival",
    "status",
    "detected_at",
    "resolved_at",
]


class SheetsWriter:
    def __init__(self, credentials_path: str, spreadsheet_id: str, worksheet_name: str):
        creds = Credentials.from_service_account_file(credentials_path, scopes=_SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(spreadsheet_id)
        try:
            self.worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            self.worksheet = spreadsheet.add_worksheet(
                worksheet_name, rows=1000, cols=len(_HEADERS)
            )
            self.worksheet.append_row(_HEADERS)

    def upsert_results(self, results: list[ReconciliationResult]) -> None:
        if not results:
            return

        existing = self.worksheet.get_all_values()
        key_to_row: dict[tuple[str, str, str], int] = {}
        if existing:
            for idx, row in enumerate(existing[1:], start=2):  # bỏ header, sheet 1-indexed
                if len(row) >= 3:
                    key_to_row[(row[0], row[1], row[2])] = idx

        updates: list[tuple[int, list[str]]] = []
        appends: list[list[str]] = []
        for r in results:
            key = (r.order_code, r.lt_code, r.leg_id)
            values = _to_row(r)
            if key in key_to_row:
                updates.append((key_to_row[key], values))
            else:
                appends.append(values)

        last_col = gspread.utils.rowcol_to_a1(1, len(_HEADERS))[:-1]
        for row_idx, values in updates:
            self.worksheet.update(f"A{row_idx}:{last_col}{row_idx}", [values])
        if appends:
            self.worksheet.append_rows(appends)

        logger.info("Đồng bộ Google Sheet: %d cập nhật, %d dòng mới", len(updates), len(appends))


def _to_row(r: ReconciliationResult) -> list[str]:
    return [
        r.order_code,
        r.lt_code,
        r.leg_id,
        r.to_code or "",
        r.cargo_type.value,
        r.to_subtype.value,
        r.sender_location,
        r.dispatched_at.isoformat() if r.dispatched_at else "",
        r.leg_actual_arrival.isoformat() if r.leg_actual_arrival else "",
        r.status.value,
        r.detected_at.isoformat() if r.detected_at else "",
        r.resolved_at.isoformat() if r.resolved_at else "",
    ]
