# Tổng kết Week 1 — Hạ tầng và hai luồng hệ thống

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Hiểu vai trò của từng service trong hệ thống RAG.
- Phân biệt offline ingestion path và online serving path.
- Phân tích ảnh hưởng khi một service gặp lỗi.

## Tóm tắt một phút

Ingestion tạo dữ liệu có thể tìm kiếm; serving dùng dữ liệu đã index để trả lời người dùng. Hai luồng được tách để lỗi ingestion không làm ngừng phục vụ dữ liệu cũ. PostgreSQL là source of truth, OpenSearch là retrieval index, còn Ollama chỉ đảm nhiệm generation.

## Hai luồng thực tế

### Ingestion — offline

```text
Airflow schedule
  → arXiv fetch + PDF download
  → PDF parsing
  → PostgreSQL
  → đọc paper từ PostgreSQL
  → chunking + passage embedding
  → OpenSearch
  → report + cleanup
```

Trong implementation hiện tại, paper được lưu vào PostgreSQL **trước**, sau đó indexing task mới đọc paper để chunk, embed và ghi OpenSearch.

### Serving — online

```text
User → FastAPI → Redis cache check
                 ├─ cache hit → response
                 └─ cache miss
                      → query embedding
                      → OpenSearch retrieval
                      → Ollama generation
                      → cache store + response
```

- PostgreSQL không được đọc trong request path `/ask` hiện tại.
- Nếu query embedding lỗi, hệ thống có thể fallback về BM25.
- Source PDF được tạo từ `arxiv_id`, không cần đọc nội dung PDF từ PostgreSQL.

## Failure isolation cần nhớ

- **Airflow/arXiv/PDF parser lỗi:** không có dữ liệu mới; dữ liệu đã index vẫn được serving.
- **PostgreSQL lỗi:** ingestion bị chặn. Serving đang chạy có thể tiếp tục nếu OpenSearch còn dữ liệu, nhưng Compose yêu cầu PostgreSQL healthy khi khởi động API.
- **Embedding lúc ingestion lỗi:** paper mới không được index vector.
- **Embedding lúc serving lỗi:** giảm chất lượng xuống BM25, không nhất thiết mất toàn bộ search.
- **OpenSearch lỗi:** retrieval mới thất bại; exact cached response vẫn có thể dùng nếu cache hit.
- **Ollama lỗi:** `/ask` không sinh được câu trả lời, nhưng `/hybrid-search/` vẫn có thể trả raw search results.
- **FastAPI lỗi:** single instance hiện tại ngừng phục vụ; production cần nhiều replica và load balancer.

## Airflow trên máy cấu hình hạn chế

Không bắt buộc chạy Airflow liên tục để hoàn thành mục tiêu học tập Week 1. Có thể thay bằng việc đọc DAG, giải thích schedule, dependencies, retry và failure isolation. Phần hands-on Airflow được hoãn đến khi có môi trường phù hợp hơn.

## Câu hỏi ôn tập

1. Vì sao phải lưu paper vào PostgreSQL trước khi tạo search index?
2. Query embedding lỗi có làm toàn bộ retrieval ngừng không?
3. PostgreSQL có nằm trong `/ask` request path hiện tại không?
4. Airflow lỗi có làm dữ liệu cũ trong OpenSearch biến mất không?
5. Khi Ollama lỗi, endpoint nào vẫn có thể trả kết quả tìm kiếm?

<details>
<summary>Đáp án gợi ý</summary>

1. PostgreSQL là source of truth, giúp indexing có thể chạy lại và tái tạo OpenSearch.
2. Không; hệ thống có thể fallback về BM25.
3. Không; `/ask` retrieval trực tiếp từ OpenSearch.
4. Không; chỉ việc cập nhật dữ liệu mới bị gián đoạn.
5. `/api/v1/hybrid-search/`.

</details>

## Bài tập thực hành đề xuất

Vẽ lại hai luồng mà không xem tài liệu, sau đó đánh dấu mỗi service là source, orchestrator, storage, retrieval, generation hoặc interface.

## Checklist tự đánh giá

- [x] Phân biệt được ingestion và serving.
- [x] Giải thích được vai trò của các service chính.
- [x] Phân tích được failure isolation.
- [x] Xác minh các service cốt lõi bằng notebook.
- [x] Hiểu vai trò Airflow qua DAG; hands-on được hoãn do giới hạn phần cứng.

**Trạng thái: Week 1 hoàn thành.**
