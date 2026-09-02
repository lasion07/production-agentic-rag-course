# Kết quả bài kiểm tra thường xuyên số 1 — Week 1–4

Quay lại: [Đề kiểm tra](assessment-01-weeks1-4.md) · [Mục lục](README.md)

## Kết quả

**Tổng điểm: 81/100 — Đạt**

- Phần A — Kiến thức nền tảng: **20/20**
- Phần B — Tính toán và diễn giải: **22/25**
- Phần C — Tình huống production: **23/35**
- Phần D — Thiết kế hệ thống: **16/20**

Không phần nào dưới 50%, đáp ứng điều kiện đạt của bài kiểm tra.

## Chấm chi tiết

### Phần A — 20/20

Câu 1–10 đều đúng. Học viên nắm chắc source of truth, failure isolation, mapping/filter, retry classification, transaction rollback, vector compatibility, RRF candidate pool và ba mức health/readiness/quality.

### Phần B — 22/25

- **Câu 11: 6/7.** Kết quả đúng: stride 500, 5 chunks, 2.700 indexed words, 400 duplicated words. Công thức phải dùng `(num_chunks - 1) × overlap`, không phải `× stride`.
- **Câu 12: 4/6.** Precision@5 = 2/5 và Recall@5 = 2/4 đúng. Relevant đầu tiên ở rank 2 nên `RR = 1/2 = 0,5`, không phải 2.
- **Câu 13: 6/6.** A ≈ 0,0325; C ≈ 0,0323; A đứng cao hơn.
- **Câu 14: 6/6.** Có 4 metadata-only papers và 8 papers có parsed full text; lưu metadata độc lập với parsing nên counters không mâu thuẫn.

### Phần C — 23/35

- **Câu 15: 6/10.** Retry hai cấp hợp lý. Vì đây là paper đã được cập nhật, triệu chứng chính thường là retrieval trả **bản cũ**, không nhất thiết mất hoàn toàn paper. Chỉ `index_status` chưa đủ: cần source/index version hoặc content hash, `updated_at/indexed_at`, attempts và last error. Sau khi retry cạn, cần DLQ/outbox và reconciliation job định kỳ, không chỉ tiếp tục retry task.
- **Câu 16: 6/8.** Phân loại 400, 429 và 503 đúng. Timeout của idempotent GET có thể retry với exponential backoff + jitter; không nên mặc định tăng response timeout sau mỗi lần. Shared budget còn ngăn số lần retry nhân lên giữa client và Airflow, tránh tăng tải lên dependency đang lỗi.
- **Câu 17: 7/7.** Dùng cùng `arxiv_id`, cập nhật metadata hợp lệ và giữ nguyên full text tốt là monotonic update đúng.
- **Câu 18: 2/5.** Giảm parsing concurrency là đúng nhưng còn thiếu validation trước parsing: MIME/magic bytes, file size, page count, corruption, timeout và resource limits. Download concurrency không cần giảm cùng mức nếu network path vẫn ổn.
- **Câu 19: 2/5.** Ingestion có thể vẫn chạy nhưng không phải graceful serving chính. FastAPI/OpenSearch vẫn có thể trả raw retrieval results qua hybrid-search; `/ask` nên dùng cached answer nếu có, hoặc trả degraded response/503 rõ ràng thay vì giả lập câu trả lời.

### Phần D — 16/20

- **Câu 20: 9/10.** Đã có candidate K lớn, rerank/diversify, max chunks per paper và final K theo token budget. Cần biến giới hạn linh hoạt thành policy có thể đo/test, ví dụ retrieve 50 → MMR/rerank → tối đa 2 chunks/paper → final 8.
- **Câu 21: 7/10.** New index, re-embedding, matching query model, shadow test, cutover và rollback đều đúng hướng. Không nhất thiết tạo cluster mới; thường tạo versioned index mới trong cùng cluster. Nên dual-write/backfill, dùng alias để cutover/rollback, và so relevance metrics/latency với labeled eval set thay vì yêu cầu output mới giống output cũ 95%.

## Điểm mạnh

- Hiểu chắc kiến trúc ingestion/serving và failure isolation.
- Phân loại tốt retryable/non-retryable errors.
- Nắm đúng idempotency, transaction rollback và monotonic update.
- Hiểu candidate generation, RRF và chunk diversity.
- Có tư duy migration theo shadow/cutover/rollback.

## Nội dung cần ôn lại

1. Phân biệt rank với reciprocal rank; kiểm tra công thức trước khi thay số.
2. Reconciliation/outbox/DLQ cho PostgreSQL–OpenSearch consistency.
3. Retry delay, timeout và retry budget là ba khái niệm khác nhau.
4. PDF validation phải đi cùng concurrency control.
5. Serving degradation: cache, raw retrieval fallback và explicit 503.
6. Versioned index + alias cho embedding migration.

## Kế hoạch ôn tập cá nhân hóa

### Bài ôn 1 — Metrics, 15 phút

Tính Precision@K, Recall@K, RR và MRR cho ba ranking khác nhau; luôn viết công thức trước kết quả.

### Bài ôn 2 — Consistency, 20 phút

Vẽ state machine `pending → indexed | failed → retrying → dead-letter`, thêm `source_version`, `indexed_version` và reconciliation job.

### Bài ôn 3 — Graceful degradation, 15 phút

Lập ma trận lỗi cho query embedding, OpenSearch, Ollama và Redis; ghi rõ HTTP response và fallback của từng trường hợp.

### Bài ôn 4 — Migration, 20 phút

Vẽ luồng `index-v1 → dual write/backfill index-v2 → shadow eval → alias cutover → alias rollback`.

## Kết luận

Học viên đủ nền tảng để tiếp tục Week 5. Trước bài generation layer, nên ưu tiên ôn graceful degradation và context diversity vì hai nội dung này ảnh hưởng trực tiếp đến complete RAG serving.

**Trạng thái: Đạt — 81/100.**
