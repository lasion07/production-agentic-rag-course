# Production 03 — Consistency và reconciliation

## Mục lục

1. Tóm tắt một phút
2. Durable state
3. Idempotency và safe replacement
4. Reconciliation worker
5. Câu hỏi ôn tập

## 1. Tóm tắt một phút

PostgreSQL là source of truth; OpenSearch là serving projection. Mỗi paper có `source_version` và
`indexed_version`. Khi `source_version > indexed_version`, hệ thống biết dữ liệu search đang chậm hơn nguồn và
có thể tự sửa, thay vì chờ người dùng phát hiện câu trả lời cũ.

## 2. Durable state

State machine chính:

`pending → indexing → indexed`

Khi lỗi:

`indexing → retry_pending → indexing → dead_letter`

Các field cốt lõi:

- `source_version`: version mới nhất trong PostgreSQL.
- `indexed_version`: version hoàn chỉnh đã được kích hoạt trong OpenSearch.
- `index_status`, `index_attempts`: trạng thái và retry budget.
- `last_index_attempt_at`, `index_lease_expires_at`, `next_index_retry_at`: chống worker chết hoặc claim trùng.
- `last_index_error`: lỗi đã sanitize để vận hành điều tra.

Invariant: `0 ≤ indexed_version ≤ source_version`. Duplicate delivery không đổi nội dung thì không tăng version.

## 3. Idempotency và safe replacement

Chunk ID có dạng `<paper_id>:v<source_version>:c<chunk_index>`. Replay cùng event ghi đè đúng document thay vì
tạo duplicate.

Mỗi indexing attempt giữ một `index_claim_token`. Worker chỉ được ghi nhận thành công/thất bại nếu token
vẫn còn là token hiện hành, nên worker cũ không thể xác nhận thay cho source version mới. P0-03 không dùng
`is_active/update_by_query`, vì thao tác đó không tạo atomic boundary cho cả paper. Atomic visibility được
chuyển sang P0-04 với physical index có version và alias cutover.

## 4. Reconciliation worker

Worker chạy định kỳ:

1. Chọn paper lệch version và đã đến hạn retry; dùng row lock để tránh claim trùng.
2. Ghi `indexing`, tăng attempt và đặt lease trước khi gọi dịch vụ ngoài.
3. Index thành công và claim vẫn hợp lệ thì cập nhật `indexed_version`.
4. Lỗi thì rollback session, ghi lỗi và exponential backoff.
5. Hết retry budget thì ghi `dead_letter` và phát critical alert hook.

Nếu worker chết giữa bước 2–3, lease hết hạn sẽ khiến worker sau claim lại. Deterministic IDs làm replay an toàn.

## 5. Câu hỏi ôn tập

1. Vì sao chỉ có `index_status=indexed` nhưng không có hai version vẫn chưa đủ phát hiện stale data?
2. Tại sao phải commit trạng thái claim trước khi gọi embedding/OpenSearch?
3. Nếu partial bulk index tạo 7/10 chunks, retrieval có được thấy 7 chunks đó không?
4. Lease khác retry delay như thế nào?
5. Vì sao exact paper IDs tốt hơn truy vấn “N paper mới nhất” sau ingestion?

Đề xuất thực hành: inject lỗi partial bulk, crash sau OpenSearch nhưng trước PostgreSQL acknowledgement, rồi replay
cùng version. Kiểm tra chunk count không tăng, last-good version vẫn searchable và state cuối trở về `indexed`.
