"""Client lấy dữ liệu LT/TO/đơn từ API nội bộ công ty.

`SourceAPIClient` là interface trừu tượng — toàn bộ phần còn lại của bot chỉ
phụ thuộc vào interface này, không phụ thuộc chi tiết API thật. Điều này giúp:
  - Unit test dễ dàng bằng fake/mock implementation.
  - Khi có API docs/response mẫu thật, chỉ cần sửa `HttpInternalAPIClient`
    (đặc biệt 3 hàm `_parse_*`) mà không đụng vào logic đối soát/lưu trữ.

QUAN TRỌNG: endpoint path và cách map field JSON trong `HttpInternalAPIClient`
hiện là GIẢ ĐỊNH dựa trên mô tả nghiệp vụ, CẦN được chỉnh lại theo API thật
(Swagger/Postman collection/response mẫu) trước khi chạy production.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime

import requests

from .domain import ActualReceipt, CargoType, ExpectedOrder, LinehaulLeg, TOSubType

logger = logging.getLogger(__name__)


class SourceAPIClient(ABC):
    """Interface nguồn dữ liệu LT/TO/đơn."""

    @abstractmethod
    def get_arrived_legs(self, since: datetime, destination_code: str) -> list[LinehaulLeg]:
        """Danh sách chặng LT có destination_code == BDA, đã cập nhật kể từ `since`."""

    @abstractmethod
    def get_expected_orders(self, lt_code: str, leg_id: str) -> list[ExpectedOrder]:
        """Manifest đơn mà điểm gửi xác nhận đã gửi đi cho 1 chặng LT."""

    @abstractmethod
    def get_actual_received_orders(self, lt_code: str, leg_id: str) -> list[ActualReceipt]:
        """Đơn đã scan nhận thực tế tại BDA cho 1 chặng LT."""


class HttpInternalAPIClient(SourceAPIClient):
    """Cài đặt thật gọi API nội bộ công ty qua HTTP."""

    def __init__(self, base_url: str, token: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ---- endpoints (đường dẫn GIẢ ĐỊNH, sửa theo API thật) ----

    def get_arrived_legs(self, since: datetime, destination_code: str) -> list[LinehaulLeg]:
        data = self._get(
            "/linehaul-trips/legs",
            params={
                "destination_code": destination_code,
                "updated_since": since.isoformat(),
                "status": "ARRIVED",
            },
        )
        return [self._parse_leg(item) for item in data.get("items", [])]

    def get_expected_orders(self, lt_code: str, leg_id: str) -> list[ExpectedOrder]:
        data = self._get(f"/linehaul-trips/{lt_code}/legs/{leg_id}/manifest")
        return [self._parse_expected_order(item, lt_code, leg_id) for item in data.get("items", [])]

    def get_actual_received_orders(self, lt_code: str, leg_id: str) -> list[ActualReceipt]:
        data = self._get(f"/linehaul-trips/{lt_code}/legs/{leg_id}/bda-scans")
        return [self._parse_actual_receipt(item, lt_code, leg_id) for item in data.get("items", [])]

    # ---- mapping JSON -> domain model (CHỖ DUY NHẤT cần sửa khi có API thật) ----

    def _parse_leg(self, item: dict) -> LinehaulLeg:
        return LinehaulLeg(
            lt_code=item["lt_code"],
            leg_id=item["leg_id"],
            origin_code=item["origin_code"],
            destination_code=item["destination_code"],
            scheduled_arrival=_parse_dt(item.get("scheduled_arrival")),
            actual_arrival=_parse_dt(item.get("actual_arrival")),
        )

    def _parse_expected_order(self, item: dict, lt_code: str, leg_id: str) -> ExpectedOrder:
        return ExpectedOrder(
            order_code=item["order_code"],
            lt_code=lt_code,
            leg_id=leg_id,
            to_code=item.get("to_code"),
            cargo_type=CargoType(item["cargo_type"]),
            to_subtype=TOSubType(item.get("to_subtype", TOSubType.NOT_APPLICABLE.value)),
            sender_location=item["sender_location"],
            dispatched_at=_parse_dt(item["dispatched_at"]),
        )

    def _parse_actual_receipt(self, item: dict, lt_code: str, leg_id: str) -> ActualReceipt:
        return ActualReceipt(
            order_code=item["order_code"],
            lt_code=lt_code,
            leg_id=leg_id,
            received_at=_parse_dt(item["received_at"]),
        )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
