# bot_pick — BOT ĐỐI SOÁT PICKUP (missing đơn giữa điểm gửi và BDA)

Bot đối soát các đơn mà điểm gửi đã xác nhận gửi đi trên 1 chuyến LinehaulTrip
(LT) nhưng thực tế **không có mặt tại BDA** (điểm nhận) khi hàng đến.

Đây là bản "soi gương" của [`nguyenchivietthanh/bot_deli_ver1`](https://github.com/nguyenchivietthanh/bot_deli_ver1)
— bot đó coi BDA là điểm **GỬI**, đối soát hàng BDA gửi đi có bị stuck ở các
điểm nhận khác không. Bot này coi BDA là điểm **NHẬN**, đối soát hàng nơi khác
gửi đến có thực sự tới BDA không. Hai bot dùng chung 1 hệ FMS nội bộ
(`spx.shopee.vn`) nên phần lớn cách gọi API/tên trạm dùng lại được — xem mục
"Nguồn dữ liệu FMS" bên dưới.

## Nghiệp vụ

- **BDA**: điểm nhận hàng (hub đích). Có nhiều điểm gửi khác nhau gửi hàng đến.
- **Loại hàng**: `BULKY`, `TO_TRANSIT`, `TO_SORTING`. Hai loại `TO_*` có thêm
  phân loại theo số đơn trong TO: `SINGLE` (TO 1 đơn) / `MULTI` (TO nhiều đơn).
  (Trong FMS, việc BULKY vs TO nhiều đơn được xác định bằng `order_count` của
  TO: `== 1` → xử lý như BULKY, `> 1` → TO_SORTING — xác nhận từ bot_deli_ver1.)
- **LT (LinehaulTrip)**: 1 chuyến xe, có thể có nhiều chặng (leg). Bot chỉ xử
  lý các chặng có `destination_code == BDA`.
- **Đơn cần đối soát (MISSING)**: có trong danh sách "Pending Inbound" của FMS
  tại chặng LT đến BDA — tức điểm gửi đã cho lên xe nhưng FMS ghi nhận **chưa
  được scan/unload tại BDA**.

### Vòng đời trạng thái 1 đơn thiếu

```
phát hiện thiếu
      │
      ▼
PENDING_GRACE  ──(hết grace_period, vẫn thiếu)──▶  MISSING
      │                                                │
      │ (scan nhận muộn tại BDA)                       │ (scan nhận muộn)
      ▼                                                ▼
              RESOLVED_LATE ◀─────────────────────────┘
      │
      │ (quá confirm_horizon vẫn không thấy)
      ▼
CONFIRMED_MISSING  (chốt để đội vận hành xử lý nghiệp vụ)
```

`grace_period` (mặc định 60 phút) là thời gian chờ hợp lý sau khi LT đến để
tránh báo nhầm do dỡ hàng/scan còn chậm. `confirm_horizon` (mặc định 24h) là
mốc chốt cuối cùng. Hai mốc này đứng độc lập, nhưng gần với
`PENDING_READY_AFTER_ARRIVED_HOURS = 36` / `PENDING_DEADLINE_AFTER_ARRIVED_HOURS = 48`
mà bot_deli_ver1 đang dùng cho chiều ngược lại — có thể tham khảo khi tinh
chỉnh SLA thật.

## Nguồn dữ liệu FMS

`src/fms/` chứa toàn bộ phần gọi FMS nội bộ, port lại từ bot_deli_ver1:

- **`browser_fetch.py`** — copy nguyên văn từ bot_deli_ver1. Gọi API FMS qua
  `fetch()` bên trong 1 phiên Chrome **đã đăng nhập sẵn** vào
  `https://spx.shopee.vn` (không phải API token) — Selenium giữ Chrome sống,
  chọn role/station theo tên trạm truyền vào.
- **`session.py`** — `FmsSession`: bọc `browser_fetch.request_json` + phân
  trang (`fetch_list`), port từ `FmsSession` trong bot_deli_ver1.
- **`constants.py`** — endpoint FMS + tên/id trạm BDA đã xác nhận.
- **`client.py`** — `FmsInternalAPIClient`: cài đặt `SourceAPIClient` thật,
  chứa toàn bộ logic nghiệp vụ (tìm chặng LT đến BDA, gọi Pending Inbound tại
  BDA, mở rộng TO ra đơn con). Đọc docstring đầu file để biết phần nào đã
  **xác nhận** từ source bot_deli_ver1 và phần nào **chưa xác nhận** (cần
  kiểm chứng với phiên FMS thật).

### Điểm mấu chốt: FMS đã tự "đối soát" sẵn

Khác với bản thiết kế ban đầu (tự lấy 2 danh sách "đã gửi" + "đã nhận" rồi tự
diff), FMS có sẵn API **"Pending Inbound"**
(`trip/history/loading/list` / `trip/loading/list` với
`type=pending&unloaded_sequence_number=<chặng>`) trả về đúng phần **chưa được
unload** tại 1 chặng của 1 trip — tức FMS đã tự tính "đã gửi trừ đã nhận" cho
mình rồi. Bot chỉ cần:

1. Tìm các chặng LT có điểm đến là BDA (`get_arrived_legs`).
2. Gọi Pending Inbound đúng chặng đó (`get_pending_orders`) → chính là danh
   sách đơn thiếu, đã mở rộng từng TO ra đơn con qua `general_to/detail/search`.
3. Ở vòng lặp sau, gọi lại Pending Inbound cùng chặng: đơn nào **không còn**
   trong danh sách nữa → coi là đã được scan nhận (RESOLVED_LATE).

Nhờ vậy `reconciliation.py` (logic thuần, có unit test) không cần thay đổi:
`build_missing_results`/`advance_result_status` vẫn nhận vào danh sách
missing + tập order_code "đã nhận" như thiết kế ban đầu, chỉ khác nguồn dữ
liệu tính ra 2 tập đó.

## Kiến trúc

```
run.py                       entrypoint, chạy vòng lặp 24/7
src/
  domain.py                  model nghiệp vụ (CargoType, TOSubType, LinehaulLeg,
                              ExpectedOrder, ReconciliationResult, ...)
  reconciliation.py          logic đối soát thuần (không I/O, dễ unit test)
  api_client.py               SourceAPIClient (interface trừu tượng)
  poller.py                   vòng lặp "cuốn chiếu": quét chặng mới + tái kiểm
                              tra các đơn đang mở (PENDING_GRACE/MISSING)
  fms/
    browser_fetch.py          vendor nguyên văn từ bot_deli_ver1 (Selenium/Chrome)
    session.py                 FmsSession: request + phân trang
    constants.py                endpoint FMS + tên/id trạm BDA
    client.py                   FmsInternalAPIClient: cài đặt SourceAPIClient thật
  storage/
    models.py                 SQLAlchemy models (SQLite)
    db.py                      khởi tạo engine/session
    repository.py              upsert kết quả + checkpoint
  sheets/
    writer.py                  đồng bộ kết quả sang Google Sheet
tests/
  test_reconciliation.py       unit test cho logic đối soát
```

Nguyên tắc thiết kế: **logic đối soát (`reconciliation.py`) không phụ thuộc
API/DB/Sheet thật** — mọi thứ đi qua interface `SourceAPIClient`. Nhờ vậy có
thể test toàn bộ luồng quyết định trạng thái mà không cần Chrome/FMS thật, và
khi FMS đổi field/endpoint thì chỉ cần sửa `src/fms/client.py`.

## Cơ chế chạy "cuốn chiếu" 24/7

Vì Hub/SOC vận hành 24/7, bot chạy như 1 tiến trình dài hơi (`run.py`), lặp
theo `POLL_INTERVAL_SECONDS`. Mỗi vòng:

1. Lấy các chặng LT mới **đến BDA** kể từ checkpoint lần quét trước
   (`leg_checkpoints` / `scan_state` trong SQLite).
2. Với mỗi chặng mới: gọi Pending Inbound tại BDA → ghi các đơn thiếu.
3. Với các đơn đang ở trạng thái mở (`PENDING_GRACE`/`MISSING`) từ các vòng
   trước: gọi lại Pending Inbound cùng chặng để tự động chuyển sang
   `RESOLVED_LATE` nếu đã scan, hoặc leo trạng thái theo thời gian.
4. Ghi kết quả mới/thay đổi vào SQLite và (nếu cấu hình) đồng bộ Google Sheet.

Nhờ bước 3, bot không cần xử lý lại toàn bộ lịch sử mỗi vòng — dữ liệu "cuốn"
dần về trạng thái ổn định.

## Chuẩn bị Chrome/FMS

BOT cần 1 Chrome profile riêng (không dùng chung Chrome cá nhân) đã đăng nhập
sẵn FMS với role/station = BDA (tên trạm trong `BDA_HUB_CODE`):

1. Chạy `python run.py` lần đầu — Chrome sẽ tự mở tới `https://spx.shopee.vn`.
2. Đăng nhập FMS thủ công, chọn đúng station BDA.
3. `Ctrl+C` dừng BOT sau khi xác nhận đã đăng nhập xong.
4. Chạy lại `python run.py` — các lần sau BOT tự dùng lại cookie đã đăng nhập
   (lưu trong profile Chrome riêng của BOT, không đụng Chrome cá nhân).

Chi tiết cấu hình profile/pacing/retry: xem docstring đầu
`src/fms/browser_fetch.py` và các biến `BOT_DELI_CHROME_*`/`BOT_DELI_BROWSER_*`
trong `.env.example`.

## Cài đặt

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# điền BDA_HUB_CODE / BDA_STATION_ID nếu khác mặc định
# nếu dùng Google Sheets: điền GOOGLE_SERVICE_ACCOUNT_JSON + GOOGLE_SPREADSHEET_ID
# và share quyền Editor cho email của service account trên Google Sheet đó

pytest                 # chạy unit test logic đối soát (không cần Chrome/FMS)
python run.py           # chạy bot 24/7 (cần Chrome + đã đăng nhập FMS)
```

## TODO trước khi chạy production

1. **Xác nhận tham số lọc trip theo BDA** trong `_fetch_candidate_trips`
   (`src/fms/client.py`): đang dùng `middle_station=<id BDA>` độc lập (không
   kèm `first_station` như bot_deli_ver1 từng dùng) — tham số này CÓ THẬT
   trong FMS nhưng chưa xác nhận dùng độc lập có lọc đúng "mọi trip đi qua
   BDA" hay không, và chưa xác nhận `trip/list` (Handover) chấp nhận tham số
   này giống `trip/history/list`. Code đã tự an toàn bằng cách luôn xác nhận
   lại qua `trip_station[]` phía client, nhưng nên kiểm chứng trực tiếp (mở
   Network tab trong FMS UI khi lọc LT đến BDA) để tối ưu số request.
2. Xác nhận `scan_time` trong dòng Pending Inbound đúng là thời điểm điểm gửi
   scan hàng lên xe (dùng làm `dispatched_at`) — xem docstring `client.py`.
3. Tinh chỉnh `GRACE_PERIOD_MINUTES` / `CONFIRM_HORIZON_HOURS` theo SLA thực
   tế của Hub/SOC (tham khảo `PENDING_READY_AFTER_ARRIVED_HOURS` /
   `PENDING_DEADLINE_AFTER_ARRIVED_HOURS` của bot_deli_ver1).
4. Tạo service account Google Cloud, bật Google Sheets API, tải file JSON
   credentials, share Sheet đích cho email service account.
5. Cân nhắc nâng cấp SQLite → Postgres/MySQL khi khối lượng dữ liệu lớn (chỉ
   cần đổi connection string trong `src/storage/db.py`).
6. Loại hàng `TO_TRANSIT` (TO đi xuyên qua BDA, không unload) chưa được phân
   biệt tường minh trong `client.py` — hiện mọi TO nhiều đơn đều gắn
   `TO_SORTING`. Cần xác nhận điều kiện nhận biết TO_TRANSIT thật (có thể
   liên quan tới trip có nhiều chặng, BDA là `middle_station` chứ không phải
   điểm unload cuối) trước khi tách riêng.
