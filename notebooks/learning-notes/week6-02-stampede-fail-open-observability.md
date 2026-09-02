# Week 6.2 — Cache stampede, Redis fail-open và observability metrics

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Nhận diện cache stampede và tải trùng lặp lên downstream.
- Phân biệt local lock với Redis distributed lock.
- Thiết kế request coalescing bằng single-flight.
- Giữ serving hoạt động khi Redis lỗi mà không làm quá tải Ollama.
- Phân biệt metric name, labels và chọn metric có cardinality an toàn.

## Tóm tắt một phút

Khi nhiều requests cùng miss một key, tất cả có thể chạy retrieval và Ollama, tạo cache stampede. Local lock chỉ phối hợp requests trong một process; distributed lock phối hợp được nhiều workers. Request thắng lock tính kết quả, request thua poll cache với backoff và jitter trong một wait budget. Redis nên fail-open, nhưng cache outage có thể chuyển tải sang Ollama nên vẫn cần concurrency limit hoặc single-flight fallback. Observability phải tách hit, miss, error, contention và latency.

## Cache stampede

```text
100 requests giống nhau
→ 100 cache misses
→ 100 generations
→ tranh chấp CPU/RAM và tăng latency
```

Stampede còn được gọi là dogpile effect hoặc thundering herd.

## Local và distributed lock

### Local lock

`asyncio.Lock` chỉ chia sẻ trong một process. Với bốn API workers, có thể vẫn có bốn generations trùng lặp.

### Redis distributed lock

```text
SET lock:<cache_key> <unique_token> NX PX <lock_ttl>
```

- `NX`: chỉ một request lấy được lock.
- `PX`: lock tự hết hạn để tránh deadlock.
- `unique_token`: chỉ owner được release lock.

Winner cần double-check cache sau khi lấy lock, chạy RAG nếu vẫn miss, ghi cache rồi release lock an toàn.

Losers:

```text
không lấy được lock
→ chờ backoff + jitter
→ kiểm tra cache lại
→ trả ngay khi winner ghi kết quả
→ dừng khi vượt wait budget/SLA
```

Không nên đợi nguyên lock TTL. Lock TTL là safety deadline, không phải polling interval hay request wait timeout.

## Ba loại thời gian

- **Polling interval:** khoảng nghỉ giữa hai lần kiểm tra cache.
- **Wait timeout:** tổng thời gian loser được phép chờ.
- **Lock TTL:** thời gian lock tồn tại nếu owner crash hoặc quên release.

Nếu computation có thể dài hơn lock TTL, cần TTL đủ lớn hoặc lease renewal. Nếu lock hết hạn quá sớm, request khác có thể lấy lock và tạo duplicate generation.

## Redis fail-open

Request path nên xử lý:

```text
Redis GET lỗi → coi như cache unavailable → chạy full RAG
Redis SET lỗi → vẫn trả answer vừa sinh
```

Fail-open bảo vệ availability nhưng không tự bảo vệ downstream capacity. Khi Redis lỗi, nhiều requests giống nhau có thể cùng chạy Ollama. Cần cân nhắc:

- Single-flight fallback.
- Concurrency limiter hoặc queue.
- Circuit breaker cho Redis.
- Timeout Redis ngắn.
- Stale answer có giới hạn nếu chính sách cho phép.

Implementation hiện tại fail-open trong request path, nhưng Redis lỗi lúc startup vẫn có thể làm API không khởi động. Redis cũng chưa xuất hiện trong health response.

## Metric name và labels

Ví dụ:

```text
cache_requests_total{result="hit", endpoint="/ask"} 820
```

- Metric name: `cache_requests_total`.
- Label names: `result`, `endpoint`.
- Label values: `hit`, `/ask`.
- Metric value: `820`.

Labels tạo các chiều phân loại cho cùng metric, không phải tên nhóm metric.

## Metric đề xuất

```text
cache_requests_total{result="hit|miss|error"}
cache_get_duration_seconds{result="hit|miss|error"}
rag_request_duration_seconds{cache_result="hit|miss|error"}
cache_lock_contention_total
cache_lock_wait_duration_seconds
cache_coalesced_requests_total
cache_lock_timeout_total
cache_bypass_total{reason="redis_unavailable|circuit_open"}
```

Hit ratio thường loại Redis errors khỏi mẫu số:

```text
hit_ratio = hits / (hits + misses)
```

Raw query, full cache key, user ID và trace ID không nên là metric labels vì gây high cardinality. Chúng phù hợp hơn với logs hoặc traces.

## Khoảng trống implementation hiện tại

- Chưa có single-flight/distributed lock.
- Redis timeout 30 giây quá dài cho optional cache.
- Redis client đồng bộ được gọi trong async endpoint.
- Startup fail-close dù request path fail-open.
- Health endpoint chưa kiểm tra Redis.
- Chưa có hit/miss/error counters và cache lookup span.
- Cache hit return sớm nên request trace thiếu output/latency đồng nhất với cache miss.

## Bằng chứng thực hành

Mô phỏng 100 concurrent requests:

```text
no_lock:
generations=100, misses=100

four_local_locks:
generations=4, coalesced=96

redis_distributed_lock:
generations=1, contentions=99, coalesced=99
p95_lock_wait=0.246s

fail_open:
redis_errors=10, successful_responses=10, generations=10
```

`hits=0` và `coalesced=99` không mâu thuẫn: cả 100 request-level lookups ban đầu đều miss; sau đó 99 losers nhận kết quả của winner.

Thời gian ba scenario gần `0.2s` không đại diện cho Ollama thật vì simulated generation dùng `asyncio.sleep`, cho phép các tác vụ overlap mà không tranh CPU.

## Lỗi thường gặp

- Dùng local lock rồi cho rằng nhiều workers đã được phối hợp.
- Cho losers ngủ nguyên lock TTL.
- Release distributed lock mà không kiểm tra owner token.
- Đặt lock TTL ngắn hơn generation nhưng không renew lease.
- Coi Redis errors là cache misses trong metric.
- Dùng raw query hoặc cache key làm metric label.
- Nghĩ fail-open đồng nghĩa hệ thống chắc chắn chịu được tải.

## Câu hỏi ôn tập

1. Vì sao bốn workers và local lock vẫn có thể tạo bốn generations?
2. Backoff, jitter, wait timeout và lock TTL khác nhau thế nào?
3. Vì sao cache miss và Redis error cần metric values riêng?
4. Fail-open bảo vệ điều gì và đẩy rủi ro sang đâu?
5. Metric name và label khác nhau thế nào?

<details>
<summary>Đáp án gợi ý</summary>

1. Mỗi process có một lock riêng, không nhìn thấy lock của process khác.
2. Backoff điều chỉnh khoảng chờ; jitter làm lệch thời điểm; wait timeout giới hạn request; lock TTL chống deadlock.
3. Miss là hành vi bình thường, error là sự cố dependency và cần alert riêng.
4. Bảo vệ availability nhưng đẩy computation xuống retrieval/Ollama.
5. Metric name là đại lượng đo; labels là các chiều phân loại có tập giá trị hữu hạn.

</details>

## Bài tập thực hành đề xuất

Chạy `run_stampede_observability_practical.py`, thay đổi `REQUESTS`, `WORKERS`, generation time và lock TTL. Quan sát số generations, contentions, coalesced requests và p95 wait.

## Checklist tự đánh giá

- [x] Giải thích được cache stampede.
- [x] Phân biệt local và distributed lock.
- [x] Thiết kế winner/loser flow.
- [x] Hiểu fail-open và downstream overload.
- [x] Phân biệt metric name, labels và values.
- [x] Chạy mô phỏng 100 concurrent requests.

**Trạng thái: Week 6.2 hoàn thành.**
