# Week 5.3 — Streaming, latency và cancellation

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt TTFT, total latency và generation throughput.
- Hiểu lifecycle của HTTP streaming/SSE.
- Xử lý lỗi sau khi response headers đã commit.
- Cancel downstream work khi client disconnect.
- Không cache partial/unvalidated output.

## Tóm tắt một phút

Streaming chủ yếu giảm perceived latency bằng cách gửi token sớm; nó không nhất thiết giảm tổng thời gian. Sau khi response headers và token đầu tiên đã được gửi, HTTP status không thể đổi từ 200 thành 500. Lỗi giữa stream phải được biểu diễn bằng error event. Client disconnect phải cancel generation để tránh lãng phí tài nguyên.

## Các metric

- **TTFT:** từ lúc nhận request đến token đầu tiên.
- **Total latency:** đến khi generation hoàn tất.
- **Tokens/second:** generation throughput.
- **Retrieval latency:** embedding + search.
- **Cancellation latency:** thời gian giải phóng downstream work sau disconnect.

Ví dụ token đầu ở 3 giây và hoàn tất ở 18 giây:

```text
TTFT = 3s
total latency = 18s
```

## Vì sao không đổi sang HTTP 500 giữa stream?

HTTP response được gửi theo thứ tự:

```text
status line + headers
→ body chunk 1
→ body chunk 2
→ ...
```

Khi body chunk đầu tiên tới client, `200 OK` đã commit. Server không thể gửi một status line thứ hai cho cùng response. Vì vậy protocol trong body cần explicit events:

```text
event: token
data: {...}

event: error
data: {"code":"GENERATION_FAILED","retryable":true}
```

## Disconnect và cancellation

Khi client disconnect:

1. Phát hiện disconnect/cancelled coroutine.
2. Cancel Ollama request.
3. Đóng network resources.
4. Không cache partial answer.
5. Ghi trace status `cancelled` và latency.

## Cache policy

Chỉ cache khi:

- Stream đã có completion signal.
- Answer hoàn chỉnh.
- Output validation thành công.

Không cache partial output do timeout, error hoặc disconnect.

## Khoảng trống implementation hiện tại

- SSE-like body đang dùng media type `text/plain`, không phải `text/event-stream`.
- Chưa phát hiện client disconnect.
- Chưa cancel Ollama generation.
- Error event gửi raw exception string.
- Chưa có heartbeat và explicit event names.
- Completion phụ thuộc Ollama gửi `done`.

## Câu hỏi ôn tập

1. Streaming cải thiện TTFT hay chắc chắn giảm total latency?
2. Vì sao status không thể đổi sau token đầu tiên?
3. Partial answer có nên được cache không?
4. Server cần làm gì khi client disconnect?

<details>
<summary>Đáp án gợi ý</summary>

1. Chủ yếu cải thiện TTFT/perceived latency; không chắc giảm total latency.
2. Status line và headers đã được gửi/commit.
3. Không, vì chưa hoàn chỉnh và chưa validation.
4. Cancel downstream generation, giải phóng resources và ghi trace cancelled.

</details>

## Checklist tự đánh giá

- [x] Tính đúng TTFT và total latency.
- [x] Hiểu HTTP headers commit.
- [x] Thiết kế error event giữa stream.
- [x] Nắm cancellation và cache policy.

**Trạng thái: Week 5.3 hoàn thành.**
