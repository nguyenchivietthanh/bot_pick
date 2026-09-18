"""Hằng số FMS xác nhận được từ nguyenchivietthanh/bot_deli_ver1 (bot đối soát
chiều ngược lại: BDA là điểm GỬI). Bot đó dùng cùng hệ FMS này, chỉ khác
chiều nên phần lớn endpoint/tên trạm dùng lại được.

Nguồn xác nhận: BOT-Deli_BDA_arrived_LT.py — `first_station=4110` tương ứng
SOC_CODE "BD B Mega SOC".
"""

from __future__ import annotations

FMS_BASE = "https://spx.shopee.vn"

# Tên trạm BDA hiển thị trong FMS (dùng để chọn role/station khi Selenium
# login, và để so khớp station_name trả về từ API).
BDA_STATION_NAME = "BD B Mega SOC"

# ID trạm BDA dùng cho filter `middle_station` trên trip/history/list.
# XÁC NHẬN từ bot_deli_ver1 (first_station=4110 <-> SOC_CODE "BD B Mega SOC").
BDA_STATION_ID = "4110"

TRIP_HISTORY_LIST_URL = f"{FMS_BASE}/api/admin/transportation/trip/history/list"
TRIP_LIST_URL = f"{FMS_BASE}/api/admin/transportation/trip/list"
TRIP_HISTORY_DETAIL_URL = f"{FMS_BASE}/api/admin/transportation/trip/history/detail"
TRIP_DETAIL_URL = f"{FMS_BASE}/api/admin/transportation/trip/detail"
TRIP_HISTORY_LOADING_LIST_URL = f"{FMS_BASE}/api/admin/transportation/trip/history/loading/list"
TRIP_LOADING_LIST_URL = f"{FMS_BASE}/api/admin/transportation/trip/loading/list"
GENERAL_TO_DETAIL_URL = f"{FMS_BASE}/api/in-station/general_to/detail/search"
TRACKING_SEARCH_URL = f"{FMS_BASE}/api/fleet_order/order/tracking_list/search"

PAGE_COUNT = 100

# LT đã ENDED tại 1 trạm dùng status 90 (xác nhận từ bot_deli_ver1).
TRIP_STATION_STATUS_ENDED = "90"
