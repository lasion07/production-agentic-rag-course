# Production 02 — Deployment boundary

## Mục lục

1. Development và production khác nhau ở đâu
2. Boundary đã thiết kế
3. Secret, TLS và least privilege
4. Runtime hardening
5. Câu hỏi ôn tập

## 1. Development và production khác nhau ở đâu

Development Compose ưu tiên tiện học: publish nhiều port, credential dễ nhớ và service tự khởi tạo.
Production ưu tiên giảm blast radius: chỉ ingress public, backend private, secret nằm ngoài image/source và
startup phải fail nếu cấu hình không an toàn.

## 2. Boundary đã thiết kế

- Caddy nhận traffic Internet và terminate TLS; API chỉ `expose` trên internal network.
- PostgreSQL, Redis, OpenSearch và Langfuse là managed/private dependencies, không nằm trên public host port.
- Airflow production profile chỉ chạy scheduler; không public web UI.
- `compose.yml` cũ được giữ nguyên cho bài học nhưng được đánh dấu development-only.

## 3. Secret, TLS và least privilege

- Docker secret là file mount, không phải giá trị được bake vào image hay ghi thẳng trong Compose.
- Entrypoint chuyển `*_FILE` sang environment theo allowlist rồi `exec` process chính.
- PostgreSQL dùng `sslmode=verify-full`; Redis và OpenSearch vừa mã hóa TLS vừa verify CA.
- Mã hóa mà không verify certificate vẫn có thể bị man-in-the-middle.
- Service account chỉ nên có quyền trên database/index cần dùng, không dùng tài khoản admin.

## 4. Runtime hardening

- API UID/GID `10001`; Airflow UID/GID `50000`.
- Root filesystem read-only; chỉ các tmpfs cần thiết được ghi.
- Drop capabilities, bật `no-new-privileges`, đặt PID/CPU/RAM limit và termination grace period.
- Dùng immutable image tag/digest để rollback đúng phiên bản.

## 5. Câu hỏi ôn tập

1. Vì sao `ports` cho PostgreSQL nguy hiểm hơn `expose` nội bộ?
2. TLS encryption khác certificate verification như thế nào?
3. Vì sao secret environment trong Compose vẫn kém hơn secret file/secret manager?
4. Read-only root filesystem giúp hạn chế hậu quả khi process bị khai thác ra sao?
5. Vì sao production scheduler không nên tự chạy database migration khi mỗi replica khởi động?

Gợi ý thực hành: render `compose.production.yml`, kiểm tra chỉ gateway có `ports`, rồi cố tình đổi
OpenSearch sang HTTP hoặc Redis tắt TLS và quan sát `Settings` từ chối startup.
