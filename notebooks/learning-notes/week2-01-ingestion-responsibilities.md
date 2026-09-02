# Week 2.1 — Trách nhiệm thành phần và graceful degradation

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt trách nhiệm của client, parser, orchestrator và repository.
- Hiểu partial success và graceful degradation trong ingestion pipeline.
- Không nhầm số paper được lưu với số PDF được xử lý thành công.

## Tóm tắt một phút

`MetadataFetcher` điều phối pipeline nhưng giao HTTP cho `ArxivClient`, parsing cho `PDFParserService` và database cho `PaperRepository`. PDF lỗi không làm mất metadata: paper vẫn được lưu với `pdf_processed=False` để có thể xử lý lại sau.

## Luồng cốt lõi

```text
fetch metadata
  → download PDF có giới hạn concurrency
  → parse PDF có giới hạn concurrency
  → lưu toàn bộ metadata vào PostgreSQL
       ├─ parse thành công → metadata + full text
       └─ parse thất bại  → metadata only
```

## Cơ chế quan trọng

- `asyncio.Semaphore`: giới hạn số download và parse đồng thời.
- `asyncio.gather(..., return_exceptions=True)`: cô lập lỗi của từng paper.
- `arxiv_id`: khóa dùng để upsert, tránh tạo paper trùng khi chạy lại.
- `pdf_processed=False`: đánh dấu paper cần xử lý PDF lại.

## Ví dụ

Với 10 metadata, 2 download lỗi và 1 parse lỗi:

```text
papers_fetched  = 10
pdfs_downloaded = 8
pdfs_parsed     = 7
papers_stored   = 10
full text       = 7
metadata only   = 3
```

Nếu `process_pdfs=False`, cả 10 paper vẫn được lưu và đều có `pdf_processed=False`.

## Lỗi tư duy thường gặp

- Cho rằng PDF lỗi thì paper không được lưu.
- Rollback toàn batch vì một paper lỗi.
- Nhầm orchestrator với component thực hiện HTTP, parsing hoặc SQL.
- Chỉ đếm success mà không lưu danh sách item thất bại để retry.

## Câu hỏi ôn tập

1. Vì sao `papers_stored` có thể lớn hơn `pdfs_parsed`?
2. `return_exceptions=True` giúp pipeline như thế nào?
3. Paper parse thất bại nên được lưu với trạng thái gì?
4. Vì sao không nên rollback toàn batch khi một PDF lỗi?

<details>
<summary>Đáp án gợi ý</summary>

1. Metadata vẫn có thể được lưu dù PDF chưa parse thành công.
2. Nó cho phép các item khác tiếp tục và trả lỗi theo từng paper.
3. Lưu metadata với `pdf_processed=False` để retry sau.
4. Rollback làm mất partial success và lãng phí network, CPU cùng thời gian đã sử dụng.

</details>

## Bài tập thực hành đề xuất

Mô phỏng một batch năm paper có hai parser failure, rồi viết kết quả mong đợi cho các counters và trạng thái database.

## Checklist tự đánh giá

- [x] Phân biệt được trách nhiệm của bốn thành phần chính.
- [x] Hiểu graceful degradation và partial success.
- [x] Tính đúng counters khi PDF processing bị lỗi.
- [x] Giải thích được vì sao metadata vẫn phải được lưu.

**Trạng thái: Week 2.1 hoàn thành.**
