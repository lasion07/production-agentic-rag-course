# Tổng kết Week 2 — Production ingestion pipeline

Quay lại: [Mục lục sổ học tập](README.md)

## Tóm tắt một phút

Week 2 xây write path từ arXiv đến PostgreSQL. Pipeline tách HTTP, parsing, orchestration và persistence; giới hạn concurrency theo tài nguyên; giữ partial success; retry có chọn lọc; upsert idempotent và không để lần retry lỗi làm giảm chất lượng dữ liệu đã có.

## Luồng hoàn chỉnh

```text
arXiv metadata
  → rate limit + transient retry
  → PDF download/cache
  → validate PDF
  → Docling parsing
  → merge metadata + parsed content
  → per-paper PostgreSQL transaction
  → failure record để retry sau
```

## Nguyên tắc production đã học

- Metadata vẫn được lưu khi PDF processing thất bại.
- Download và parsing cần concurrency limit riêng.
- Validation giúp fail fast nhưng không thay thế isolation/timeout.
- Client retry và task retry phải có chung retry budget.
- Upsert dùng khóa ổn định và monotonic merge policy.
- Database error cần rollback session trước khi tiếp tục.
- Partial success phù hợp hơn rollback toàn batch cho các paper độc lập.

## Bằng chứng thực hành

- Các cell có nội dung trong notebook Week 2 đã được chạy, không có error output.
- arXiv fetch thành công.
- PDF download/cache và Docling parsing thành công.
- PostgreSQL upsert và retrieval thành công.
- E2E test: 3 fetched, 3 downloaded, 3 parsed, 3 stored, 0 errors.
- Tổng thời gian E2E được ghi nhận: khoảng 327 giây trên máy local.
- Airflow hands-on được hoãn do giới hạn phần cứng; DAG và failure model đã được hiểu.

## Câu hỏi ôn tập

1. Vì sao PDF lỗi không nên làm mất metadata?
2. Khi nào dùng client retry và khi nào để Airflow retry task?
3. Vì sao parse concurrency nên thấp hơn download concurrency?
4. Retry ingestion phải bảo vệ dữ liệu tốt đã có như thế nào?
5. Sau một database error, phải làm gì trước item tiếp theo?

<details>
<summary>Đáp án gợi ý</summary>

1. Metadata vẫn hữu ích và cho phép xử lý PDF lại sau.
2. Client xử lý lỗi ngắn/cục bộ; Airflow xử lý task thất bại hoặc sự cố dài hơn.
3. Parsing dùng nhiều CPU/RAM còn download chủ yếu chờ network.
4. Dùng monotonic merge: không ghi đè parsed content tốt bằng kết quả retry thất bại.
5. Rollback session, ghi failure rồi mở transaction mới cho item kế tiếp.

</details>

## Checklist hoàn thành

- [x] Hiểu trách nhiệm các thành phần ingestion.
- [x] Thiết kế được graceful degradation và layered retry.
- [x] Kiểm soát được PDF validation và concurrency.
- [x] Hiểu upsert, idempotency và transaction boundary.
- [x] Chạy thành công pipeline end-to-end.

**Trạng thái: Week 2 hoàn thành.**
