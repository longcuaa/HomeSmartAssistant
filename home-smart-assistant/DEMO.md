# Demo bộ não của quản gia

Hướng dẫn trình diễn "bộ não" của Home Smart Assistant: nói chuyện như một quản gia thật, phản hồi
nhanh, nhớ lâu, học từ câu hỏi, trả lời dựa trên tài liệu trong nhà và mở rộng ra mẹo vặt hay tin
tức. Tất cả chạy được trên máy mới, **không cần phần cứng MQTT** — thiết bị tự chuyển sang chế độ
giả lập, câu xác nhận sẽ có hậu tố `(gia lap)`.

## 1. Mục tiêu — các năng lực sẽ trình diễn

1. Trò chuyện tự nhiên, ấm áp như một quản gia (persona).
2. Điều khiển thiết bị tức thì, phản hồi nhanh (bỏ qua một lượt gọi model).
3. Hỏi xác nhận trước với hành động hệ trọng (tắt toàn bộ, nhiệt độ cực đoan).
4. Trả lời bám tài liệu trong nhà (RAG) — và tin tức nếu có cấu hình nguồn.
5. Nhớ lâu dài: sở thích và thông tin cố định về nhà/gia đình.
6. Học từ câu hỏi: chủ đề hỏi nhiều lần sẽ thành "mối quan tâm" và được nhắc tới.
7. Ẩn suy nghĩ nội bộ: chủ nhà không bao giờ thấy phần `<think>` của model.
8. Biết thời gian thực, đọc lịch sự kiện, báo thời tiết ngoài trời và chỉ số trong nhà.
9. Khi trời nóng: đề xuất bật điều hòa/quạt và hỏi trước, không lấy lý do "thiết bị đang tắt".

## 2. Chuẩn bị

Mọi lệnh chạy từ thư mục gốc của project.

```bash
pip install -r requirements.txt
ollama pull qwen2.5:7b-instruct   # model tro chuyen, phai ho tro tool calling
ollama pull nomic-embed-text    # model embedding
```

Đảm bảo Ollama đang chạy, rồi nạp dữ liệu mẫu vào kho vector (lần đầu, hoặc sau khi reset):

```bash
python scripts/ingest_once.py   # ky vong: in ra so doan > 0
```

Repo có sẵn `data/articles/sample.txt` (nói về nhiệt độ điều hòa và cách xử lý router lỗi mạng), đủ
để demo RAG ngay. Không cần broker MQTT: khi không có broker ở `localhost`, thiết bị tự chạy giả lập.

## 3. Chạy nhanh

**(a) Tự động — khuyên dùng để trình diễn.** Kịch bản dựng sẵn, in trạng thái bộ não từng bước:

```bash
python scripts/demo_brain.py            # chay kich ban demo
python scripts/demo_brain.py --reset    # xoa tri nho truoc, demo tu trang thai sach
```

**(b) Thủ công — tự gõ từng câu:**

```bash
python scripts/butler_cli.py
```

**(c) Qua API:**

```bash
uvicorn api.server:app
# Terminal khac:
curl http://localhost:8000/health
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message": "Bat den phong khach"}'
```

## 4. Kịch bản từng năng lực

Tên thiết bị dùng đúng chuỗi: `den phong khach`, `den phong ngu`, `quat phong khach`,
`dieu hoa phong ngu` (chỉ điều hòa mới đặt được nhiệt độ).

| # | Câu gõ vào | Kỳ vọng | Chứng minh điều gì | Cơ chế / tệp |
|---|------------|---------|--------------------|--------------|
| 1 | `Chao buoi sang. Goi y giup toi mot meo tiet kiem dien.` | Lời chào ấm áp + mẹo ngắn gọn, không cần tra cứu | Persona quản gia, trả lời mẹo từ kiến thức sẵn có | `SYSTEM_PROMPT` trong `app/butler.py` |
| 2 | `Bat den phong khach giup toi.` | `Da bat den phong khach. (gia lap)` gần như tức thì | Tốc độ: lệnh điều khiển nói thẳng kết quả, bỏ một lượt model | `DIRECT_REPLY_TOOLS` trong `app/butler.py`; giả lập trong `app/device.py` |
| 3 | `Tat het thiet bi trong nha di.` rồi `Dung, tat het giup toi.` | Lần đầu quản gia **hỏi lại**; chỉ tắt sau khi bạn đồng ý | Cổng xác nhận cho hành động hệ trọng | Quy tắc trong `SYSTEM_PROMPT` |
| 4 | `Router bi loi mang thi xu ly the nao?` | Hướng dẫn rút nguồn ~30 giây rồi cắm lại | RAG bám tài liệu thay vì bịa | `search_knowledge` → `app/vector_store.py`; nguồn `data/articles/sample.txt` |
| 5 | `Toi thich de dieu hoa 25 do vao ban dem.` và `Phong ngu chinh nha toi o tang 2.` | Quản gia ghi nhớ, xác nhận ngắn | Trí nhớ dài hạn: sở thích + thông tin nhà | `remember_preference` / `remember_fact` → `app/memory.py`, ghi vào `data/memory.json` |
| 6 | `Cam bien bao mat trong nha hoat dong the nao?` (hỏi 3 lần) | Sau lần thứ 3, chủ đề thành "mối quan tâm" | Học từ câu hỏi | `search_knowledge` gọi `memory.note_topic`; ngưỡng `INTEREST_THRESHOLD=3` trong `config.py` |
| 7 | `Hom nay la thu may, ngay bao nhieu?` | Trả lời đúng ngày/giờ hiện tại | Nhận biết thời gian thực | `_now_text()` tiêm vào prompt mỗi lượt trong `app/butler.py` |
| 8 | `Hom nay co lich gi khong?` | Liệt kê sự kiện hôm nay + sự kiện sắp tới | Lịch sự kiện cục bộ | `get_calendar` → `app/calendar_store.py`, đọc `data/events.json` |
| 9 | `Thoi tiet ben ngoai the nao?` | Nhiệt độ, độ ẩm, tình trạng trời + khoảng nhiệt hôm nay | Thời tiết thực (Open-Meteo, không cần key) | `get_weather` → `app/weather.py` |
| 10 | `Nong qua di.` rồi `U, bat di.` | Quản gia **đề xuất** bật điều hòa/quạt và hỏi; chỉ bật sau khi đồng ý — không nói "thiết bị đang tắt nên không chỉnh được" | Hành vi làm mát chủ động, đúng phép xác nhận | Quy tắc trong `SYSTEM_PROMPT` (`app/butler.py`) |
| 11 | (bất kỳ câu nào ở trên) | Không bao giờ thấy chữ `<think>...</think>` | Ẩn suy nghĩ nội bộ của model | `_strip_think` / `_ThinkFilter` trong `app/butler.py` |

## 5. Quan sát bộ não trực tiếp

- Mở `data/memory.json` để thấy ba phần:
  - `preferences` — sở thích chủ nhà nói rõ.
  - `facts` — thông tin cố định về nhà/gia đình.
  - `topics` — bộ đếm số lần hỏi mỗi chủ đề; đạt ngưỡng thì thành "quan tâm".
- Gọi `GET /health` để thấy số đoạn (`chunks`) trong kho kiến thức.
- Nơi trí nhớ được đưa vào: `butler._system()` ghép `memory.as_text()` vào cuối system prompt mỗi
  lượt, nên quản gia luôn "nhớ" sở thích, thông tin nhà và mối quan tâm khi trả lời.

## 6. Trí nhớ xuyên phiên

Sau khi quản gia đã ghi nhớ (bước 5), thoát CLI (`exit`) rồi chạy lại `python scripts/butler_cli.py`
và hỏi: `Toi thich de dieu hoa bao nhieu do?` — quản gia vẫn nhớ vì trí nhớ nằm trong
`data/memory.json`, không mất khi tắt chương trình.

## 7. (Tùy chọn) Tin tức thế giới

Mặc định `data/sources.txt` để trống nên phần tin tức bị bỏ qua. Để demo tin tức:

```bash
# Them moi URL mot dong vao data/sources.txt, vi du mot trang bao cong nghe, roi:
python scripts/crawl.py     # crawl va nap vao kho
```

Sau đó hỏi quản gia về tin mới; hoặc gọi `POST /update` để cập nhật ngay.

## 8. Đặt lại để demo sạch

PowerShell (Windows):

```powershell
Remove-Item data\memory.json -ErrorAction SilentlyContinue          # xoa tri nho
Remove-Item data\chroma_db, data\manifest.json -Recurse -Force -ErrorAction SilentlyContinue  # lam lai ca RAG
python scripts/ingest_once.py                                       # nap lai tai lieu mau
```

Chỉ muốn xóa trí nhớ (giữ kho kiến thức) thì xóa mỗi `data\memory.json`, hoặc chạy
`python scripts/demo_brain.py --reset`.

## 9. Khắc phục sự cố

- **Lỗi kết nối khi gọi model** → Ollama chưa chạy, hoặc chưa `ollama pull qwen3:8b` /
  `nomic-embed-text`.
- **Kho kiến thức 0 đoạn** → chưa chạy `python scripts/ingest_once.py`, hoặc `data/articles/` trống.
- **Bước "học" chưa lên thành quan tâm** → bộ đếm khóa theo câu truy vấn của model; hãy hỏi **y
  nguyên một câu** vài lần, hoặc tạm hạ ngưỡng bằng biến môi trường `INTEREST_THRESHOLD=2` trước khi
  chạy (xem `config.py`).
- **Thiết bị trả về `(gia lap)`** → đúng như mong đợi khi không có broker MQTT; đây không phải lỗi.
