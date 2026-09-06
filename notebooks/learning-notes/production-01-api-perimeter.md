# Production 01 — API perimeter

## Mục lục

1. Mục tiêu
2. Thiết kế đã triển khai
3. Quy tắc vận hành
4. Những điều cần nhớ
5. Câu hỏi ôn tập

## 1. Mục tiêu

Bảo vệ biên API trước khi tối ưu sâu retrieval hoặc cost. Một request hợp lệ phải có danh tính,
quota, correlation ID và error contract an toàn trước khi được phép tiêu tốn tài nguyên downstream.

## 2. Thiết kế đã triển khai

- `X-API-Key` xác thực caller; hệ thống chỉ lưu fingerprint SHA-256 rút gọn làm `user_id`, không log key.
- Redis áp dụng hai giới hạn trong cùng cửa sổ: per-identity và global.
- `/api/v1/live` là public; health chi tiết và mọi business endpoint đều được bảo vệ.
- Swagger, ReDoc và OpenAPI document endpoints bị tắt trong production.
- Mỗi response có `X-Request-ID`; access log chỉ ghi metadata, không ghi body/raw query.
- Mọi lỗi public dùng envelope `error.code`, `error.message`, `error.request_id`, `error.details?`.
- Validation error không echo input; exception nội bộ chỉ xuất hiện trong server log/trace.
- Feedback chỉ được chấp nhận khi API identity sở hữu `trace_id` tương ứng.

## 3. Quy tắc vận hành

- Development mặc định giữ auth/rate limit tắt để bài học cũ vẫn chạy.
- Production từ chối startup nếu `DEBUG=true`, auth/rate limit tắt, API key yếu, hoặc Langfuse
  capture raw content mà chưa bật policy opt-in.
- Redis là dependency bắt buộc của security khi rate limit/feedback ownership hoạt động. Nếu Redis lỗi,
  perimeter fail-closed nhanh bằng HTTP 503; không bỏ qua kiểm soát bảo mật.
- HTTP 429 trả `Retry-After` và quota headers để client biết khi nào thử lại.

## 4. Những điều cần nhớ

- Authentication trả lời “ai đang gọi”; authorization trả lời “caller đó được làm gì”.
- Per-identity limit bảo vệ tính công bằng; global limit bảo vệ tổng năng lực và hóa đơn provider.
- Liveness chỉ chứng minh process còn sống; dependency health có thể chậm hoặc chứa thông tin vận hành,
  nên không phải public liveness probe.
- Request ID do server sinh mặc định. Chỉ tin ID từ ingress khi đã có trusted proxy boundary.
- Cho phép raw content trong Langfuse không đồng nghĩa với việc nên ghi raw content vào application log.

## 5. Câu hỏi ôn tập

1. Vì sao chỉ có per-user rate limit vẫn chưa bảo vệ được tổng OpenAI budget?
2. Vì sao feedback cần kiểm tra trace ownership dù `trace_id` khó đoán?
3. Redis rate-limit bị timeout thì fail-open hay fail-closed? Vì sao khác cache Redis?
4. `request_id` giúp điều tra một HTTP 500 qua API log và Langfuse trace như thế nào?
5. Tại sao public error message không được chứa `str(exception)`?

Gợi ý thực hành: bật production config bằng hai API key test, gọi xen kẽ đến khi chạm global quota,
sau đó thử gửi feedback của key B cho trace do key A tạo và kiểm tra HTTP 403.
