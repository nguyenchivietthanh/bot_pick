"""Vòng lặp chạy 24/7 kiểu 'cuốn chiếu':

- Mỗi vòng: lấy các chặng LT mới đến BDA kể từ checkpoint lần trước, đối soát
  expected vs actual, ghi kết quả (DB + Sheet).
- Đồng thời, quét lại các kết quả đang "mở" (PENDING_GRACE/MISSING) để:
    + tự động resolve nếu đơn được scan nhận muộn (RESOLVED_LATE), hoặc
    + chuyển PENDING_GRACE -> MISSING khi hết thời gian ân hạn, hoặc
    + chốt CONFIRMED_MISSING khi quá mốc xác nhận cuối cùng.
  Nhờ vậy dữ liệu "cuốn" dần về trạng thái ổn định mà không cần xử lý lại
  toàn bộ lịch sử mỗi vòng.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from .api_client import SourceAPIClient
from .config import Settings
from .domain import LinehaulLeg, ReconciliationResult
from .reconciliation import advance_result_status, build_missing_results
from .sheets.writer import SheetsWriter
from .storage.repository import ReconciliationRepository

logger = logging.getLogger(__name__)


class ReconciliationPoller:
    def __init__(
        self,
        settings: Settings,
        api_client: SourceAPIClient,
        repository: ReconciliationRepository,
        sheets_writer: SheetsWriter | None,
    ):
        self.settings = settings
        self.api_client = api_client
        self.repository = repository
        self.sheets_writer = sheets_writer

    def run_forever(self) -> None:
        logger.info("Bắt đầu vòng lặp đối soát 24/7 (cuốn chiếu)...")
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception(
                    "Lỗi trong 1 vòng đối soát, thử lại sau %ss",
                    self.settings.poll_interval_seconds,
                )
            time.sleep(self.settings.poll_interval_seconds)

    def run_once(self) -> None:
        now = datetime.now(timezone.utc)
        since = self.repository.get_last_scan_checkpoint() or (
            now - self.settings.initial_lookback
        )

        legs = self.api_client.get_arrived_legs(since=since, destination_code=self.settings.bda_code)
        logger.info("Tìm thấy %d chặng LT mới đến BDA cần xử lý", len(legs))
        for leg in legs:
            self._process_new_leg(leg, now)

        self._recheck_open_results(now)

        self.repository.set_last_scan_checkpoint(now)

    def _process_new_leg(self, leg: LinehaulLeg, now: datetime) -> None:
        if leg.actual_arrival is None:
            return  # chặng chưa thực sự đến BDA, bỏ qua vòng này

        # Nguồn dữ liệu (FMS Pending Inbound) đã tự trả về đúng phần "chưa tới
        # BDA" - không cần tự diff expected vs actual nữa.
        missing = self.api_client.get_pending_orders(leg.lt_code, leg.leg_id)

        results = build_missing_results(
            missing, leg.actual_arrival, now, self.settings.grace_period
        )
        for r in results:
            self.repository.upsert_result(r)
        self.repository.upsert_checkpoint(leg, now)

        if results:
            logger.info("LT=%s leg=%s: %d đơn đang thiếu tại BDA", leg.lt_code, leg.leg_id, len(missing))
        self._sync_sheet(results)

    def _recheck_open_results(self, now: datetime) -> None:
        open_results = self.repository.get_open_results()
        if not open_results:
            return

        by_leg: dict[tuple[str, str], list[ReconciliationResult]] = {}
        for r in open_results:
            by_leg.setdefault((r.lt_code, r.leg_id), []).append(r)

        changed: list[ReconciliationResult] = []
        for (lt_code, leg_id), results in by_leg.items():
            still_pending_codes = {o.order_code for o in self.api_client.get_pending_orders(lt_code, leg_id)}
            # "received" = đơn đang theo dõi mà giờ không còn nằm trong danh
            # sách Pending Inbound nữa -> FMS đã ghi nhận tới BDA.
            received_codes = {r.order_code for r in results if r.order_code not in still_pending_codes}
            for r in results:
                if advance_result_status(
                    r,
                    received_codes,
                    now,
                    self.settings.grace_period,
                    self.settings.confirm_horizon,
                ):
                    self.repository.upsert_result(r)
                    changed.append(r)

        if changed:
            logger.info("Cập nhật trạng thái %d đơn đang theo dõi", len(changed))
        self._sync_sheet(changed)

    def _sync_sheet(self, results: list[ReconciliationResult]) -> None:
        if self.sheets_writer and results:
            self.sheets_writer.upsert_results(results)
