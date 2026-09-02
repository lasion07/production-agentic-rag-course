# Week 4.3 — HNSW, k-NN và RRF

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Hiểu vì sao vector search trong production thường dùng ANN.
- Nắm vai trò của HNSW và các tham số chính.
- Tính và giải thích Reciprocal Rank Fusion.
- Hiểu giới hạn của candidate generation và rank fusion.

## Tóm tắt một phút

HNSW tìm hàng xóm gần đúng để đổi một phần độ chính xác lấy tốc độ và khả năng mở rộng. BM25 và vector search tạo hai danh sách ứng viên; RRF hợp nhất chúng theo thứ hạng thay vì cộng trực tiếp hai loại score khác thang đo. RRF chỉ có thể xếp hạng những tài liệu đã được ít nhất một retriever tìm thấy.

## HNSW và k-NN

Mapping hiện tại:

- Vector field: `knn_vector`
- Dimension: `1024`
- Similarity: cosine
- ANN algorithm: HNSW
- `m = 16`
- `ef_construction = 512`

Trade-off:

- `m` lớn: graph dày hơn, thường tăng recall nhưng tốn RAM/storage và thời gian index.
- `ef_construction` lớn: xây index kỹ hơn, thường tăng recall nhưng indexing chậm hơn.
- Candidate `k` lớn: tăng cơ hội tìm relevant documents nhưng tăng search cost.

## Reciprocal Rank Fusion

```text
RRF(d) = Σ 1 / (c + rank_i(d))
```

Dự án dùng `c = 60`. Ví dụ:

```text
BM25:   A #1, B #2, C #3
Vector: B #1, D #2, A #3

RRF(A) = 1/61 + 1/63 ≈ 0.0323
RRF(B) = 1/62 + 1/61 ≈ 0.0325
```

B đứng cao hơn A. C chỉ xuất hiện trong BM25 nên có `1/63 ≈ 0.0159`, thấp hơn các document được cả hai retriever ủng hộ.

## Candidate pool là giới hạn cứng

```text
BM25 candidates ─┐
                 ├─ union ─ RRF ─ final top-K
Vector candidates┘
```

- ANN bỏ sót một relevant document nhưng BM25 tìm thấy: RRF vẫn có thể giữ document đó.
- Cả BM25 và vector đều bỏ sót: RRF không thể phục hồi.
- Document có mặt trong candidate pool vẫn có thể bị loại nếu final top-K quá nhỏ.

Vì vậy phải phân biệt:

1. **Candidate recall:** relevant item có lọt vào tập ứng viên không?
2. **Ranking quality:** nếu đã lọt vào, nó được xếp ở vị trí nào?

## Lỗi thiết kế thường gặp

- Chỉ tune fusion nhưng candidate pool quá nhỏ.
- Tăng HNSW recall mà không đo latency và memory.
- Cho rằng ANN luôn trả exact nearest neighbors.
- So sánh raw BM25 score và cosine score trực tiếp.
- Chỉ đo Precision@K, không kiểm tra candidate recall.

## Câu hỏi ôn tập

1. Vì sao HNSW được gọi là approximate search?
2. RRF giải quyết vấn đề gì của hybrid retrieval?
3. RRF có thể phục hồi document bị cả BM25 và vector bỏ sót không?
4. Candidate `k` và final `K` khác nhau như thế nào?

<details>
<summary>Đáp án gợi ý</summary>

1. Nó duyệt graph để tìm nhanh các hàng xóm gần đúng, không quét chính xác toàn bộ vector.
2. Hợp nhất các bảng xếp hạng có thang score khác nhau.
3. Không, document đó không có trong đầu vào của fusion.
4. Candidate `k` là số ứng viên mỗi retriever cung cấp; final `K` là số kết quả trả cho downstream/user.

</details>

## Bài tập thực hành đề xuất

Chạy cùng một evaluation query qua BM25, vector và RRF; so sánh candidate recall, Precision@K, Recall@K, RR và latency.

## Checklist tự đánh giá

- [x] Giải thích được HNSW trade-off.
- [x] Tính đúng RRF score.
- [x] Hiểu document được nhiều retriever ủng hộ thường có lợi thế.
- [x] Phân biệt lỗi candidate generation và lỗi ranking.

**Trạng thái: Week 4.3 hoàn thành.**
