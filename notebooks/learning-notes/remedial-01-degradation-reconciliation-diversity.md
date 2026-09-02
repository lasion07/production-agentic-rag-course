# Bài phụ đạo 1 — Degradation, reconciliation và context diversity

Quay lại: [Mục lục](README.md) · [Kết quả kiểm tra số 1](assessment-01-weeks1-4-result.md)

## Kết quả tái đánh giá

**8,5/10 — Đạt mục tiêu củng cố**

- Graceful degradation: **3/3**
- Consistency reconciliation: **2,5/3**
- Context diversity: **3/4**

## 1. Graceful degradation

Mục tiêu không phải luôn trả HTTP 200, mà là giữ lại năng lực còn đáng tin cậy và mô tả đúng chế độ thực tế.

```text
Redis lỗi            → bỏ cache, tiếp tục
Query embedding lỗi  → BM25 + LLM, actual_mode=bm25
Ollama lỗi           → raw retrieval/degraded response hoặc 503
OpenSearch lỗi       → cache hit nếu có; nếu không thì 503
```

Không được biến OpenSearch timeout thành “không tìm thấy tài liệu”: empty result là kết quả nghiệp vụ, timeout là trạng thái không biết kết quả.

### Code hiện tại

- Redis failure được bỏ qua.
- Embedding failure fallback BM25.
- `/ask` chưa trả raw retrieval khi Ollama lỗi.
- `search_mode` có thể báo `hybrid` dù thực tế đã fallback BM25.

## 2. Consistency reconciliation

**Reconciliation job** là thành phần chạy định kỳ để so sánh:

```text
source_version/content_hash trong PostgreSQL
                  với
indexed_version/indexed_hash trong OpenSearch/index state
```

Nếu `source_version=12 > indexed_version=11` dù status đang là `indexed`, job phải sửa status và requeue version 12. Khi retry cạn, chuyển DLQ và alert.

Luồng an toàn:

```text
stage/index v12
→ verify đủ chunks + đúng model/version
→ chuyển active version sang v12
→ xóa v11 sau cùng
```

Không xóa v11 trước vì index v12 có thể lỗi, tạo khoảng trống retrieval.

## 3. Context diversity

Với candidates:

```text
A1, A2, A3, B1, C1, A4
```

`final_K=4`, `max_chunks_per_paper=2` có thể tạo:

```text
A1, A2, B1, C1
```

Nếu A2 gần như trùng A1:

- Không nhất thiết hạ toàn hệ thống xuống một chunk mỗi paper.
- Thử A3 nếu A3 bổ sung nội dung mới.
- Nếu mọi A-chunk còn lại đều trùng, chọn `A1, B1, C1` rồi lấy sâu hơn để tìm D1.
- Nếu không có candidate đa dạng phù hợp, trả ba chunks tốt còn hơn nhồi một duplicate chỉ để đủ K.

Pipeline đề xuất:

```text
candidate_K lớn
→ rerank
→ near-duplicate removal
→ max chunks per paper
→ MMR/diversity
→ token-budget packing
→ final context
```

## Ba quy tắc ghi nhớ

1. **Degrade truthfully:** báo đúng năng lực thực tế; unknown không phải empty.
2. **Reconcile by version:** status một mình không chứng minh hai storage đồng bộ.
3. **Diversity before quantity:** final K là giới hạn tối đa, không phải chỉ tiêu bắt buộc phải lấp đầy.

## Câu hỏi ôn nhanh

1. Jina lỗi nhưng BM25 khỏe thì actual search mode là gì?
2. Thành phần nào phát hiện `source_version > indexed_version` sau khi retry flow đã bỏ sót lỗi?
3. Vì sao ba chunks tốt, khác nhau có thể tốt hơn bốn chunks với một duplicate?

<details>
<summary>Đáp án</summary>

1. BM25/degraded mode.
2. Reconciliation job.
3. Duplicate tốn token nhưng cung cấp ít thông tin mới và có thể khuếch đại một nguồn.

</details>

**Trạng thái: Hoàn thành bài phụ đạo.**
