"""Interface nguồn dữ liệu LT/TO/đơn.

Cài đặt thật: `src/fms/client.py` (`FmsInternalAPIClient`), gọi thẳng vào hệ
FMS nội bộ (spx.shopee.vn) qua Chrome đã đăng nhập sẵn — xem `src/fms/`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from .domain import ExpectedOrder, LinehaulLeg


class SourceAPIClient(ABC):
    """Interface nguồn dữ liệu LT/TO/đơn."""

    @abstractmethod
    def get_arrived_legs(self, since: datetime, destination_code: str) -> list[LinehaulLeg]:
        """Danh sách chặng LT có destination_code == BDA, cập nhật kể từ `since`."""

    @abstractmethod
    def get_pending_orders(self, lt_code: str, leg_id: str) -> list[ExpectedOrder]:
        """Đơn hiện CHƯA được ghi nhận đã tới BDA cho 1 chặng LT cụ thể.

        Nguồn dữ liệu tự chịu trách nhiệm diff "đã gửi" vs "đã nhận" (với FMS,
        đây chính là danh sách "Pending Inbound" — FMS đã tính sẵn phần chưa
        unload tại trạm, khỏi cần tự so khớp 2 tập expected/actual).
        """
