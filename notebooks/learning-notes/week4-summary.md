# Tổng kết Week 4 — Chunking, embeddings và hybrid retrieval

Quay lại: [Mục lục sổ học tập](README.md)

## Những năng lực đã đạt được

- Tính chunk size, overlap, stride, duplication và trade-off.
- Phân tích section-aware chunking bằng implementation thật.
- Hiểu passage/query embedding và cosine similarity.
- Giải thích HNSW, candidate generation và ANN trade-off.
- Tính RRF và phân biệt candidate recall với ranking quality.
- Chạy end-to-end real embeddings → OpenSearch → FastAPI hybrid search.
- Đọc retrieval metrics và nhận biết evaluation dataset quá dễ.
- Phát hiện chunk monopolization và paper-length exposure bias.

## Luồng Week 4 hoàn chỉnh

```text
PostgreSQL papers
  → section-aware chunking
  → Jina retrieval.passage embeddings
  → OpenSearch BM25 + HNSW index

User query
  → Jina retrieval.query embedding
  → BM25 candidates + vector candidates
  → RRF
  → deduplicate/diversify/rerank
  → final context cho LLM
```

## Nguyên tắc production cần nhớ

1. Chunking là retrieval design, không chỉ là cắt text.
2. Cùng dimension chưa đủ; embedding model/version/space phải tương thích.
3. Hybrid cần fusion vì BM25 và vector score khác thang đo.
4. RRF không thể cứu document bị mọi retriever bỏ sót.
5. Candidate K nên lớn để giữ recall; final K nên nhỏ, đa dạng và phù hợp token budget.
6. Metrics đẹp trên corpus nhỏ không phải bằng chứng production quality.
7. Phải đánh giá diversity và bias theo paper, không chỉ theo chunk.

## Bằng chứng hoàn thành

- 3 papers, 81 chunks, 81 real Jina embeddings, 0 indexing errors.
- OpenSearch HNSW và native RRF pipeline hoạt động.
- FastAPI hybrid endpoint trả HTTP 200.
- 6/6 evaluation queries đưa relevant paper lên hạng 1.
- Unit kiến thức 4.1–4.4 và phân tích failure/trade-off đã hoàn thành.

## Việc nên cải tiến sau khóa học

- Thêm max-chunks-per-paper hoặc MMR trước LLM.
- Xây evaluation set lớn hơn và có failure slices.
- Thêm retry/backoff cho lỗi Jina có thể retry; fail fast với 401/403.
- Ghi `embedding_model` và version để hỗ trợ re-index migration.
- Sửa kiểm tra tồn tại của RRF search pipeline.

**Trạng thái: Week 4 hoàn thành.**
