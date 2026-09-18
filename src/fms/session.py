"""FMS session wrapper: gọi API qua Chrome đã đăng nhập + phân trang.

Port lại `FmsSession`/`fetch_list` của bot_deli_ver1
(BOT-Deli_BDA_export_LT_unit_to_BQ.py), bỏ nhánh `requests` thô cũ vì
`browser_fetch.request_json` đã là đường đi chính thức (xác nhận qua
`get_fms_headers()` trong bot_deli_ver1 chỉ trả về marker
`{"__browser_fetch_role": soc_code}`).
"""

from __future__ import annotations

import math

from . import browser_fetch
from .constants import PAGE_COUNT


class FmsSession:
    def __init__(self, role: str):
        self.role = role

    def request_json(
        self,
        method: str,
        url: str,
        payload: dict | None = None,
        label: str = "",
        max_retries: int | None = None,
        fail_soft: bool = True,
    ) -> dict | None:
        try:
            return browser_fetch.request_json(
                self.role, method, url, payload=payload or {}, label=label, max_retries=max_retries
            )
        except browser_fetch.BrowserNoRecordError:
            return None
        except browser_fetch.BrowserFetchError:
            if fail_soft:
                return None
            raise

    def fetch_list(
        self,
        url_template: str,
        payload: dict | None = None,
        count: int = PAGE_COUNT,
        label: str = "",
    ) -> tuple[list[dict], int]:
        """Gọi `url_template` (chứa `{page}`/`{count}`) và gộp `data.list[]` qua các trang."""
        all_rows: list[dict] = []
        page = 1
        total = 0
        total_pages = 0

        while True:
            url = url_template.format(page=page, count=count)
            data = self.request_json(
                "GET",
                url,
                payload=payload or {},
                label=f"{label} | page {page}" if label else f"page {page}",
            )
            if data is None:
                break

            data_node = data.get("data") or {}
            if page == 1:
                total = int(data_node.get("total") or 0)
                total_pages = math.ceil(total / count) if total > 0 else 0
                if total == 0:
                    return all_rows, 0

            rows = data_node.get("list") or []
            if not rows:
                break

            all_rows.extend(rows)
            if page >= total_pages:
                break
            page += 1

        return all_rows, total
