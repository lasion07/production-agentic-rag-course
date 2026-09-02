# Week 2.2 — Rate limit, retry và failure scope

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt client-level retry và task-level retry.
- Nhận diện transient error và permanent error.
- Thiết kế retry không vi phạm rate limit hoặc tạo retry storm.

## Tóm tắt một phút

Dùng client retry để phục hồi nhanh từ lỗi tạm thời và Airflow retry để phục hồi khi sự cố kéo dài hơn. Chỉ retry lỗi có khả năng phục hồi, dùng exponential backoff + jitter, tôn trọng `Retry-After` và giới hạn tổng retry budget.

## Hai tầng retry

```text
HTTP request lỗi
  → client retry ngắn hạn
       ├─ thành công → tiếp tục
       └─ hết retry → exception
                           ↓
                    Airflow retry task
```

- Client retry có phạm vi nhỏ và thời gian chờ ngắn.
- Airflow retry chạy lại task với khoảng chờ dài hơn.
- `retries=2` trong Airflow nghĩa là một lần đầu và hai lần chạy lại.

## Chính sách lỗi

- `400`: không retry; phải sửa request.
- `401/403`: không retry mù; kiểm tra credential hoặc permission.
- `429`: retry theo `Retry-After`, đồng thời tuân thủ rate limit.
- `502/503/504`: retry với exponential backoff và jitter.
- Network timeout khi gọi idempotent `GET`: có thể retry.

Thời gian chờ nên thỏa mãn:

```text
delay = max(rate_limit_remaining, backoff, Retry-After) + jitter
```

## Lỗi thiết kế thường gặp

- Retry mọi status code.
- Dùng backoff ngắn hơn rate limit của provider.
- Không thêm jitter khiến nhiều worker retry cùng lúc.
- Không phân biệt `max_attempts` với `max_retries`.
- Kết hợp nhiều tầng retry mà không giới hạn tổng số HTTP attempts.

## Câu hỏi ôn tập

1. Vì sao cần cả client retry và Airflow retry?
2. Vì sao không retry HTTP `400`?
3. Khi nhận `429` với `Retry-After`, giá trị nào quyết định thời gian chờ?
4. Ba client attempts kết hợp ba task attempts tạo tối đa bao nhiêu HTTP attempts?

<details>
<summary>Đáp án gợi ý</summary>

1. Client phục hồi nhanh và cục bộ; Airflow xử lý sự cố kéo dài hoặc task thất bại hoàn toàn.
2. Request không hợp lệ sẽ tiếp tục thất bại nếu không được sửa.
3. Chờ ít nhất bằng giá trị lớn nhất giữa rate limit, backoff và `Retry-After`, rồi thêm jitter.
4. Tối đa chín attempts.

</details>

## Bài tập thực hành đề xuất

Viết pseudo-code cho một HTTP `GET` có `max_attempts=3`, retry `429/502/503/504` và timeout, nhưng fail-fast với `400`.

## Checklist tự đánh giá

- [x] Phân biệt được transient và permanent error.
- [x] Chọn đúng lỗi cần retry.
- [x] Hiểu layered retry và retry amplification.
- [x] Biết sử dụng backoff, jitter và `Retry-After`.

**Trạng thái: Week 2.2 hoàn thành.**
