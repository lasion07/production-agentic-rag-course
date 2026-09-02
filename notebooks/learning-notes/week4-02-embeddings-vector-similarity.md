# Week 4.2 — Embeddings và vector similarity

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Hiểu embedding biểu diễn ngữ nghĩa như thế nào.
- Phân biệt passage embedding và query embedding.
- Hiểu điều kiện để so sánh vector bằng cosine similarity.
- Nhận biết điểm mạnh, điểm yếu của BM25, vector và hybrid retrieval.

## Tóm tắt một phút

Embedding biến text thành vector trong một không gian ngữ nghĩa. Query và passage gần nghĩa sẽ có vector gần nhau dù không dùng cùng từ. Trong dự án, Jina v3 tạo vector 1.024 chiều với hai task `retrieval.query` và `retrieval.passage`. Hai phía phải dùng cùng model/version và không gian tương thích; chỉ có cùng số chiều là chưa đủ.

## Luồng embedding

```text
Paper chunk --retrieval.passage--> vector 1.024 chiều --index--> OpenSearch
User query --retrieval.query------> vector 1.024 chiều --search-> k-NN
```

Passage và query có vai trò bất đối xứng nên dùng task khác nhau, nhưng model được huấn luyện để đặt chúng trong cùng retrieval space.

## Cosine similarity

```text
cos(q, d) = (q · d) / (||q|| × ||d||)
```

- Đo độ giống nhau về hướng, không dựa trực tiếp vào số keyword trùng.
- Giá trị càng lớn thì hai vector thường càng gần về ngữ nghĩa.
- Vector khác số chiều không thể thực hiện dot product/cosine similarity.
- Vector cùng số chiều nhưng đến từ hai model hoặc hai version không tương thích vẫn có thể cho similarity vô nghĩa.

## BM25, vector và hybrid

- **BM25:** mạnh với exact terms, identifier, model name, error code và thuật ngữ hiếm.
- **Vector:** mạnh với synonym, paraphrase và câu hỏi diễn đạt khác tài liệu.
- **Hybrid:** lấy ứng viên từ cả hai nhánh rồi hợp nhất thứ hạng.

Hybrid không đơn giản là cộng trực tiếp BM25 score với cosine score vì hai thang điểm khác nhau. Implementation hiện tại dùng **Reciprocal Rank Fusion (RRF)**, tức kết hợp dựa trên vị trí xếp hạng của mỗi nhánh.

## Cấu hình trong dự án

- Model: `jina-embeddings-v3`
- Dimension: `1024`
- Passage task: `retrieval.passage`
- Query task: `retrieval.query`
- Vector type: `float`
- OpenSearch field: `knn_vector`
- Similarity space: `cosinesimil`
- ANN algorithm: HNSW

Một vector float32 1.024 chiều cần khoảng 4 KiB dữ liệu thô; storage thực tế lớn hơn do metadata và HNSW graph.

## Lỗi thiết kế thường gặp

- Đổi embedding model nhưng không re-index toàn bộ corpus.
- Chỉ kiểm tra dimension mà bỏ qua model/version/task compatibility.
- Dùng một dummy vector giống nhau cho mọi text rồi kết luận vector retrieval hoạt động.
- Cộng BM25 score và vector score trực tiếp mà không normalize hoặc rank-fuse.
- Không fallback về BM25 khi external embedding API lỗi.
- Đánh giá bằng vài query thuận lợi thay vì một retrieval evaluation set.

## Câu hỏi ôn tập

1. Vì sao passage và query dùng task khác nhau nhưng vẫn so sánh được?
2. Cùng 1.024 chiều đã đủ bảo đảm hai vector tương thích chưa?
3. Khi nào BM25 có thể tốt hơn vector search?
4. Vì sao hybrid ranking cần normalization hoặc rank fusion?

<details>
<summary>Đáp án gợi ý</summary>

1. Model được huấn luyện cho asymmetric retrieval và ánh xạ hai vai trò vào cùng không gian.
2. Chưa; chúng còn phải đến từ model/version và retrieval space tương thích.
3. Khi query chứa exact identifier, mã lỗi, tên riêng hoặc thuật ngữ hiếm.
4. Vì BM25 và vector similarity có thang điểm khác nhau, không nên cộng thô.

</details>

## Bài tập thực hành đề xuất

Với cùng một query, chạy BM25, vector và hybrid search; ghi lại top-K, đánh dấu relevant/non-relevant rồi so sánh Precision@K, Recall@K và RR.

## Checklist tự đánh giá

- [x] Phân biệt lexical match và semantic match.
- [x] Giải thích được passage/query embedding.
- [x] Nêu được điều kiện tương thích vector.
- [x] Giải thích được vai trò của hybrid retrieval.

**Trạng thái: Week 4.2 hoàn thành.**
