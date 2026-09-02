# Week 3.4 — Retrieval evaluation và practical validation

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt liveness, readiness và retrieval quality.
- Tính Precision@K, Recall@K và Reciprocal Rank/MRR.
- Kiểm chứng BM25, filter, fuzzy search, highlighting và pagination.

## Tóm tắt một phút

HTTP 200 chỉ chứng minh service sống; index có dữ liệu mới chứng minh retrieval sẵn sàng; relevance metrics mới cho biết retrieval có tốt không. `OR` thường tăng recall, `AND` tăng precision nhưng có thể bỏ sót synonym hoặc partial matches.

## Ba mức kiểm chứng

```text
Liveness  → OpenSearch phản hồi
Readiness → mapping/index/data sẵn sàng query
Quality   → kết quả đạt relevance metrics
```

## Metrics

- `Precision@K = relevant trong top K / K`
- `Recall@K = relevant tìm được / tổng relevant trong corpus`
- `RR = 1 / rank của kết quả relevant đầu tiên`
- `MRR` là trung bình RR trên nhiều query.

MRR phù hợp khi người dùng cần thấy ít nhất một kết quả đúng càng sớm càng tốt.

## Practical evidence

Index local `week3-bm25-lab` được tạo riêng với 6 documents; không gọi external embedding API và không thay đổi main hybrid index.

Query `retrieval augmented generation`:

- `OR`: 4 hits; relevant document đứng rank 1, score 12.70.
- `AND`: 1 hit; chỉ relevant document được giữ lại.
- `OR + cs.AI filter`: 2 hits; score document đầu vẫn 12.70, chứng minh filter không cộng score.
- Typo query `retrival generatoin`: fuzzy search vẫn tìm được relevant document ở rank 1.
- Highlighting đánh dấu cả `retrieval/retrieves` và `generation/generating` sau analysis.
- Pagination theo date trả các trang không trùng nhau.
- `QueryBuilder`: 8/8 unit tests pass.

Với nhãn OR `[R, N, N, N]`:

```text
Precision@4 = 1/4
Recall@4    = 1/1
RR          = 1/1
```

Với AND `[R]`:

```text
Precision@1 = 1/1
Recall@1    = 1/1
RR          = 1/1
```

## Production lessons

- Không mặc định dùng `AND`; nó có thể giảm recall trên query tự nhiên.
- Không kết luận latency từ một request; cần warm-up và p50/p95 trên nhiều lần chạy.
- Fuzziness tăng typo tolerance nhưng cũng mở rộng candidate set.
- Sort theo date có thể làm `_score` không còn quyết định thứ tự chính.
- Relevance label và query set phải phản ánh intent thực tế của người dùng.

## Câu hỏi ôn tập

1. Cluster green có chứng minh retrieval quality không?
2. Khi nào ưu tiên Precision@K, Recall@K hoặc MRR?
3. Vì sao `AND` có thể làm giảm recall?
4. Category filter có làm BM25 score tăng không?

<details>
<summary>Đáp án gợi ý</summary>

1. Không; cần dữ liệu, query thực tế và relevance metrics.
2. Precision cho độ sạch top K, recall cho độ bao phủ, MRR cho vị trí hit đúng đầu tiên.
3. Relevant documents có thể dùng synonym, paraphrase hoặc chỉ một phần query terms.
4. Không; filter chỉ loại document không đủ điều kiện.

</details>

## Checklist hoàn thành

- [x] Tính đúng Precision@K, Recall@K và RR.
- [x] So sánh OR, AND và filter bằng query thật.
- [x] Kiểm chứng fuzzy search, highlighting và pagination.
- [x] Chạy unit tests QueryBuilder thành công.
- [x] Phân biệt service health với retrieval quality.

**Trạng thái: Week 3 hoàn thành.**
