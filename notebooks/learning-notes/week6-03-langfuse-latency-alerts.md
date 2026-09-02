# Week 6.3 — Langfuse tracing, latency breakdown và production alerts

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt trace, span, metric và log.
- Thiết kế trace tree cho complete RAG request.
- Tìm bottleneck bằng latency breakdown và percentiles.
- Thiết kế alert có threshold, window, minimum traffic và severity.
- Hiểu fail-open span, telemetry gap, sampling và privacy.

## Tóm tắt một phút

Trace mô tả một request cụ thể; spans mô tả từng bước bên trong. Metrics cho biết xu hướng tổng thể và thường là nguồn của alerts; logs hỗ trợ điều tra chi tiết. Child span có thể `error` trong khi root request vẫn `ok` nếu graceful degradation thành công. Latency contribution chính xác cần so sánh child và root trong cùng trace; không nên chia hai giá trị p95 độc lập như một tỷ lệ chính xác. Alert severity phải dựa trên ảnh hưởng tới user SLO, không chỉ độ lớn của lỗi dependency.

## Trace tree production

```text
rag_request
├─ cache_lookup
├─ lock_wait
├─ query_embedding
├─ search_retrieval
├─ context_construction
├─ llm_generation
├─ output_validation
└─ cache_store
```

Mỗi span nên có duration, status và metadata có cardinality phù hợp. Generation span nên ghi model, token usage, TTFT và finish reason.

## Trace, metric và log

- **Trace:** điều tra hành trình của một request.
- **Span:** một operation có start/end nằm trong trace.
- **Metric:** tổng hợp xu hướng như error rate hoặc p95 latency.
- **Log:** sự kiện chi tiết để tìm kiếm và debug.

Luồng điều tra thường là:

```text
metric kích hoạt alert
→ mở trace đại diện
→ tìm span lỗi hoặc chậm
→ dùng logs để xem nguyên nhân chi tiết
```

## Root status và child status

Ví dụ:

```text
cache_lookup status=error
→ Redis operation thực sự thất bại
→ fail-open chạy full RAG thành công
→ rag_request status=ok
```

Root status mô tả business request outcome. Nó không chứng minh trace exporter hoặc Langfuse ingestion thành công. Telemetry delivery cần metric riêng.

## Latency breakdown

Trong một representative trace:

```text
rag_request           = 50.00s
llm_generation        = 48.00s
generation contribution = 48/50 = 96%
```

Đây là contribution hợp lệ vì hai durations thuộc cùng một request.

Với aggregate percentiles:

```text
p95 total      = 52s
p95 generation = 48s
```

`48/52` chỉ là chỉ báo. Hai p95 có thể được tạo bởi hai requests khác nhau nên percentiles không cộng hoặc chia như các child durations của một trace.

## Production alerts

Một alert cần:

```text
signal + threshold + time window + minimum traffic + severity + runbook
```

Ví dụ:

```text
rag_error_rate > 2%
trong 10 phút
với ít nhất 50 requests
→ critical
```

Các alert chính:

- RAG error rate.
- p95/p99 total latency.
- LLM timeout/error rate.
- Empty retrieval rate.
- Cache error/bypass rate.
- Citation hoặc grounding validation failure.
- Trace delivery gap khi API vẫn có traffic.

Redis error cao nhưng mọi request fail-open thành công thường là warning/degraded. Nó trở thành critical khi kéo theo user errors, latency SLO breach hoặc downstream saturation.

## Sampling và telemetry gap

Nên quan sát từng giai đoạn:

```text
traces_eligible
→ traces_sampled
→ traces_exported
→ traces_accepted
```

Nếu chủ động sample 70%, nhận khoảng 700/1.000 traces là dự kiến. Nếu sampling tắt mà chỉ nhận 700 traces, 30% còn lại là telemetry delivery gap.

Production thường sample success traces nhưng giữ 100% errors, timeouts và negative-feedback traces.

## Privacy và cost

Không nên mặc định ghi toàn bộ user query, retrieved context, system prompt và answer. Có thể:

- Redact secrets và PII.
- Lưu preview hoặc hash.
- Lưu token/character counts thay cho full content.
- Dùng sampling theo outcome.

## Khoảng trống implementation hiện tại

- Chưa trace cache lookup, lock wait, validation và cache store.
- Cache hit return sớm trước `end_request()`.
- LLM đang dùng generic span thay vì generation observation.
- Chưa ghi token usage, TTFT, finish reason và structured error.
- Quan hệ parent-child chưa được ràng buộc tường minh trong wrapper.
- Full prompt và answer đang được đưa vào trace.
- Flush cuối từng request có thể giảm hiệu quả batching.

Runtime hiện cho thấy:

```text
enabled=True
has_public_key=False
has_secret_key=False
host=http://localhost:3000
```

`LangfuseSettings` mong đợi prefix `LANGFUSE__`, trong khi `.env` dùng tên `LANGFUSE_`. Self-hosted Langfuse containers cũng chưa chạy, nên hiện chưa có trace thật được gửi.

## Bằng chứng thực hành

Trace mô phỏng:

```text
rag_request: 50.00s
├─ cache_lookup:          0.03s error, fail-open
├─ query_embedding:       0.90s
├─ search_retrieval:      0.40s
├─ context_construction:  0.10s
├─ llm_generation:       48.00s
└─ output_validation:     0.20s
```

Alert evaluation:

```text
rag_error_rate:     3%  > 2%  → critical FIRING
redis_error_rate:  40% > 10% → warning FIRING
trace_delivery_gap: 30% > 5% → warning FIRING
```

## Lỗi thường gặp

- Hiểu child `error` là tracing thất bại thay vì operation thất bại.
- Đánh dấu root request failed dù fallback trả response hợp lệ.
- Dùng hai p95 độc lập để tính contribution chính xác.
- Page on-call cho mọi dependency error dù user SLO chưa bị ảnh hưởng.
- Không đặt minimum traffic cho rate alert.
- Xem intentional sampling là trace delivery loss.
- Ghi raw prompt/query làm metric labels hoặc trace data không kiểm soát.

## Câu hỏi ôn tập

1. Khi nào child span error nhưng root trace vẫn ok?
2. Vì sao percentiles không có tính cộng?
3. Alert cần những thành phần nào?
4. Sampling và telemetry loss khác nhau thế nào?
5. Vì sao full prompt không nên luôn được ghi vào trace?

<details>
<summary>Đáp án gợi ý</summary>

1. Khi operation lỗi nhưng fallback hoàn tất business request.
2. Các percentile của từng metric có thể đến từ các requests khác nhau.
3. Signal, threshold, window, minimum traffic, severity và runbook.
4. Sampling là chủ động bỏ theo policy; telemetry loss xảy ra sau quyết định giữ trace.
5. Do privacy, security, storage cost và data-retention requirements.

</details>

## Bài tập thực hành đề xuất

Chạy `run_tracing_alerts_practical.py`, thay đổi span durations, error counts, thresholds và sampling rate. Quan sát root/child status và alert severity.

## Checklist tự đánh giá

- [x] Thiết kế được RAG trace tree.
- [x] Phân biệt root và child outcome.
- [x] Tính latency contribution trong cùng trace.
- [x] Hiểu p50/p95/p99 và giới hạn của percentile arithmetic.
- [x] Thiết kế alert đầy đủ điều kiện.
- [x] Phân biệt sampling với delivery gap.
- [x] Chạy trace/alert practical.

**Trạng thái: Week 6.3 hoàn thành.**
