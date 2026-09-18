"""Domain model cho bài toán đối soát đơn missing giữa các điểm gửi và BDA.

Thuật ngữ nghiệp vụ:
- LT (LinehaulTrip): 1 chuyến xe vận chuyển, có thể có nhiều chặng (leg).
  Bot chỉ xử lý các chặng có destination_code == BDA.
- TO (Transfer Order / đơn trung chuyển): 1 gói chứa 1 hoặc nhiều đơn hàng.
  TO 1 đơn = TOSubType.SINGLE, TO nhiều đơn = TOSubType.MULTI.
- Bulky: loại hàng không đóng theo TO, so khớp trực tiếp theo order_code.
- "Expected" = đơn mà điểm gửi xác nhận đã gửi đi trên 1 chặng LT cụ thể.
- "Actual" = đơn đã scan nhận thực tế tại BDA cho chặng LT đó.
- "Missing" = có trong Expected nhưng không có trong Actual.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class CargoType(str, Enum):
    BULKY = "BULKY"
    TO_TRANSIT = "TO_TRANSIT"
    TO_SORTING = "TO_SORTING"


class TOSubType(str, Enum):
    SINGLE = "SINGLE"  # TO 1 đơn
    MULTI = "MULTI"  # TO nhiều đơn (>1 đơn trong TO)
    NOT_APPLICABLE = "NOT_APPLICABLE"  # Bulky không đóng theo TO


class ReconciliationStatus(str, Enum):
    PENDING_GRACE = "PENDING_GRACE"  # mới phát hiện thiếu, còn trong thời gian ân hạn (dỡ hàng/scan trễ)
    MISSING = "MISSING"  # hết thời gian ân hạn, vẫn chưa thấy tại BDA -> cần đối soát
    RESOLVED_LATE = "RESOLVED_LATE"  # từng bị đánh dấu thiếu, sau đó scan nhận muộn tại BDA
    CONFIRMED_MISSING = "CONFIRMED_MISSING"  # quá mốc xác nhận cuối cùng, chốt thiếu để xử lý nghiệp vụ


@dataclass(frozen=True)
class LinehaulLeg:
    """1 chặng của 1 LT. Chỉ xử lý khi destination_code == mã BDA."""

    lt_code: str
    leg_id: str
    origin_code: str
    destination_code: str
    scheduled_arrival: datetime | None
    actual_arrival: datetime | None  # None nếu chặng chưa thực sự đến BDA


@dataclass(frozen=True)
class ExpectedOrder:
    """Đơn mà điểm gửi xác nhận đã gửi đi trên 1 chặng LT cụ thể."""

    order_code: str
    lt_code: str
    leg_id: str
    to_code: str | None
    cargo_type: CargoType
    to_subtype: TOSubType
    sender_location: str
    dispatched_at: datetime


@dataclass(frozen=True)
class ActualReceipt:
    """Đơn đã scan nhận thực tế tại BDA cho 1 chặng LT."""

    order_code: str
    lt_code: str
    leg_id: str
    received_at: datetime


@dataclass
class ReconciliationResult:
    """1 dòng kết quả đối soát cho 1 đơn trên 1 chặng LT."""

    order_code: str
    lt_code: str
    leg_id: str
    to_code: str | None
    cargo_type: CargoType
    to_subtype: TOSubType
    sender_location: str
    dispatched_at: datetime
    leg_actual_arrival: datetime
    status: ReconciliationStatus
    detected_at: datetime
    resolved_at: datetime | None = None
