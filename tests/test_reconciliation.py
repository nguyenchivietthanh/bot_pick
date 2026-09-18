from datetime import datetime, timedelta, timezone

from src.domain import (
    ActualReceipt,
    CargoType,
    ExpectedOrder,
    ReconciliationResult,
    ReconciliationStatus,
    TOSubType,
)
from src.reconciliation import advance_result_status, build_missing_results, diff_orders


def _expected(order_code: str) -> ExpectedOrder:
    return ExpectedOrder(
        order_code=order_code,
        lt_code="LT001",
        leg_id="LEG01",
        to_code="TO001",
        cargo_type=CargoType.TO_TRANSIT,
        to_subtype=TOSubType.MULTI,
        sender_location="HN_HUB",
        dispatched_at=datetime(2026, 9, 18, 1, 0, tzinfo=timezone.utc),
    )


def test_diff_orders_finds_missing():
    expected = [_expected("ORD1"), _expected("ORD2"), _expected("ORD3")]
    actual = [
        ActualReceipt(
            order_code="ORD2",
            lt_code="LT001",
            leg_id="LEG01",
            received_at=datetime(2026, 9, 18, 3, 0, tzinfo=timezone.utc),
        )
    ]

    missing = diff_orders(expected, actual)

    assert {o.order_code for o in missing} == {"ORD1", "ORD3"}


def test_diff_orders_no_missing_when_all_received():
    expected = [_expected("ORD1")]
    actual = [
        ActualReceipt(
            order_code="ORD1",
            lt_code="LT001",
            leg_id="LEG01",
            received_at=datetime(2026, 9, 18, 3, 0, tzinfo=timezone.utc),
        )
    ]

    assert diff_orders(expected, actual) == []


def test_build_missing_results_pending_within_grace():
    missing = [_expected("ORD1")]
    leg_arrival = datetime(2026, 9, 18, 3, 0, tzinfo=timezone.utc)
    now = leg_arrival + timedelta(minutes=10)

    results = build_missing_results(missing, leg_arrival, now, grace_period=timedelta(minutes=60))

    assert results[0].status == ReconciliationStatus.PENDING_GRACE


def test_build_missing_results_missing_after_grace():
    missing = [_expected("ORD1")]
    leg_arrival = datetime(2026, 9, 18, 3, 0, tzinfo=timezone.utc)
    now = leg_arrival + timedelta(minutes=90)

    results = build_missing_results(missing, leg_arrival, now, grace_period=timedelta(minutes=60))

    assert results[0].status == ReconciliationStatus.MISSING


def _result(status: ReconciliationStatus, leg_arrival: datetime) -> ReconciliationResult:
    return ReconciliationResult(
        order_code="ORD1",
        lt_code="LT001",
        leg_id="LEG01",
        to_code="TO001",
        cargo_type=CargoType.TO_TRANSIT,
        to_subtype=TOSubType.MULTI,
        sender_location="HN_HUB",
        dispatched_at=leg_arrival - timedelta(hours=1),
        leg_actual_arrival=leg_arrival,
        status=status,
        detected_at=leg_arrival,
    )


def test_advance_result_status_resolves_late_when_scanned():
    leg_arrival = datetime(2026, 9, 18, 3, 0, tzinfo=timezone.utc)
    result = _result(ReconciliationStatus.MISSING, leg_arrival)
    now = leg_arrival + timedelta(hours=2)

    changed = advance_result_status(
        result,
        received_codes={"ORD1"},
        now=now,
        grace_period=timedelta(minutes=60),
        confirm_horizon=timedelta(hours=24),
    )

    assert changed is True
    assert result.status == ReconciliationStatus.RESOLVED_LATE
    assert result.resolved_at == now


def test_advance_result_status_confirms_missing_after_horizon():
    leg_arrival = datetime(2026, 9, 18, 3, 0, tzinfo=timezone.utc)
    result = _result(ReconciliationStatus.MISSING, leg_arrival)
    now = leg_arrival + timedelta(hours=25)

    changed = advance_result_status(
        result,
        received_codes=set(),
        now=now,
        grace_period=timedelta(minutes=60),
        confirm_horizon=timedelta(hours=24),
    )

    assert changed is True
    assert result.status == ReconciliationStatus.CONFIRMED_MISSING


def test_advance_result_status_no_change_when_still_pending():
    leg_arrival = datetime(2026, 9, 18, 3, 0, tzinfo=timezone.utc)
    result = _result(ReconciliationStatus.PENDING_GRACE, leg_arrival)
    now = leg_arrival + timedelta(minutes=5)

    changed = advance_result_status(
        result,
        received_codes=set(),
        now=now,
        grace_period=timedelta(minutes=60),
        confirm_horizon=timedelta(hours=24),
    )

    assert changed is False
    assert result.status == ReconciliationStatus.PENDING_GRACE
