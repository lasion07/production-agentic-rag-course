# Bài 01 — Đồng bộ PostgreSQL và OpenSearch

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt nguồn dữ liệu chính và chỉ mục tìm kiếm.
- Giải thích hậu quả khi hai hệ thống không đồng bộ.
- Đề xuất cơ chế retry, reconciliation và monitoring phù hợp.

## Tóm tắt một phút

PostgreSQL giữ dữ liệu gốc, còn OpenSearch giữ bản sao được tối ưu cho retrieval. Nếu cập nhật OpenSearch thất bại, RAG có thể trả lời bằng dữ liệu cũ. Hệ thống production cần versioning, idempotent indexing, retry có backoff, dead-letter queue, cảnh báo và reconciliation định kỳ.

## Kiến thức cốt lõi

### Vai trò

- **PostgreSQL**: nguồn dữ liệu chính (*source of truth*).
- **OpenSearch**: bản sao phục vụ BM25, vector và hybrid retrieval.

Nếu OpenSearch bị mất, có thể tái tạo index từ PostgreSQL. Chiều ngược lại không nên được xem là an toàn.

### Khi cập nhật OpenSearch thất bại

Người dùng có thể nhận nội dung cũ, không tìm thấy paper mới, hoặc thấy metadata và chunks không đồng nhất.

Đây là bài toán **eventual consistency** giữa database và search index.

## Luồng xử lý đề xuất

1. Cập nhật paper trong PostgreSQL và tăng `content_version`.
2. Đánh dấu `index_status = pending`.
3. Upsert vào OpenSearch theo ID ổn định và version.
4. Nếu thất bại, retry tối đa 3 lần với exponential backoff.
5. Nếu vẫn thất bại, ghi lỗi, đưa vào dead-letter queue và gửi cảnh báo.
6. Chạy reconciliation job định kỳ để tìm và re-index các paper có `content_version != indexed_version`.

```text
PostgreSQL update
      ↓
index_status = pending
      ↓
OpenSearch upsert
  ├─ Thành công → indexed
  └─ Thất bại → retry → dead-letter queue + alert
```

## Nguyên tắc cần nhớ

- Indexing phải **idempotent**: chạy lại không tạo chunks trùng lặp.
- Chỉ xóa hoặc vô hiệu hóa chunks cũ sau khi version mới index thành công.
- Theo dõi số job `pending`, `failed`, độ trễ indexing và document-count drift.

> PostgreSQL là dữ liệu gốc. OpenSearch là bản sao phục vụ tìm kiếm và phải có khả năng tái tạo.

## Lỗi thiết kế thường gặp

- Retry liên tục không có backoff.
- Dùng ID ngẫu nhiên khiến mỗi lần retry tạo thêm chunks trùng lặp.
- Xóa index cũ trước khi version mới được index thành công.
- Chỉ ghi log nhưng không có cảnh báo hoặc reconciliation job.

## Câu hỏi ôn tập

1. Vì sao OpenSearch không nên là source of truth?
2. Người dùng thấy gì khi PostgreSQL đã cập nhật nhưng OpenSearch vẫn giữ version cũ?
3. `content_version` và `indexed_version` giúp phát hiện vấn đề nào?
4. Vì sao retry indexing phải idempotent?
5. Sau ba lần retry thất bại, hệ thống nên làm gì?

<details>
<summary>Đáp án gợi ý</summary>

1. OpenSearch là chỉ mục dẫn xuất, tối ưu cho tìm kiếm và có thể được tái tạo từ dữ liệu gốc.
2. Kết quả retrieval có thể cũ, thiếu paper hoặc chứa metadata và chunks không đồng nhất.
3. Phát hiện paper chưa được index đúng phiên bản mới nhất.
4. Để chạy lại an toàn mà không tạo dữ liệu hoặc chunks trùng lặp.
5. Ghi nhận trạng thái `failed`, đưa job vào dead-letter queue, cảnh báo và để reconciliation job xử lý lại.

</details>

## Bài tập thực hành đề xuất

- Thiết kế schema tối thiểu gồm `content_version`, `indexed_version`, `index_status`, `index_attempts` và `last_index_error`.
- Viết pseudo-code cho một indexing worker có tối đa ba lần retry với exponential backoff.
- Xác định ba metric bạn sẽ đưa lên dashboard vận hành.

## Checklist tự đánh giá

- [ ] Tôi phân biệt được source of truth và search index.
- [ ] Tôi giải thích được eventual consistency bằng một ví dụ.
- [ ] Tôi hiểu retry, idempotency và dead-letter queue giải quyết vấn đề gì.
- [ ] Tôi biết cách chủ động phát hiện dữ liệu lệch bằng reconciliation job.
