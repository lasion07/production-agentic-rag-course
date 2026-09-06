# Production 04 — Alembic và OpenSearch alias cutover

## Mục tiêu

Thay schema mutation lúc application startup bằng release jobs có thể review, kiểm thử và rollback có kiểm
soát.

## Tóm tắt một phút

- `Base.metadata.create_all()` không phải migration system: nó không biểu diễn lịch sử thay đổi hoặc data
  backfill.
- Alembic revision là artifact bất biến; deployment chạy `upgrade head` trước khi rollout application.
- Một legacy baseline có thể là no-op để nối lịch sử của database đã tồn tại; không được `stamp head` để bỏ
  qua DDL chưa chạy.
- OpenSearch mapping không thể sửa tùy ý trên index đang phục vụ. Tạo physical index mới, nạp/kiểm tra dữ
  liệu, rồi chuyển alias.
- Serving đọc qua `*-read`; ingestion ghi qua `*-write`. Một `_aliases` request chuyển cả hai alias nên không
  có cửa sổ một bên dùng schema cũ, một bên dùng schema mới.
- Rollback OpenSearch là trỏ alias về physical generation cũ đã giữ lại. Rollback PostgreSQL ưu tiên
  forward-fix hoặc restore backup sang database mới khi thay đổi dữ liệu có tính phá hủy.

## Luồng release

1. Backup PostgreSQL và OpenSearch snapshot.
2. Chạy Alembic migration job.
3. `prepare` physical OpenSearch generation mới và reindex dữ liệu.
4. So sánh count, mapping và chạy representative retrieval queries.
5. Atomic `cutover` read/write aliases.
6. Rollout application, canary và theo dõi lỗi/latency/relevance.
7. Nếu regress, `rollback` aliases và image; chỉ rollback database khi đã xác nhận compatibility.

## Invariants quan trọng

- API/worker startup không được tự tạo hoặc sửa PostgreSQL schema trong production.
- API và Airflow startup chỉ validate OpenSearch; `search-migrate` bootstrap là process riêng.
- Read alias và write alias phải cùng trỏ đúng một physical index.
- Candidate index rỗng bị từ chối cutover, trừ bootstrap được cho phép rõ ràng.
- Không xóa generation cũ trước khi hết rollback window.

## Bằng chứng thực hành

- PostgreSQL backup: `/private/tmp/rag-before-p0-04.dump` (254 KB).
- Alembic: legacy `5f2621c13b39` → consistency state `20260906_0001` → cleanup/integrity revisions → head `20260907_0004`; 7 paper được backfill `pending`, temporary defaults và unique index trùng được dọn mà vẫn giữ uniqueness.
- OpenSearch: legacy 81 chunks → `v1` đủ 81 chunks; BM25 smoke query trả đúng paper.
- Rollback drill: aliases `v1` → `v0` → `v1`; read/write alias luôn cùng target và cùng count 81.

## Câu hỏi ôn tập

1. Vì sao `create_all()` không thay thế Alembic?
2. Vì sao cần tách physical index name khỏi read/write alias?
3. Điều gì phải được kiểm tra trước atomic cutover?
4. Vì sao downgrade database không phải lúc nào cũng là rollback an toàn?

## Đáp án ngắn

1. Nó không có ordered revisions, data migration và reviewable rollback history.
2. Physical name mô tả schema generation; alias là stable serving contract.
3. Mapping, count, reindex failures và representative retrieval quality.
4. Downgrade có thể xóa column/data; restore backup hoặc forward-fix thường an toàn hơn.

## Bài tập đề xuất

- Tạo `v2`, copy dữ liệu từ read alias hiện hành, kiểm tra queries, cutover rồi rollback về `v1`.
- Fault injection: candidate rỗng, alias read/write lệch target, reindex có failures.
- Diễn tập restore PostgreSQL vào database tạm và OpenSearch snapshot vào cluster/index tạm.
