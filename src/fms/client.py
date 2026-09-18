"""FmsInternalAPIClient — cài đặt SourceAPIClient thật, gọi FMS nội bộ.

Đây là bản "soi gương" của nguyenchivietthanh/bot_deli_ver1: bot đó coi BDA là
điểm GỬI (lọc trip theo `first_station=<id BDA>`, rồi kiểm tra "Pending
Inbound" ở các điểm NHẬN khác). Bot này coi BDA là điểm NHẬN: cần các chặng LT
có BDA là điểm đến, rồi kiểm tra "Pending Inbound" NGAY TẠI BDA — tức các
TO/đơn nơi gửi đã cho lên xe nhưng chưa được scan/unload tại BDA.

ĐÃ XÁC NHẬN trực tiếp từ source bot_deli_ver1 (không đoán):
  - Tên trạm BDA trong FMS: "BD B Mega SOC" (SOC_CODE), id trạm: "4110".
  - `trip/history/loading/list` (LT đã Ended) và `trip/loading/list` (LT đang
    Handover) nhận `type=pending&unloaded_sequence_number=<n>
    &actual_unloaded_sequence_number=0` để trả về đúng phần CHƯA được unload
    tại sequence `n` của trip — đây chính là tập "missing" cần tìm, do FMS đã
    tự diff sẵn (không cần tự so khớp expected vs actual nữa).
    Nguồn: bot_deli_ver1 BOT-Deli_BDA_check_bulky_pending.py
    `fetch_pending_loading_list()`.
  - `general_to/detail/search?to_number=...` mở rộng 1 TO ra sender/receiver/
    order_count/danh sách đơn con. `order_count == 1` -> xử lý như BULKY (TO 1
    đơn); `order_count > 1` -> TO_SORTING (TO nhiều đơn).
    Nguồn: bot_deli_ver1 BOT-Deli_BDA_export_LT_unit_to_BQ.py `fetch_to_detail()`.
  - `trip/history/detail` / `trip/detail` trả `data.trip_station[]`, mỗi trạm
    có `station_no`/`ata`/`eta`.

CHƯA XÁC NHẬN — cần kiểm chứng với phiên FMS thật trước khi tin tưởng hoàn
toàn (xem README mục TODO):
  - Tham số lọc trip theo "có BDA là 1 trạm trên hành trình" khi gọi
    `trip/history/list`/`trip/list`. bot_deli_ver1 chỉ từng lọc theo GỐC
    (`first_station`). Ở đây dùng `middle_station=<id BDA>` — tham số này CÓ
    THẬT trong source (`first_station=2490&middle_station=4110` ở
    bot_deli_ver1 arrived_LT.py) nhưng chỉ được xác nhận dùng KÈM
    `first_station`, chưa xác nhận dùng ĐỘC LẬP có lọc đúng "mọi trip đi qua
    trạm này" hay không, và chưa xác nhận `trip/list` (Handover) có chấp nhận
    tham số này giống `trip/history/list` hay không.
    Để AN TOÀN (không lọc sai mà không biết), sau khi lấy danh sách trip theo
    filter trên, code vẫn LUÔN xác nhận lại bằng cách gọi trip detail và tự
    tìm trạm BDA trong `trip_station[]` phía client — filter server-side chỉ
    là tối ưu, không phải nguồn sự thật.
  - `scan_time` của 1 dòng Pending Inbound được dùng tạm làm `dispatched_at`
    (thời điểm điểm gửi xác nhận gửi đi) — cần xác nhận đây đúng là thời điểm
    scan tại điểm GỬI, không phải 1 mốc thời gian khác.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..api_client import SourceAPIClient
from ..domain import CargoType, ExpectedOrder, LinehaulLeg, TOSubType
from .constants import (
    BDA_STATION_ID,
    BDA_STATION_NAME,
    GENERAL_TO_DETAIL_URL,
    PAGE_COUNT,
    TRIP_DETAIL_URL,
    TRIP_HISTORY_DETAIL_URL,
    TRIP_HISTORY_LIST_URL,
    TRIP_HISTORY_LOADING_LIST_URL,
    TRIP_LIST_URL,
    TRIP_LOADING_LIST_URL,
    TRIP_STATION_STATUS_ENDED,
)
from .session import FmsSession
from .utils import extract_order_id, first_value, normalize_text, parse_fms_timestamp, to_epoch_seconds, to_int

logger = logging.getLogger(__name__)

# Pending Inbound chỉ còn ý nghĩa trong vài ngày quanh lúc trip đến — quét lại
# quá xa vừa tốn request vừa không tìm thấy gì thêm (bot_deli_ver1 dùng cùng
# logic với PENDING_INBOUND_MAX_AGE_DAYS = 2).
TRIP_ID_RESCAN_WINDOW = timedelta(days=3)


class FmsInternalAPIClient(SourceAPIClient):
    def __init__(
        self,
        role: str = BDA_STATION_NAME,
        bda_station_name: str = BDA_STATION_NAME,
        bda_station_id: str = BDA_STATION_ID,
    ):
        self.session = FmsSession(role)
        self._bda_station_name = bda_station_name
        self._bda_station_id = bda_station_id
        self._trip_id_cache: dict[str, str] = {}

    # ---- SourceAPIClient ----

    def get_arrived_legs(self, since: datetime, destination_code: str) -> list[LinehaulLeg]:
        window_to = datetime.now(timezone.utc)
        trips = self._fetch_candidate_trips(since, window_to)

        legs: list[LinehaulLeg] = []
        for trip in trips:
            trip_id = first_value(trip, ["id", "trip_id"])
            trip_number = first_value(trip, ["trip_number", "lh_trip_number"])
            if not trip_id or not trip_number:
                continue
            trip_number = str(trip_number)
            self._trip_id_cache[trip_number] = str(trip_id)

            stations = self._fetch_trip_stations(trip_id, trip_number)
            stop = self._find_station_stop(stations, destination_code)
            if stop is None:
                continue

            origin_name = first_value(stations[0], ["station_name", "name", "station"]) if stations else ""
            legs.append(
                LinehaulLeg(
                    lt_code=trip_number,
                    leg_id=str(stop["sequence"]),
                    origin_code=origin_name or "",
                    destination_code=destination_code,
                    scheduled_arrival=stop.get("eta"),
                    actual_arrival=stop.get("ata"),
                )
            )
        return legs

    def get_pending_orders(self, lt_code: str, leg_id: str) -> list[ExpectedOrder]:
        trip_id = self._resolve_trip_id(lt_code)
        if trip_id is None:
            logger.warning("Khong tim lai duoc trip_id cho LT=%s, bo qua vong nay", lt_code)
            return []

        rows = self._fetch_pending_loading_list(trip_id, lt_code, leg_id)
        result: list[ExpectedOrder] = []
        for row in rows:
            result.extend(self._expand_pending_row(row, lt_code, leg_id))
        return result

    # ---- trip discovery ----

    def _fetch_candidate_trips(self, window_from: datetime, window_to: datetime) -> list[dict]:
        mtime_start = to_epoch_seconds(window_from)
        mtime_end = to_epoch_seconds(window_to)

        ended_url = (
            TRIP_HISTORY_LIST_URL
            + f"?pageno={{page}}&count={{count}}&trip_station_status={TRIP_STATION_STATUS_ENDED}"
            + f"&mtime={mtime_start},{mtime_end}&middle_station={self._bda_station_id}"
        )
        ended_rows, _ = self.session.fetch_list(ended_url, label="Ended LT toi BDA")

        live_url = (
            TRIP_LIST_URL
            + f"?pageno={{page}}&count={{count}}&query_type=2"
            + f"&mtime={mtime_start},{mtime_end}&middle_station={self._bda_station_id}"
        )
        live_rows, _ = self.session.fetch_list(live_url, label="Handover LT toi BDA")

        return ended_rows + live_rows

    def _fetch_trip_stations(self, trip_id, trip_number: str) -> list[dict]:
        for label, url in [
            (
                f"History trip detail - {trip_number}",
                f"{TRIP_HISTORY_DETAIL_URL}?trip_id={trip_id}&new_process_switch=false",
            ),
            (
                f"Live trip detail - {trip_number}",
                f"{TRIP_DETAIL_URL}?trip_id={trip_id}&new_process_switch=false",
            ),
        ]:
            data = self.session.request_json("GET", url, label=label)
            data_node = (data or {}).get("data") or {}
            stations = data_node.get("trip_station") or data_node.get("trip_stations")
            if stations:
                return stations
        return []

    def _find_station_stop(self, stations: list[dict], destination_code: str) -> dict | None:
        target = normalize_text(destination_code)
        for index, station in enumerate(stations, start=1):
            name = first_value(station, ["station_name", "name", "station"])
            if normalize_text(name) != target:
                continue
            sequence = to_int(first_value(station, ["station_no", "station_number"]), default=index)
            ata = parse_fms_timestamp(first_value(station, ["ata", "arrived_time", "actual_arrival_time"]))
            eta = parse_fms_timestamp(first_value(station, ["eta", "scheduled_arrival_time"]))
            return {"sequence": sequence, "ata": ata, "eta": eta}
        return None

    def _resolve_trip_id(self, lt_code: str) -> str | None:
        if lt_code in self._trip_id_cache:
            return self._trip_id_cache[lt_code]
        since = datetime.now(timezone.utc) - TRIP_ID_RESCAN_WINDOW
        self.get_arrived_legs(since=since, destination_code=self._bda_station_name)
        return self._trip_id_cache.get(lt_code)

    # ---- Pending Inbound tại BDA ----

    def _fetch_pending_loading_list(self, trip_id, trip_number: str, unloaded_sequence_number: str) -> list[dict]:
        url_suffix = (
            f"?trip_id={trip_id}&pageno={{page}}&count={{count}}"
            f"&unloaded_sequence_number={unloaded_sequence_number}"
            f"&actual_unloaded_sequence_number=0&type=pending"
        )
        for label, url_prefix in [
            (
                f"Pending inbound history - {trip_number} seq {unloaded_sequence_number}",
                TRIP_HISTORY_LOADING_LIST_URL,
            ),
            (
                f"Pending inbound live - {trip_number} seq {unloaded_sequence_number}",
                TRIP_LOADING_LIST_URL,
            ),
        ]:
            rows, total = self.session.fetch_list(url_prefix + url_suffix, label=label)
            if total > 0 or rows:
                return rows
        return []

    def _expand_pending_row(self, row: dict, lt_code: str, leg_id: str) -> list[ExpectedOrder]:
        scan_number = str(row.get("scan_number") or "").strip()
        to_number = str(row.get("to_number") or "").strip()
        dispatched_at = parse_fms_timestamp(row.get("scan_time")) or datetime.now(timezone.utc)
        fallback_sender = row.get("loaded_station_name") or ""

        if to_number or scan_number.startswith("TO"):
            return self._expand_to_row(to_number or scan_number, lt_code, leg_id, dispatched_at, fallback_sender)

        # Bulky trực tiếp (vd SPX...), không đóng theo TO.
        return [
            ExpectedOrder(
                order_code=scan_number,
                lt_code=lt_code,
                leg_id=leg_id,
                to_code=None,
                cargo_type=CargoType.BULKY,
                to_subtype=TOSubType.NOT_APPLICABLE,
                sender_location=fallback_sender,
                dispatched_at=dispatched_at,
            )
        ]

    def _expand_to_row(
        self, to_number: str, lt_code: str, leg_id: str, dispatched_at: datetime, fallback_sender: str
    ) -> list[ExpectedOrder]:
        detail = self._fetch_to_detail(to_number)
        sender = detail.get("sender") or fallback_sender
        order_count = detail.get("order_count") or 0
        children = detail.get("detail_rows") or []

        if order_count == 1:
            child = children[0] if children else {}
            order_code = extract_order_id(child) or to_number
            return [
                ExpectedOrder(
                    order_code=order_code,
                    lt_code=lt_code,
                    leg_id=leg_id,
                    to_code=to_number,
                    cargo_type=CargoType.BULKY,
                    to_subtype=TOSubType.NOT_APPLICABLE,
                    sender_location=sender,
                    dispatched_at=dispatched_at,
                )
            ]

        if not children:
            # Chưa lấy được danh sách đơn con (vd FMS lỗi tạm) - vẫn giữ ở mức
            # TO để không mất dấu, chờ vòng sau đối soát lại.
            return [
                ExpectedOrder(
                    order_code=to_number,
                    lt_code=lt_code,
                    leg_id=leg_id,
                    to_code=to_number,
                    cargo_type=CargoType.TO_SORTING,
                    to_subtype=TOSubType.MULTI,
                    sender_location=sender,
                    dispatched_at=dispatched_at,
                )
            ]

        results = []
        for child in children:
            order_code = extract_order_id(child)
            if not order_code:
                continue
            results.append(
                ExpectedOrder(
                    order_code=order_code,
                    lt_code=lt_code,
                    leg_id=leg_id,
                    to_code=to_number,
                    cargo_type=CargoType.TO_SORTING,
                    to_subtype=TOSubType.MULTI,
                    sender_location=sender,
                    dispatched_at=dispatched_at,
                )
            )
        return results

    def _fetch_to_detail(self, to_number: str) -> dict:
        url_template = GENERAL_TO_DETAIL_URL + f"?pageno={{page}}&to_number={to_number}&count={{count}}"
        first_page = self.session.request_json(
            "GET",
            url_template.format(page=1, count=PAGE_COUNT),
            label=f"TO detail {to_number} | page 1",
        )
        data_node = (first_page or {}).get("data") or {}
        detail_rows, total = self.session.fetch_list(url_template, label=f"TO detail {to_number}")

        sample = detail_rows[0] if detail_rows else {}
        sender_keys = ["sender", "sender_name", "sender_station_name", "from_station_name", "loaded_station_name"]
        sender = first_value(data_node, sender_keys) or first_value(sample, sender_keys)

        order_count = to_int(first_value(data_node, ["quantity"]))
        if order_count <= 0:
            forward_quantity = to_int(first_value(data_node, ["forward_quantity"]))
            return_quantity = to_int(first_value(data_node, ["return_quantity"]))
            order_count = forward_quantity + return_quantity
        if order_count <= 0:
            order_count = to_int(total or len(detail_rows))

        return {"sender": sender, "order_count": order_count, "detail_rows": detail_rows}
