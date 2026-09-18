"""Logic đối soát thuần (pure functions) — không phụ thuộc I/O, dễ test.

Quy tắc chốt trạng thái:
- Ngay khi phát hiện thiếu: PENDING_GRACE (cho phép trễ do thời gian dỡ hàng/scan).
- Sau grace_period kể từ giờ đến thực tế của chặng mà vẫn thiếu: MISSING.
- Nếu sau đó xuất hiện trong actual receipts: RESOLVED_LATE.
- Nếu quá confirm_horizon vẫn không thấy: CONFIRMED_MISSING (chốt để xử lý nghiệp vụ).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .domain import ActualReceipt, ExpectedOrder, ReconciliationResult, ReconciliationStatus


def diff_orders(
    expected: list[ExpectedOrder], actual: list[ActualReceipt]
) -> list[ExpectedOrder]:
    """Trả về các đơn có trong expected nhưng không có trong actual (theo order_code)."""
    received_codes = {a.order_code for a in actual}
    return [e for e in expected if e.order_code not in received_codes]


def build_missing_results(
    missing: list[ExpectedOrder],
    leg_actual_arrival: datetime,
    now: datetime,
    grace_period: timedelta,
) -> list[ReconciliationResult]:
    """Tạo các ReconciliationResult mới cho danh sách đơn thiếu vừa phát hiện."""
    status = (
        ReconciliationStatus.PENDING_GRACE
        if now - leg_actual_arrival < grace_period
        else ReconciliationStatus.MISSING
    )
    return [
        ReconciliationResult(
            order_code=o.order_code,
            lt_code=o.lt_code,
            leg_id=o.leg_id,
            to_code=o.to_code,
            cargo_type=o.cargo_type,
            to_subtype=o.to_subtype,
            sender_location=o.sender_location,
            dispatched_at=o.dispatched_at,
            leg_actual_arrival=leg_actual_arrival,
            status=status,
            detected_at=now,
        )
        for o in missing
    ]


def advance_result_status(
    result: ReconciliationResult,
    received_codes: set[str],
    now: datetime,
    grace_period: timedelta,
    confirm_horizon: timedelta,
) -> bool:
    """Cập nhật trạng thái của 1 result đang mở (PENDING_GRACE/MISSING) tại chỗ.

    Trả về True nếu trạng thái có thay đổi (cần ghi lại DB/Sheet).
    """
    if result.order_code in received_codes:
        result.status = ReconciliationStatus.RESOLVED_LATE
        result.resolved_at = now
        return True

    age = now - result.leg_actual_arrival
    if age >= confirm_horizon:
        if result.status != ReconciliationStatus.CONFIRMED_MISSING:
            result.status = ReconciliationStatus.CONFIRMED_MISSING
            return True
        return False

    if age >= grace_period:
        if result.status != ReconciliationStatus.MISSING:
            result.status = ReconciliationStatus.MISSING
            return True
        return False

    return False
