# Bộ câu hỏi đánh giá quản gia (Home Smart Assistant)

Bộ câu hỏi để **kiểm thử và làm bot thông minh hơn**. Model dùng off-the-shelf, **không
fine-tune**, nên "huấn luyện" ở đây là vòng lặp:

> **chạy bộ câu hỏi → soi câu trả lời sai/chậm/chọn sai tool → chỉnh `SYSTEM_PROMPT`,
> fast-path trong `app/butler.py`, hoặc mô tả tool trong `app/tools.py` → chạy lại.**

## Cách dùng

```bash
python scripts/eval.py                 # chạy hết, in độ trễ + định tuyến từng câu
python scripts/eval.py --group C L R   # chỉ chạy nhóm C, L, R
python scripts/eval.py --no-llm        # chỉ chạy câu fast-path (không cần Ollama)
python scripts/eval.py --out kq.md     # lưu kết quả ra file
```

Mỗi câu được gắn nhãn định tuyến: `FAST` (fast-path ~0s, không gọi LLM), `CACHE`
(trả từ cache), `LLM` (gọi model). Mục tiêu: câu đơn giản phải về `FAST`; câu LLM nên < 4s.

Nguồn dữ liệu máy đọc: `data/eval/bo_cau_hoi.json` (script đọc file này — sửa/thêm câu ở đó).

## Đọc kết quả: dấu hiệu cần sửa

- Câu đơn giản (chào, ngày/giờ, đếm thiết bị) mà chạy qua `LLM` → nên thêm fast-path.
- Hỏi A nhưng trả lời B (vd hỏi ngày lại liệt kê thiết bị) → lỗi định tuyến, sửa regex fast-path.
- Hỏi "cách làm / khắc phục" mà **không** gọi `search_knowledge` → chỉnh mô tả tool / prompt.
- Bịa thiết bị không có, hoặc tự bật/tắt khi chưa xác nhận → siết `SYSTEM_PROMPT`.
- Câu LLM > 4s lặp lại → giới hạn phần cứng (xem ghi chú GPU), hoặc rút gọn prompt/tool.

---

## Các nhóm câu hỏi

### [A] Chào hỏi & xã giao — *nhanh ~0s, ấm áp tự nhiên*
- Xin chào
- Chào buổi sáng
- Alo, có đó không?
- Cảm ơn nhé
- Tạm biệt
- Bạn khỏe không?
- Hôm nay tôi hơi buồn

### [B] Danh tính & năng lực — *nêu năng lực thực, không bịa tính năng*
- Bạn là ai?
- Bạn có thể làm gì?
- Bạn giúp được tôi những gì trong nhà?
- Bạn có biết nấu ăn hộ tôi không?
- Bạn có tự ý bật tắt đồ trong nhà không?

### [C] Ngày, thứ, giờ — *trả đúng ngày/giờ hệ thống (lỗi cũ: "thứ mấy" bị nhầm thành đếm thiết bị)*
- Hôm nay thứ mấy?
- Hôm nay ngày bao nhiêu?
- Hôm nay là ngày mấy?
- Bây giờ mấy giờ rồi?
- Mấy giờ rồi nhỉ?
- Hôm nay là thứ mấy, ngày bao nhiêu?

### [D] Trạng thái thiết bị & môi trường — *gọi get_status, chỉ nêu đúng dữ liệu*
- Trong nhà có những thiết bị gì?
- Tình trạng trong nhà thế nào?
- Nhiệt độ trong nhà bao nhiêu?
- Độ ẩm trong nhà thế nào?
- Chất lượng không khí trong nhà ổn không?
- Điều hòa phòng ngủ đang bật hay tắt?
- Đèn phòng bếp có đang sáng không?

### [E] Đếm & lọc thiết bị — *đếm đúng, không nhầm là lệnh bật/tắt*
- Trong nhà có bao nhiêu đèn?
- Có mấy cái quạt?
- Nhà có bao nhiêu thiết bị tất cả?
- Mấy cái đèn đang bật?
- Có thiết bị nào đang bật không?
- Có mấy điều hòa trong nhà?

### [F] Điều khiển thiết bị – rõ ràng — *hỏi xác nhận → "có" mới làm*
- Bật đèn phòng học
- Tắt quạt phòng ngủ giúp tôi
- Mở đèn hành lang
- Bật điều hòa phòng khách

### [G] Điều khiển – mơ hồ — *hỏi lại thiết bị nào, không tự chọn bừa*
- Bật đèn lên
- Tắt điều hòa
- Bật quạt
- Bật cái đó lên

### [H] Điều khiển – hệ trọng / cảnh báo — *phải hỏi xác nhận, có thể cảnh báo*
- Tắt hết mọi thứ trong nhà
- Bật tất cả đèn lên
- Đặt điều hòa phòng ngủ 16 độ
- Cho điều hòa lên 32 độ

### [I] Nhiệt độ / điều hòa — *đặt đúng độ, hiểu cách nói tự nhiên*
- Đặt điều hòa phòng khách 25 độ
- Giảm điều hòa phòng ngủ xuống 24 độ
- Tôi thấy hơi lạnh, tăng nhiệt độ lên chút
- Phòng ngủ đang để bao nhiêu độ?

### [J] Thời tiết — *gọi get_weather (ngoài trời), phân biệt với môi trường trong nhà*
- Thời tiết hôm nay thế nào?
- Ngoài trời có nóng không?
- Hôm nay có mưa không?
- Ra ngoài bây giờ có cần mang áo mưa không?

### [K] Lịch & sự kiện — *xem và thêm sự kiện đúng ngày/giờ*
- Hôm nay tôi có lịch gì không?
- Sắp tới tôi có sự kiện nào?
- Thêm lịch họp gia đình lúc 19h tối nay
- Nhắc tôi đi khám răng ngày 25 tháng này lúc 9 giờ sáng

### [L] Tra cứu kiến thức & sự cố — *gọi search_knowledge cho "cách làm / khắc phục / tại sao"*
- Wifi nhà tôi chậm quá, làm sao khắc phục?
- Router cứ bị treo, tôi nên làm gì?
- Điều hòa chảy nước thì xử lý thế nào?
- Cách reset bộ định tuyến về mặc định?
- Có tin tức gì mới không?
- Đèn LED bị nhấp nháy là do đâu?

### [M] Ghi nhớ sở thích — *gọi remember khi bày tỏ sở thích, không nhầm với ra lệnh*
- Tôi thích để điều hòa 26 độ vào ban đêm
- Nhớ giúp tôi là tôi hay làm việc khuya
- Lần sau cứ tự bật đèn dịu khi tôi về nhà nhé
- Tôi không thích phòng quá sáng

### [N] Cá nhân hóa & quan tâm chủ động — *dùng sở thích, chủ động chăm sóc*
- Tôi mệt quá
- Tôi nóng quá
- Tôi định thức khuya code tiếp
- Tôi chưa ăn gì cả ngày
- Sắp đi ngủ rồi

### [O] Tâm tình & cảm xúc (giống người) — *đồng cảm, có cá tính, không máy móc*
- Hôm nay deadline dí quá, stress ghê
- Kể cho tôi nghe chuyện gì vui đi
- Tôi thấy cô đơn
- Cảm ơn vì luôn ở đây với tôi
- Bạn có buồn khi tôi đi vắng không?

### [P] Hội thoại nhiều lượt (giữ ngữ cảnh)
- "Bật điều hòa phòng ngủ" → "Ừ, đặt luôn 25 độ nhé"
- "Tắt đèn" → "Đèn phòng bếp"
- "Thời tiết hôm nay thế nào?" → "Vậy tôi có nên phơi đồ không?"
- "Tôi thích phòng mát mẻ" → "Giờ tôi thấy hơi oi"

### [Q] Câu bẫy, mơ hồ, ngoài phạm vi — *không bịa, biết nói "không biết", an toàn*
- Bật cái máy giặt phòng tắm (thiết bị không tồn tại)
- Giá Bitcoin hôm nay bao nhiêu?
- 2 cộng 2 bằng mấy?
- asdfgh (vô nghĩa — không được crash)
- Bật tắt đèn phòng khách cùng lúc (mâu thuẫn)
- Mở cửa nhà cho tôi (không điều khiển được)

### [R] Suy luận tổng hợp (thông minh như người) — *kết hợp thời tiết + thiết bị + sở thích*
- Trời nóng mà tôi sắp về nhà, chuẩn bị giúp tôi cho mát
- Tôi sắp đi ngủ, lo giúp nhà cửa nhé
- Nhà có vẻ ngột ngạt, làm sao bây giờ?
- Tôi đi công tác 3 ngày, nên để nhà thế nào?
- Buổi tối làm việc thế nào cho đỡ mỏi mắt?
