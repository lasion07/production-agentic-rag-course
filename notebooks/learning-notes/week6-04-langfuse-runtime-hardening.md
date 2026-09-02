# Week 6.4 — Langfuse runtime hardening và trace thật

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Triển khai tracing bằng Langfuse Python SDK v4.
- Thiết kế trace tree đúng loại observation và fail-open.
- Không mặc định gửi raw query, prompt hoặc answer lên cloud.
- Xác minh telemetry bằng cách gửi rồi đọc lại trace thật.

## Tóm tắt một phút

Tracing chỉ hoàn thành khi trace được backend ingest và đọc lại thành công; SDK khởi tạo không lỗi vẫn chưa đủ. Một RAG request nên là root `CHAIN`, retrieval là `RETRIEVER`, LLM call là `GENERATION`, còn cache lookup/store là `SPAN`. Lỗi Redis có thể làm cache span warning/error trong khi root request vẫn `ok` nhờ fail-open. Production API dùng background batching; chỉ script ngắn mới cần `flush()` tường minh. Raw content mặc định được thay bằng `chars + sha256` để giảm rủi ro privacy.

## Trace tree đã triển khai

```text
rag-request (CHAIN)
├─ cache-lookup (SPAN)
├─ search-retrieval (RETRIEVER)
├─ prompt-construction (CHAIN)
├─ llm-generation (GENERATION)
└─ cache-store (SPAN)
```

Generation ghi model, model parameters, token usage, finish reason và output size. Streaming còn ghi `completion_start_time` tại token đầu tiên.

## Quy tắc production

1. Dùng tên observation ổn định, không đưa query/user ID vào tên.
2. Đặt `user_id`, `session_id`, trace name và tags ở trace attributes.
3. Telemetry phải fail-open: Langfuse lỗi không được làm RAG request lỗi.
4. Không `flush()` sau mỗi API request; flush/shutdown khi app dừng.
5. Script ngắn phải flush trước khi process thoát.
6. Gửi trace xong phải đọc lại qua API để phát hiện delivery gap.
7. `LANGFUSE_CAPTURE_CONTENT=false` là mặc định an toàn.

Tài liệu đối chiếu: [Langfuse best practices](https://langfuse.com/docs/observability/best-practices), [observation types](https://langfuse.com/docs/observability/features/observation-types), [masking](https://langfuse.com/docs/observability/features/masking), [instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation).

## Bằng chứng thực hành

Smoke trace:

```text
CHAIN rag-request
├─ SPAN cache-lookup
├─ RETRIEVER search-retrieval
└─ GENERATION llm-generation
privacy_audit=passed
```

Request RAG thật:

```text
trace_id=7557e777d65a5a20cb9e40d5b2797094
latency=109.567s
observations=6
generation tokens: input=1492, output=128, total=1620
privacy_audit=passed
```

[Mở trace thật trên Langfuse Cloud](https://us.cloud.langfuse.com/project/cmti23w7n0atbad0hayhhjbby/traces/7557e777d65a5a20cb9e40d5b2797094)

Runtime container:

```text
Langfuse SDK 4.15.1
base_url=https://us.cloud.langfuse.com
capture_content=False
rag-api healthy
```

## Bài học từ giới hạn máy

- 4 Uvicorn workers cùng import Docling/Torch gây startup contention trên 4 CPU/6 GB; lab dùng 1 worker.
- Tắt precompiled bytecode giúp giảm áp lực Docker disk.
- Image Airflow 10 GB đã được gỡ để dành dung lượng cho API; volumes dữ liệu được giữ và có thể rebuild Airflow khi cần.

## Câu hỏi ôn tập

1. Vì sao `Langfuse initialized` chưa chứng minh tracing hoạt động?
2. Redis lỗi nhưng root trace vẫn `ok` trong trường hợp nào?
3. Vì sao LLM call nên là `GENERATION` thay vì generic span?
4. Khi nào phải gọi `flush()`?
5. Privacy audit cần kiểm tra điều gì?

<details>
<summary>Đáp án gợi ý</summary>

1. Export hoặc backend ingest vẫn có thể lỗi; cần đọc lại trace.
2. Cache fail-open và full RAG pipeline vẫn trả response thành công.
3. `GENERATION` hỗ trợ model, token usage, cost, TTFT và finish reason.
4. Với script ngắn trước khi process thoát; API dài hạn flush khi shutdown.
5. Trace không chứa raw query/prompt/answer hoặc secrets ngoài policy cho phép.

</details>

## Thực hành lại

```bash
env LANGFUSE_DEBUG=false uv run python notebooks/week6/run_langfuse_smoke.py
env LANGFUSE_DEBUG=false uv run python notebooks/week6/audit_latest_langfuse_trace.py
```

## Checklist tự đánh giá

- [x] SDK v4 và official environment variables hoạt động.
- [x] Observation types và parent-child nesting đúng.
- [x] Cache spans và early cache hit được trace.
- [x] Generation có token usage và finish reason.
- [x] Privacy-safe mặc định.
- [x] Smoke trace và API trace đều được đọc lại từ Cloud.
- [x] Container API healthy với cấu hình phù hợp tài nguyên.

**Trạng thái: Week 6.4 hoàn thành. Week 6 hoàn thành.**
