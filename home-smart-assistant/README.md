# Home Smart Assistant

Một **quản gia AI** cho nhà thông minh, nói tiếng Việt. Nó trò chuyện với chủ nhà, trả lời câu hỏi
dựa trên tài liệu của bạn (RAG), đưa ra gợi ý cá nhân hóa, điều khiển thiết bị, và còn biết giờ
giấc, lịch sự kiện, thời tiết cùng tin tức. Bộ não dùng một model có sẵn (qwen3 qua Ollama) kết hợp
RAG để bám dữ liệu và tool calling để hành động — **không train lại model nào**.

Tài liệu này tóm tắt toàn bộ dự án: nó làm được gì, luồng hoạt động ra sao, từng file/hàm đóng vai
trò gì, và cách tối ưu tốc độ phản hồi.

---

## 1. Tổng quan các năng lực

- **Trò chuyện tự nhiên** như một quản gia: ấm áp, ngắn gọn, lịch sự.
- **Điều khiển thiết bị** (đèn, quạt, điều hòa) qua tool calling; thật thì qua MQTT, không có phần
  cứng thì tự chạy **giả lập** (câu trả lời gắn hậu tố `(gia lap)`).
- **RAG**: trả lời bám tài liệu trong nhà và tin tức đã nạp, thay vì bịa.
- **Trí nhớ dài hạn**: nhớ sở thích và thông tin cố định của gia đình; **học từ câu hỏi** (chủ đề
  hỏi nhiều lần thành "mối quan tâm").
- **Thời gian thực**: luôn biết ngày giờ hiện tại.
- **Lịch sự kiện** cục bộ (`data/events.json`) và **thời tiết** ngoài trời (Open-Meteo, không cần
  key).
- **Tự cập nhật tin tức** từ các nguồn báo mỗi sáng (tùy chọn).
- **Tốc độ**: stream từng đoạn chữ, lệnh điều khiển trả lời thẳng, tắt suy nghĩ nội bộ để nhanh.
- **Ẩn suy nghĩ nội bộ**: chủ nhà không bao giờ thấy phần `<think>` của model.

Để trình diễn từng năng lực, xem **`DEMO.md`** hoặc chạy `python scripts/demo_brain.py`.

---

## 2. Luồng hoạt động

### Luồng một lượt chat

```
Người dùng (CLI / API)
      │  câu hỏi + lịch sử hội thoại
      ▼
app/butler.py  ──►  _system(): dựng system prompt
      │              (persona + giờ hiện tại + trí nhớ + /no_think)
      ▼
app/llm.py  ──►  gọi model qua endpoint tương thích OpenAI (Ollama/vLLM)
      │
      ├─ model trả lời thẳng ──────────────► stream về người dùng
      │
      └─ model yêu cầu gọi công cụ
                 │
                 ▼
        app/tools.py: execute(name, args)
          ├─ điều khiển thiết bị → app/device.py (MQTT) hoặc giả lập
          ├─ search_knowledge   → app/vector_store.py (Chroma) + embedding
          ├─ get_weather        → app/weather.py (Open-Meteo)
          ├─ get_calendar       → app/calendar_store.py (data/events.json)
          └─ remember_*         → app/memory.py (data/memory.json)
                 │  kết quả công cụ
                 ▼
        quay lại model để diễn đạt câu trả lời (tối đa MAX_STEPS = 5 vòng)
```

Hai tối ưu nằm trong `butler.py`:
- **Direct-reply**: lệnh điều khiển trong `DIRECT_REPLY_TOOLS` trả về câu xác nhận có sẵn, nói thẳng,
  **bỏ qua một lượt gọi model**.
- **Lọc suy nghĩ**: mọi khối `<think>...</think>` bị loại khỏi luồng trả lời (kể cả khi bị cắt ngang
  giữa các đoạn stream).

### Luồng nạp dữ liệu / tin tức

```
data/articles/*.{txt,md,pdf}                 data/sources.txt (URL báo)
        │                                            │
        │                                   app/crawler.py: crawl, trích nội dung
        │                                            │  lưu .md vào data/articles/
        ▼                                            ▼
app/ingest.py: cắt đoạn (documents.py) → embedding (llm.py) → app/vector_store.py (Chroma)
        │  dùng manifest băm nội dung: bỏ qua file không đổi, xóa-nạp lại file đã đổi
        ▼
   Kho vector sẵn sàng cho search_knowledge
```

Bộ lịch (`app/scheduler.py`) chạy luồng tin tức mỗi sáng; `app/watcher.py` là cách khác, tự nạp lại
khi thư mục `data/articles/` thay đổi.

---

## 3. Cấu trúc thư mục & vai trò từng file

    home-smart-assistant/
        config.py            cấu hình tập trung (model, đường dẫn, ngưỡng, toa độ, latency)
        requirements.txt
        .env.example         mẫu biến môi trường, copy thành .env nếu muốn đổi
        app/
            llm.py           client gọi model: embed(), chat()
            butler.py        quản gia: vòng lặp tool calling, bản stream, lọc suy nghĩ
            tools.py         đăng ký công cụ: điều khiển, tra cứu, ghi nhớ, thời tiết, lịch
            memory.py        trí nhớ dài hạn: sở thích, thông tin nhà, học từ câu hỏi
            weather.py       thời tiết ngoài trời qua Open-Meteo
            calendar_store.py lịch sự kiện cục bộ trong data/events.json
            device.py        lớp MQTT: publish/read_sensor, tự giả lập khi không có broker
            documents.py     đọc file txt/md/pdf và cắt thành đoạn
            vector_store.py  bọc Chroma: add/delete/query/count
            ingest.py        luồng nạp dữ liệu, cập nhật tăng dần theo manifest
            crawler.py       crawl tài liệu/báo từ web vào thư mục articles
            scheduler.py     cập nhật báo theo lịch mỗi sáng
            watcher.py       tự nạp khi thư mục articles thay đổi
        api/
            server.py        FastAPI: /chat, /chat/stream, /update, /health
        scripts/
            ingest_once.py   nạp toàn bộ thư mục một lần
            crawl.py         crawl web rồi nạp, thủ công khi cần
            scheduler.py     chạy bộ lịch cập nhật mỗi sáng
            butler_cli.py    trò chuyện với quản gia qua dòng lệnh
            demo_brain.py    kịch bản trình diễn "bộ não" (xem DEMO.md)
        data/
            articles/        tài liệu của kho (có sample.txt mẫu)
            sources.txt      danh sách nguồn báo để cập nhật mỗi sáng
            events.json      lịch sự kiện cục bộ
            memory.json      sở thích/thông tin/chủ đề đã ghi nhớ, tự sinh
            chroma_db/       kho vector, tự sinh
            manifest.json    băm nội dung để nạp tăng dần, tự sinh

### Tóm tắt hàm chính theo module

- **`config.py`** — đọc mọi thiết lập qua `os.getenv("KEY", default)`. Nguồn sự thật duy nhất cho
  cấu hình; thêm knob mới ở đây kèm mặc định.
- **`app/llm.py`** — `embed(text)` tạo vector embedding; `chat(messages, tools, stream)` gọi model
  (kèm `max_tokens` để trả lời nhanh, gọn).
- **`app/butler.py`** — `SYSTEM_PROMPT` (persona + quy tắc), `_now_text()` (giờ hiện tại),
  `_system()` (ghép prompt mỗi lượt), `chat()` (không stream, cho API), `chat_stream()` (stream cho
  CLI/TTS), `_strip_think()` / `_ThinkFilter` (ẩn suy nghĩ), `DIRECT_REPLY_TOOLS`, `MAX_STEPS=5`.
- **`app/tools.py`** — `TOOLS` (khai báo công cụ chuẩn OpenAI), `_REGISTRY` (tên → hàm),
  `execute(name, args)` (điều phối). Các hàm công cụ: `turn_on_device`, `turn_off_device`,
  `set_temperature`, `get_home_state`, `get_environment`, `search_knowledge`, `remember_preference`,
  `remember_fact`, `get_weather`, `get_calendar`, `add_event`. Trạng thái nhà giả lập trong `HOME`,
  cảm biến giả lập trong `SENSORS`.
- **`app/memory.py`** — `load()`, `add()` (sở thích), `add_fact()` (thông tin nhà),
  `note_topic()` (đếm chủ đề được hỏi), `interests()` (chủ đề vượt ngưỡng), `as_text()` (ghép để
  chèn vào prompt), `clear()`.
- **`app/weather.py`** — `current_text()`: gọi Open-Meteo, có cache, **không bao giờ ném lỗi** (mất
  mạng thì trả câu báo lỗi nhẹ).
- **`app/calendar_store.py`** — `load()`, `add(date, time, title)`, `as_text()` (sự kiện hôm nay +
  sắp tới).
- **`app/device.py`** — `publish(topic, payload)`, `read_sensor(topic, timeout)`, `simulated()`,
  `connected()`. Tự vào chế độ giả lập nếu broker ở `localhost` không kết nối được.
- **`app/documents.py`** — `load_text(path)` (đọc txt/md/pdf), `chunk(text)` (cắt đoạn có gối đầu).
- **`app/vector_store.py`** — `add_chunks()`, `delete_source()`, `query(embedding, k)`, `count()`.
- **`app/ingest.py`** — `ingest_file()`, `ingest_dir()`, `remove_file()`; dùng manifest băm nội dung
  để chỉ xử lý file mới/đổi và dọn file đã xóa.
- **`app/crawler.py`** — `crawl_urls(urls)`, `crawl_site(seed_url, max_pages)`; tôn trọng
  `robots.txt`, nghỉ `CRAWL_DELAY` giữa các request.
- **`app/scheduler.py`** — `load_sources()`, `daily_update()`, `start_blocking()`,
  `start_background()` (nhúng vào FastAPI).
- **`api/server.py`** — endpoint: `GET /health`, `POST /chat`, `POST /chat/stream` (SSE từng token),
  `POST /update` (chạy cập nhật báo ngay).

---

## 4. Các công cụ quản gia có thể gọi

| Công cụ | Tác dụng |
|---------|----------|
| `turn_on_device` / `turn_off_device` | Bật / tắt thiết bị (đèn, quạt, điều hòa) |
| `set_temperature` | Đặt nhiệt độ cho thiết bị có điều chỉnh nhiệt |
| `get_home_state` | Trạng thái hiện tại của các thiết bị |
| `get_environment` | Chỉ số trong nhà: nhiệt độ, độ ẩm, chất lượng không khí, độ sáng |
| `search_knowledge` | Tra cứu tài liệu trong nhà + tin tức đã nạp (và **đếm chủ đề** để học) |
| `remember_preference` | Ghi nhớ một sở thích rõ ràng |
| `remember_fact` | Ghi nhớ thông tin cố định về nhà/gia đình |
| `get_weather` | Thời tiết ngoài trời hiện tại + dự báo hôm nay |
| `get_calendar` | Sự kiện hôm nay và sắp tới |
| `add_event` | Thêm một sự kiện vào lịch |

Tên thiết bị giả lập: `den phong khach`, `den phong ngu`, `quat phong khach`, `dieu hoa phong ngu`
(chỉ điều hòa đặt được nhiệt độ).

---

## 5. Tốc độ phản hồi (mục tiêu 2–4 giây)

Độ trễ chủ yếu đến từ số token model phải sinh và số lượt gọi model. Các lever đã bật sẵn và cách
chỉnh:

1. **Tắt suy nghĩ của qwen3 — lever lớn nhất.** Mặc định `ENABLE_THINKING=false`, hệ thống thêm
   `/no_think` vào prompt nên model trả lời gần như tức thì thay vì sinh một khối suy luận dài trước.
   Đặt `ENABLE_THINKING=true` nếu cần suy luận sâu hơn và chấp nhận chậm hơn.
2. **Giới hạn độ dài trả lời.** `MAX_TOKENS` (mặc định 512) giữ câu trả lời ngắn gọn và nhanh.
3. **Direct-reply cho lệnh điều khiển.** Bật/tắt đèn, quạt, đặt nhiệt độ trả về câu xác nhận có sẵn,
   **bỏ một lượt gọi model**.
4. **Stream từng token.** Người dùng thấy chữ ngay khi model sinh, giảm cảm giác chờ (CLI và
   `POST /chat/stream`).
5. **Giữ model nạp sẵn (tránh cold start).** Lần gọi đầu Ollama phải nạp model vào RAM. Đặt biến môi
   trường của Ollama `OLLAMA_KEEP_ALIVE=30m` (hoặc `-1` để giữ mãi) để khỏi nạp lại giữa các câu.
6. **Trả lời thẳng khi không cần công cụ.** System prompt hướng model trả lời mẹo/kiến thức phổ
   thông ngay, không tra cứu thừa — mỗi lần tra cứu là thêm một lượt model.

**Quan trọng — phần cứng quyết định phần còn lại.** Trên CPU thuần, `qwen3:8b` có thể vượt 4 giây dù
đã tắt suy nghĩ. Để chắc chắn đạt 2–4s:
- Chạy trên **GPU**, hoặc
- Dùng **model nhỏ hơn**: `CHAT_MODEL=qwen3:4b` hay `qwen3:1.7b` (vẫn hỗ trợ tool calling), hoặc bản
  lượng tử hóa `q4`.
- Lên production: trỏ `LLM_BASE_URL` sang **vLLM** trên GPU (xem mục cuối).

---

## 6. Chuẩn bị & chạy

Cần Ollama đang chạy, kéo về hai model (model chat phải hỗ trợ tool calling):

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
pip install -r requirements.txt
```

Mọi lệnh chạy từ thư mục gốc. Lần đầu nạp tài liệu có sẵn vào kho:

```bash
python scripts/ingest_once.py
```

Trò chuyện qua dòng lệnh (trả lời hiện dần từng đoạn):

```bash
python scripts/butler_cli.py
```

Hoặc mở API:

```bash
uvicorn api.server:app
# POST /chat       body {"message": "..."}        -> trả về {"reply", "history"}
# POST /chat/stream body {"message": "..."}        -> Server-Sent Events từng token
# GET  /health                                     -> {"status", "chunks"}
# POST /update                                      -> chạy cập nhật báo ngay
```

Để trình diễn đầy đủ bộ não, xem `DEMO.md` hoặc chạy `python scripts/demo_brain.py`.

---

## 7. Trí nhớ & học từ câu hỏi

Trí nhớ nằm trong `data/memory.json`, **tách riêng khỏi kho tài liệu** để thông tin chưa xác thực
không lẫn vào kiến thức tin cậy. Ba phần:

- `preferences` — sở thích chủ nhà nói rõ (qua `remember_preference`).
- `facts` — thông tin cố định về nhà/gia đình (qua `remember_fact`).
- `topics` — đếm số lần mỗi chủ đề được hỏi (qua `search_knowledge`). Đạt `INTEREST_THRESHOLD` (mặc
  định 3) thì thành "mối quan tâm" và được chèn vào prompt để quản gia chủ động hơn.

Cả ba được `memory.as_text()` ghép vào cuối system prompt mỗi lượt, kèm ngày giờ hiện tại.

---

## 8. Tự cập nhật báo mỗi sáng (tùy chọn)

Bỏ các URL nguồn vào `data/sources.txt`, mỗi URL một dòng. Chạy bộ lịch riêng bằng
`python scripts/scheduler.py`, hoặc cứ mở API thì một bộ lịch nền đã nhúng sẵn tự cập nhật mỗi sáng
(mặc định 6 giờ, đổi qua `DAILY_UPDATE_HOUR`/`DAILY_UPDATE_MINUTE`). Muốn chạy ngay thì gọi
`POST /update`. Nếu `sources.txt` trống thì việc cập nhật được bỏ qua.

---

## 9. Cấu hình chính (xem `.env.example`)

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Endpoint tương thích OpenAI (Ollama/vLLM) |
| `CHAT_MODEL` | `qwen3:8b` | Model chat (phải hỗ trợ tool calling) |
| `EMBED_MODEL` | `nomic-embed-text` | Model embedding |
| `ENABLE_THINKING` | `false` | Bật suy nghĩ qwen3 (chậm hơn, sâu hơn) |
| `MAX_TOKENS` | `512` | Giới hạn độ dài câu trả lời |
| `TOP_K` | `4` | Số đoạn tài liệu lấy khi tra cứu |
| `INTEREST_THRESHOLD` | `3` | Số lần hỏi để một chủ đề thành "mối quan tâm" |
| `HOME_LAT` / `HOME_LON` | Hà Nội | Toạ độ lấy thời tiết |
| `EVENTS_PATH` | `data/events.json` | File lịch sự kiện |
| `MQTT_HOST` | `localhost` | Broker MQTT (localhost không kết nối được → giả lập) |
| `DAILY_UPDATE_HOUR` | `6` | Giờ cập nhật báo mỗi sáng |

---

## 10. Lên production / AWS

Toàn bộ code gọi model qua endpoint tương thích OpenAI. Khi dựng server **vLLM** trên GPU (AWS), chỉ
cần đặt `LLM_BASE_URL` trỏ sang đó — **không sửa code**. Vector DB có thể đổi từ Chroma sang Qdrant
hay pgvector bằng cách thay riêng `app/vector_store.py`. Thiết bị thật nối qua MQTT (Home
Assistant/ESP32) bằng cách cấu hình `MQTT_HOST` khác `localhost`.
