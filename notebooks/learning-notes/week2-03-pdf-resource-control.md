# Week 2.3 — PDF validation, concurrency và resource control

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt I/O-bound download với CPU/RAM-bound parsing.
- Thiết kế backpressure riêng cho từng loại workload.
- Hiểu lợi ích và giới hạn của fail-fast PDF validation.

## Tóm tắt một phút

Download có thể có concurrency cao hơn parsing. Docling tiêu tốn CPU/RAM nên cần semaphore nhỏ, đặc biệt trên M1 8GB. Trước parsing phải kiểm tra file, kích thước, PDF header và số trang để từ chối sớm input không phù hợp, nhưng validation không đảm bảo parser sẽ luôn thành công.

## Resource control

```text
Download queue ── semaphore 3–5 ──→ PDF cache
                                         ↓
Parse queue ───── semaphore 1 ─────→ structured content
```

- Download chủ yếu chờ network nên có thể chạy song song nhiều hơn.
- Parsing dùng CPU/RAM; concurrency cao có thể gây swap hoặc OOM.
- `asyncio.to_thread()` tránh block event loop nhưng không giảm tài nguyên Docling sử dụng.
- Có thể giảm `max_pages`, `max_file_size_mb`, tắt OCR và table extraction khi không cần.

## Fail-fast validation

Kiểm tra trước Docling:

1. File tồn tại và không rỗng.
2. Kích thước trong giới hạn.
3. Header bắt đầu bằng `%PDF-`.
4. Số trang trong giới hạn.

Lợi ích:

- **Reliability:** loại sớm các lỗi đã biết và cô lập failure theo paper.
- **Resource protection:** hạn chế input quá lớn hoặc bất thường làm cạn CPU/RAM.
- **Cost:** tránh khởi tạo parsing đắt đỏ cho file chắc chắn không hợp lệ.

Validation chỉ là lớp bảo vệ đầu tiên. PDF không tin cậy vẫn nên có timeout, process/container isolation và giới hạn tài nguyên.

## Lỗi thiết kế thường gặp

- Dùng chung một concurrency limit cho download và parsing.
- Tăng thread count rồi cho rằng CPU work sẽ nhanh hơn vô hạn.
- Chỉ kiểm tra phần mở rộng `.pdf`.
- Cho rằng file qua validation chắc chắn parse thành công.
- Tải nhanh không giới hạn khiến cache/queue tăng mãi khi parser chậm.

## Câu hỏi ôn tập

1. Vì sao parsing concurrency thường nhỏ hơn download concurrency?
2. `asyncio.to_thread()` giải quyết và không giải quyết điều gì?
3. Vì sao phải kiểm tra số trang và file size trước Docling?
4. Validation có thay thế sandbox và timeout không?

<details>
<summary>Đáp án gợi ý</summary>

1. Parsing dùng nhiều CPU/RAM, còn download chủ yếu chờ I/O.
2. Nó tránh block event loop nhưng không giảm CPU/RAM của parsing.
3. Để fail fast, bảo vệ tài nguyên và tránh chi phí xử lý không cần thiết.
4. Không; đó chỉ là lớp kiểm tra đầu vào cơ bản.

</details>

## Bài tập thực hành đề xuất

Chọn cấu hình download/parse concurrency cho máy 8GB RAM và nêu metric dùng để quyết định có tăng concurrency hay không.

## Checklist tự đánh giá

- [x] Phân biệt được I/O-bound và CPU/RAM-bound workload.
- [x] Điều chỉnh được concurrency cho máy cấu hình hạn chế.
- [x] Giải thích được ba lợi ích của pre-validation.
- [x] Hiểu validation không đảm bảo parsing thành công.

**Trạng thái: Week 2.3 hoàn thành.**
