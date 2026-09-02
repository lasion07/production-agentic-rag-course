# Bài kiểm tra thường xuyên số 1 — Tổng hợp Week 1–4

Quay lại: [Mục lục sổ học tập](README.md)

## Thông tin bài kiểm tra

- Phạm vi: Infrastructure, ingestion, BM25/OpenSearch, chunking, embeddings và hybrid retrieval.
- Tổng điểm: **100**.
- Thời gian đề xuất: **60–75 phút**.
- Lần làm đầu: không xem ghi chú và không chạy code.
- Được dùng máy tính cho phép tính số học.
- Trả lời ngắn gọn nhưng phải nêu lý do ở các câu tình huống.

## Phần A — Kiến thức nền tảng (20 điểm)

Mỗi câu 2 điểm. Chọn một đáp án đúng nhất.

### Câu 1

Trong kiến trúc hiện tại, thành phần nào là source of truth cho paper?

A. Redis  
B. PostgreSQL  
C. OpenSearch  
D. Ollama

### Câu 2

Airflow scheduler ngừng hoạt động nhưng OpenSearch và FastAPI vẫn khỏe. Hiện tượng phù hợp nhất là:

A. Mọi request đang phục vụ lập tức thất bại  
B. Dữ liệu đã index biến mất  
C. Dữ liệu mới không được ingest, dữ liệu cũ vẫn có thể phục vụ  
D. Ollama tự động thay Airflow chạy ingestion

### Câu 3

Field `categories` dùng để filter chính xác giá trị `cs.AI` nên được mapping chính là:

A. `text`  
B. `keyword`  
C. `knn_vector`  
D. `date`

### Câu 4

Một `category filter` đặt trong filter context sẽ:

A. Tăng BM25 score của document phù hợp  
B. Giảm BM25 score của document phù hợp  
C. Loại document không phù hợp nhưng không trực tiếp cộng BM25 score  
D. Chuyển BM25 thành cosine similarity

### Câu 5

API trả `429 Too Many Requests` cùng `Retry-After: 20`. Hành vi đúng là:

A. Không retry  
B. Retry ngay lập tức liên tục  
C. Retry sau ít nhất 20 giây và vẫn áp dụng retry budget  
D. Rollback PostgreSQL rồi retry

### Câu 6

Sau khi một lệnh SQL làm SQLAlchemy session rơi vào failed transaction, cần làm gì trước khi xử lý paper tiếp theo?

A. Chỉ ghi log  
B. Rollback session  
C. Tăng parsing concurrency  
D. Xóa OpenSearch index

### Câu 7

Hai vector cùng có 1.024 chiều thì chắc chắn có thể so sánh ngữ nghĩa đúng với nhau.

A. Đúng  
B. Sai

### Câu 8

Nếu một relevant document bị cả BM25 và vector retriever bỏ khỏi candidate pool, RRF sẽ:

A. Tự tái tạo document đó  
B. Dùng PostgreSQL để bổ sung document  
C. Không thể đưa document đó vào kết quả cuối  
D. Luôn đưa document đó lên hạng 1

### Câu 9

Phát biểu đúng nhất về candidate K và final K là:

A. Luôn phải bằng nhau  
B. Candidate K phục vụ độ bao phủ trước reranking; final K là tập nhỏ gửi downstream  
C. Final K luôn lớn hơn candidate K  
D. Chỉ BM25 mới có candidate K

### Câu 10

OpenSearch trả HTTP 200 và cluster có status green chứng minh điều gì?

A. Retrieval quality chắc chắn tốt  
B. Mọi relevant document đều ở top-1  
C. Service đang phản hồi, nhưng vẫn cần kiểm tra readiness và relevance quality  
D. Hybrid retrieval tốt hơn BM25

## Phần B — Tính toán và diễn giải (25 điểm)

### Câu 11 — Chunking (7 điểm)

Một tài liệu có 2.300 từ, `chunk_size=600`, `overlap=100`; chunk cuối được phép ngắn hơn 600 từ.

1. Tính stride.  
2. Tính số chunks.  
3. Tính tổng số từ được đưa vào tất cả chunks, tính cả overlap.  
4. Tính số từ bị lặp do overlap.

### Câu 12 — Retrieval metrics (6 điểm)

Top-5 có nhãn:

```text
[N, R, N, R, N]
```

Toàn corpus có 4 relevant documents. Tính:

1. Precision@5.  
2. Recall@5.  
3. Reciprocal Rank.

### Câu 13 — RRF (6 điểm)

Với `c=60`:

```text
BM25:   A #1, B #2, C #3
Vector: C #1, A #2, D #3
```

1. Tính RRF score của A.  
2. Tính RRF score của C.  
3. A hay C xếp cao hơn? Giải thích ngắn gọn.

### Câu 14 — Ingestion counters (6 điểm)

Một batch có:

```text
papers_fetched  = 12
pdfs_downloaded = 10
pdfs_parsed     = 8
papers_stored   = 12
```

Giả sử metadata luôn được lưu kể cả khi PDF thất bại:

1. PostgreSQL có bao nhiêu paper chỉ có metadata?  
2. Bao nhiêu paper có parsed full text?  
3. Vì sao `papers_stored=12` không mâu thuẫn với `pdfs_parsed=8`?

## Phần C — Tình huống production (35 điểm)

### Câu 15 — PostgreSQL/OpenSearch không đồng bộ (10 điểm)

Một paper đã được cập nhật thành công trong PostgreSQL nhưng cập nhật OpenSearch thất bại.

Trình bày:

1. Hiện tượng người dùng có thể gặp.  
2. Dữ liệu/trạng thái nào cần lưu để phát hiện sai lệch.  
3. Cơ chế retry phù hợp.  
4. Cách hệ thống tự khắc phục nếu retry trực tiếp vẫn thất bại.

### Câu 16 — Retry classification (8 điểm)

Phân loại từng lỗi sau thành retry hoặc không retry, đồng thời nêu delay/chiến lược:

1. HTTP 400.  
2. HTTP 429 với `Retry-After: 20`.  
3. HTTP 503.  
4. Timeout của HTTP GET.

Cuối cùng, giải thích vì sao client retry và Airflow task retry cần chung retry budget.

### Câu 17 — Idempotency và monotonic update (7 điểm)

PostgreSQL đã có paper `X` với `pdf_processed=True` và full text tốt. Một lần retry cùng `arxiv_id=X` tải được metadata mới hơn nhưng PDF parsing thất bại.

Bạn sẽ upsert như thế nào để:

- Không tạo row trùng.
- Vẫn cập nhật metadata hợp lệ.
- Không làm mất full text tốt đã có.

### Câu 18 — Resource control (5 điểm)

MacBook bắt đầu swap mạnh và Docling workers thường xuyên bị kill, trong khi download vẫn ổn định. Bạn sẽ điều chỉnh concurrency và validation thế nào? Vì sao?

### Câu 19 — Serving degradation (5 điểm)

OpenSearch và FastAPI khỏe nhưng Ollama không phản hồi. Hệ thống nên trả gì cho người dùng và thành phần nào vẫn có thể hoạt động?

## Phần D — Thiết kế hệ thống (20 điểm)

### Câu 20 — Chống chunk monopolization (10 điểm)

Hybrid retrieval trả top-10 chunks nhưng cả 10 đều thuộc cùng một paper. Hãy thiết kế lại đoạn từ retrieval đến context construction. Câu trả lời phải đề cập:

- Candidate K và final K.
- Deduplication hoặc giới hạn chunks mỗi paper.
- Diversity/reranking.
- Ảnh hưởng đến token budget của LLM.

### Câu 21 — Embedding model migration (10 điểm)

Hệ thống đang dùng model 1.024 chiều. Bạn muốn chuyển sang model mới 768 chiều mà không làm gián đoạn serving.

Thiết kế một kế hoạch migration an toàn, bao gồm:

- OpenSearch mapping/index.
- Re-embedding corpus.
- Query embedding.
- Kiểm chứng chất lượng.
- Cutover và rollback.

## Thang đánh giá

- **90–100:** Nắm chắc Week 1–4, tư duy production tốt.
- **80–89:** Hiểu tốt, còn một vài khoảng trống nhỏ.
- **70–79:** Đạt yêu cầu, cần ôn lại một số trade-off hoặc failure mode.
- **60–69:** Nắm khái niệm nhưng thiết kế production chưa ổn định.
- **Dưới 60:** Cần ôn có hướng dẫn trước khi sang phần khó hơn.

Điểm đạt đề xuất: **70/100**, đồng thời không phần nào dưới 50% số điểm của phần đó.

## Mẫu nộp bài

Sao chép mẫu dưới đây vào chat và điền câu trả lời:

```text
PHẦN A
1. ...
2. ...
...
10. ...

PHẦN B
11. ...
12. ...
13. ...
14. ...

PHẦN C
15. ...
16. ...
17. ...
18. ...
19. ...

PHẦN D
20. ...
21. ...
```

Sau khi nộp, bài sẽ được chấm theo từng câu, kèm tổng điểm, nhận xét theo Week và kế hoạch ôn tập cá nhân hóa.
