# Production 05 — Liveness, readiness và dependency health

## Mục tiêu

Tách rõ process còn sống, service có thể nhận traffic và trạng thái từng dependency; đồng thời bảo đảm lỗi cache
không làm sập API và mọi network client đều được đóng khi shutdown.

## Tóm tắt một phút

- **Liveness `/live`** chỉ hỏi: process/event loop còn sống không? Probe phải rất nhanh và không gọi network.
- **Readiness `/ready`** hỏi: request mới có thể được phục vụ không? Chỉ kiểm tra dependency bắt buộc, có timeout
  nghiêm ngặt và trả HTTP 503 khi chưa sẵn sàng.
- **Dependency health `/health`** phục vụ chẩn đoán. Optional dependency có thể `degraded` nhưng endpoint vẫn HTTP
  200 để không tạo restart loop.
- Probe độc lập chạy đồng thời: tổng latency gần dependency chậm nhất, không phải tổng latency của tất cả dependency.
- Redis cache lỗi phải fail-open với timeout ngắn: bỏ cache và chạy full RAG. Nhưng Redis rate limiter lỗi phải
  fail-closed; khi rate limiting bật, Redis trở thành dependency bắt buộc của readiness.
- Startup chỉ construct client; không chạy schema migration hoặc phụ thuộc vào optional network service.
- Shutdown đóng từng client độc lập để một lỗi cleanup không ngăn các client còn lại được giải phóng.

## Ba contract

1. `/live` → HTTP 200 nếu process hoạt động; không tiết lộ dependency.
2. `/ready` → HTTP 200 khi PostgreSQL, OpenSearch, LLM và agent graph sẵn sàng; HTTP 503 nếu dependency bắt buộc lỗi.
3. `/health` → báo `ok`, `degraded` hoặc `unhealthy` cùng latency từng component để vận hành điều tra.

## Lỗi thường gặp

- Dùng `/health` gọi mọi backend làm Docker liveness probe: một dependency chập chờn gây restart storm.
- Redis `PING` ngay trong factory: optional cache biến thành startup blocker.
- Timeout 30 giây: fail-open về logic nhưng request vẫn bị cộng thêm 30 giây latency.
- Chỉ đóng database mà quên HTTP/Redis/OpenSearch clients: connection pool và socket bị rò khi deploy lại.
- Coi Redis luôn optional: sai nếu chính Redis đang thực thi security control như distributed rate limiting.

## Câu hỏi ôn tập

1. Vì sao liveness không được gọi PostgreSQL hoặc hosted LLM?
2. Redis down khi chỉ dùng cache khác gì Redis down khi dùng rate limiting?
3. Vì sao readiness phải trả HTTP 503 thay vì chỉ ghi `status=unhealthy` trong JSON?
4. Vì sao các probe nên chạy concurrent và có timeout riêng?
5. Cleanup một client lỗi thì các client phía sau nên được xử lý thế nào?

## Đáp án ngắn

1. Lỗi mạng không có nghĩa process chết; gắn chúng với liveness dễ tạo restart loop.
2. Cache có thể bypass để giữ availability; rate limiter không được bypass vì sẽ mất security boundary.
3. Load balancer/orchestrator quyết định routing dựa trên HTTP status.
4. Để latency bị chặn bởi deadline và không cộng dồn tuần tự.
5. Ghi log lỗi rồi tiếp tục đóng tất cả client còn lại.

## Bài tập đề xuất

- Giả lập LLM health treo 30 giây và xác nhận `/ready` trả 503 trong khoảng timeout cấu hình.
- Giả lập Redis lỗi ở hai mode: cache-only phải vẫn ready; rate-limit-enabled phải not ready.
- Dùng mock client ghi lại thứ tự shutdown và xác nhận mọi `close()` đều được gọi dù một client ném exception.
