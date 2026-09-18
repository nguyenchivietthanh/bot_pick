# bot_pick — BOT ĐỐI SOÁT PICKUP (missing đơn giữa điểm gửi và BDA)

Bot đối soát các đơn mà điểm gửi đã xác nhận gửi đi trên 1 chuyến LinehaulTrip
(LT) nhưng thực tế **không có mặt tại BDA** (điểm nhận) khi hàng đến.

## Nghiệp vụ

- **BDA**: điểm nhận hàng (hub đích). Có nhiều điểm gửi khác nhau gửi hàng đến.
- **Loại hàng**: `BULKY`, `TO_TRANSIT`, `TO_SORTING`. Hai loại `TO_*` có thêm
  phân loại theo số đơn trong TO: `SINGLE` (TO 1 đơn) / `MULTI` (TO nhiều đơn).
- **LT (LinehaulTrip)**: 1 chuyến xe, có thể có nhiều chặng (leg). Bot chỉ xử
  lý các chặng có `destination_code == BDA`.
- **Đơn cần đối soát (MISSING)**: có trong manifest "đã gửi" (expected) của
  điểm gửi cho 1 chặng LT, nhưng không có trong dữ liệu scan nhận thực tế
  (actual) tại BDA cho chặng đó.

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
mốc chốt cuối cùng.

## Kiến trúc

```
run.py                     entrypoint, chạy vòng lặp 24/7
src/
  domain.py                model nghiệp vụ (CargoType, TOSubType, LinehaulLeg,
                            ExpectedOrder, ActualReceipt, ReconciliationResult, ...)
  reconciliation.py         logic đối soát thuần (không I/O, dễ unit test)
  api_client.py              SourceAPIClient (interface) + HttpInternalAPIClient
                            (cài đặt gọi API nội bộ — CẦN CHỈNH theo API thật)
  poller.py                  vòng lặp "cuốn chiếu": quét chặng mới + tái kiểm
                            tra các đơn đang mở (PENDING_GRACE/MISSING)
  storage/
    models.py               SQLAlchemy models (SQLite)
    db.py                    khởi tạo engine/session
    repository.py            upsert kết quả + checkpoint
  sheets/
    writer.py                đồng bộ kết quả sang Google Sheet
tests/
  test_reconciliation.py     unit test cho logic đối soát
```

Nguyên tắc thiết kế: **logic đối soát (`reconciliation.py`) không phụ thuộc
API/DB/Sheet thật** — mọi thứ đi qua interface `SourceAPIClient`. Nhờ vậy có
thể test toàn bộ luồng quyết định trạng thái mà không cần API thật, và khi
API nội bộ thay đổi thì chỉ cần sửa `api_client.py`.

## Cơ chế chạy "cuốn chiếu" 24/7

Vì Hub/SOC vận hành 24/7, bot chạy như 1 tiến trình dài hơi (`run.py`), lặp
theo `POLL_INTERVAL_SECONDS`. Mỗi vòng:

1. Lấy các chặng LT mới **đến BDA** kể từ checkpoint lần quét trước
   (`leg_checkpoints` / `scan_state` trong SQLite).
2. Với mỗi chặng mới: so khớp expected vs actual → ghi các đơn thiếu.
3. Với các đơn đang ở trạng thái mở (`PENDING_GRACE`/`MISSING`) từ các vòng
   trước: gọi lại actual receipts để tự động chuyển sang `RESOLVED_LATE` nếu
   đã scan, hoặc leo trạng thái theo thời gian.
4. Ghi kết quả mới/thay đổi vào SQLite và (nếu cấu hình) đồng bộ Google Sheet.

Nhờ bước 3, bot không cần xử lý lại toàn bộ lịch sử mỗi vòng — dữ liệu "cuốn"
dần về trạng thái ổn định.

## Cài đặt

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# điền SOURCE_API_BASE_URL, SOURCE_API_TOKEN, BDA_HUB_CODE, ...
# nếu dùng Google Sheets: điền GOOGLE_SERVICE_ACCOUNT_JSON + GOOGLE_SPREADSHEET_ID
# và share quyền Editor cho email của service account trên Google Sheet đó

pytest                 # chạy unit test logic đối soát
python run.py           # chạy bot 24/7
```

## TODO trước khi chạy production

1. **Chỉnh `src/api_client.py`** (`HttpInternalAPIClient`) theo API nội bộ
   thật: đường dẫn endpoint, tham số query, và đặc biệt 3 hàm `_parse_*` để
   map đúng tên field JSON thật (hiện đang là giả định hợp lý dựa trên mô tả
   nghiệp vụ, chưa phải API thật).
2. Xác nhận **định nghĩa "chặng đã đến BDA"** phía API thật: field
   `actual_arrival`/status nào đánh dấu chặng đã tới nơi, đối chiếu lại với
   phần `get_arrived_legs`.
3. Xác nhận **đơn vị khớp**: hiện đối soát theo `order_code` (mã đơn) cho cả
   3 loại hàng, kể cả TO nhiều đơn (so từng đơn con trong TO). Nếu nghiệp vụ
   cần đối soát ở cấp TO/mã kiện cho `BULKY`, cần điều chỉnh model.
4. Tinh chỉnh `GRACE_PERIOD_MINUTES` / `CONFIRM_HORIZON_HOURS` theo SLA thực
   tế của Hub/SOC.
5. Tạo service account Google Cloud, bật Google Sheets API, tải file JSON
   credentials, share Sheet đích cho email service account.
6. Cân nhắc nâng cấp SQLite → Postgres/MySQL khi khối lượng dữ liệu lớn (chỉ
   cần đổi connection string trong `src/storage/db.py`).
