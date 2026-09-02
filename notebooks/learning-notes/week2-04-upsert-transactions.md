# Week 2.4 — Upsert, transaction và idempotency

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Dùng khóa ổn định để ingestion có thể chạy lại an toàn.
- Không để retry làm giảm chất lượng dữ liệu đã lưu.
- Chọn transaction boundary phù hợp với partial success.

## Tóm tắt một phút

Upsert theo `arxiv_id` giúp tránh row trùng khi pipeline chạy lại. Merge policy phải cho phép metadata cập nhật nhưng không được ghi đè parsed content tốt bằng kết quả thất bại. Với các paper độc lập, transaction theo từng paper giúp giữ partial success; sau một lỗi phải rollback session trước khi tiếp tục.

## Idempotent upsert

```text
arxiv_id chưa tồn tại → INSERT
arxiv_id đã tồn tại  → MERGE/UPDATE
```

Retry cùng input phải tạo cùng trạng thái mong muốn, không tạo thêm row hoặc làm mất dữ liệu tốt.

## Monotonic data quality

- Metadata mới hợp lệ có thể được cập nhật.
- Parse mới thành công thì cập nhật `raw_text`, `sections` và `pdf_processed=True`.
- Parse mới thất bại thì giữ parsed content cũ và ghi `last_processing_error` cùng `last_attempted_at`.
- Nên lưu version/timestamp từ arXiv thay vì chỉ dựa vào database `updated_at`.

Blind overwrite có thể tạo trạng thái sai như:

```text
raw_text = nội dung cũ
pdf_processed = False
```

## Transaction boundary

Với batch các paper độc lập:

```text
paper 1 → transaction → commit
paper 2 → transaction → commit
paper 3 → lỗi → rollback + ghi failure
paper 4 → transaction mới → tiếp tục
```

- Không cần chạy lại paper đã commit.
- Sau database error phải `rollback()` trước khi tái sử dụng SQLAlchemy session.
- Per-paper transaction ưu tiên partial success nhưng có nhiều commit hơn batch transaction.
- Có thể tối ưu bằng chunked transactions hoặc savepoint, miễn failure isolation vẫn rõ ràng.

## Vấn đề implementation cần lưu ý

- Repository hiện commit bên trong `create()` và `update()`.
- Orchestrator lại có final `commit()`, khiến ownership của transaction không rõ ràng.
- Khi một upsert lỗi, loop bắt exception nhưng chưa rollback ngay trước item tiếp theo.
- Production code nên để service/orchestrator sở hữu transaction boundary hoặc dùng session riêng/savepoint cho từng paper.

## Câu hỏi ôn tập

1. Vì sao `arxiv_id` phù hợp làm khóa upsert?
2. Parse retry thất bại có nên đặt record tốt thành `pdf_processed=False` không?
3. Sau lỗi database, vì sao phải rollback session?
4. Khi nào per-paper transaction phù hợp hơn whole-batch transaction?

<details>
<summary>Đáp án gợi ý</summary>

1. Nó là định danh nguồn ổn định, giúp nhận ra paper đã tồn tại.
2. Không; giữ parsed content tốt và chỉ ghi nhận attempt thất bại.
3. Session sau lỗi transaction không thể dùng an toàn cho thao tác tiếp theo trước khi rollback.
4. Khi các item độc lập và cần giữ partial success thay vì một item lỗi làm mất cả batch.

</details>

## Bài tập thực hành đề xuất

Viết pseudo-code cho per-paper transaction có `commit`, `rollback`, failure logging và tiếp tục item kế tiếp.

## Checklist tự đánh giá

- [x] Hiểu idempotent upsert.
- [x] Thiết kế được monotonic merge policy.
- [x] Chọn được transaction boundary cho partial success.
- [x] Biết rollback session trước khi tiếp tục sau lỗi.

**Trạng thái: Week 2.4 hoàn thành.**
