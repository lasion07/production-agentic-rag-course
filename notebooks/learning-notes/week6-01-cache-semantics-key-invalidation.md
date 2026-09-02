# Week 6.1 — Redis cache semantics, cache key và invalidation

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Hiểu cache-aside trong RAG serving.
- Thiết kế cache key theo các yếu tố làm thay đổi response.
- Phân biệt TTL, eviction, logical invalidation và physical deletion.
- Ngăn stale answer khi corpus hoặc pipeline thay đổi.
- Hiểu Redis là dependency tối ưu và nên fail-open.

## Tóm tắt một phút

Cache hit bỏ qua retrieval và generation nên rất nhanh, nhưng cache key thiếu version có thể trả stale answer. TTL chỉ giới hạn thời gian stale; nó không tự biết paper vừa được cập nhật. Versioned namespace như `c12 → c13` làm request mới không còn đọc entry cũ, dù entry `c12` vẫn tồn tại trong Redis đến khi TTL hết hoặc bị xóa. Vì vậy cần cả version để bảo vệ correctness và TTL để thu hồi bộ nhớ.

## Implementation hiện tại

Luồng trong API:

```text
request
→ Redis GET
   ├─ hit: trả AskResponse đã cache
   └─ miss: retrieval → Ollama → Redis SET EX → response
```

Cache key hiện tại chứa:

- `query`
- `model`
- `top_k`
- `use_hybrid`
- `categories` đã sort

Key chưa chứa `corpus_version`, `prompt_version`, `retrieval_version` hoặc `response_schema_version`. TTL thực tế trong code và `.env.example` là 6 giờ.

## Cache key production đề xuất

```text
rag:answer:v2:c13:p5:r3:<request_hash>
```

Trong đó:

- `v2`: response schema/cache format version.
- `c13`: corpus/index version.
- `p5`: prompt version.
- `r3`: retrieval pipeline version.
- `request_hash`: hash của canonical request.

Nguyên tắc: hai requests chỉ dùng chung entry khi mọi yếu tố ảnh hưởng output tương đương.

## Invalidation và expiration

### TTL expiration

Key tự hết hạn sau một khoảng thời gian. TTL giới hạn độ stale và thu hồi memory, nhưng không phản ứng ngay khi corpus thay đổi.

### Logical invalidation

```text
request c12 → key c12
publish c13
request c13 → key c13 → không hit c12
```

Entry `c12` vẫn tồn tại nhưng không còn được request mới truy cập.

### Physical deletion

Key cũ thực sự bị xóa khỏi Redis. Có thể thực hiện targeted deletion hoặc để TTL dọn sau.

### Thứ tự publish version

```text
PostgreSQL update
→ OpenSearch index thành công
→ publish corpus_version mới
```

Nếu bump version trước khi OpenSearch cập nhật xong, request có thể lấy corpus cũ rồi cache nó dưới namespace mới.

## Hai failure mode cần phân biệt

### Unversioned key và không TTL

Corpus cập nhật nhưng request vẫn hit cùng key, khiến stale answer có thể tồn tại vô hạn. Đây là lỗi correctness.

### Versioned key nhưng entry cũ không TTL

Request `c13` không hit `c12`, nên correctness vẫn được bảo vệ. Tuy nhiên `c12` trở thành orphaned entry, chiếm memory vô hạn và tạo eviction pressure.

## Cache stampede

Nhiều requests cùng miss một key và đồng thời chạy retrieval/Ollama tạo **cache stampede** hoặc **dogpile effect**. Hậu quả là lặp computation, tăng latency và có thể làm quá tải downstream. Hướng xử lý là single-flight/request coalescing, distributed lock hoặc stale-while-revalidate tùy yêu cầu.

## Failure semantics

Redis lỗi trong request path nên fail-open:

```text
Redis lỗi → chạy full RAG pipeline
```

Implementation hiện tại bắt lỗi Redis trong lookup/store, nhưng Redis lỗi lúc startup vẫn có thể khiến API không khởi động. Đây là gap cần sửa ở bài tiếp theo.

## Bằng chứng thực hành

Lab Redis thu được:

```text
c12_exists=True
c12_ttl_seconds=30
same_version_hit=True
after_version_bump_hit=False
old_c12_entry_still_exists=True
lab_keys_cleaned=True
```

Kết quả chứng minh logical invalidation không đồng nghĩa physical deletion. Các key lab đã được dọn sau khi chạy.

## Lỗi thường gặp

- Nghĩ corpus update sẽ tự reset TTL.
- Nghĩ bump version sẽ xóa entry version cũ.
- Dùng TTL như cơ chế consistency duy nhất.
- Bump corpus version trước khi OpenSearch index thành công.
- Không đặt TTL vì cho rằng versioned key đã giải quyết mọi vấn đề.
- Cho Redis trở thành dependency bắt buộc của serving.

## Câu hỏi ôn tập

1. Vì sao `c13` miss dù entry `c12` vẫn tồn tại?
2. Versioned key không TTL ảnh hưởng correctness và memory thế nào?
3. TTL-only có thể trả stale answer tối đa bao lâu?
4. Cache stampede là gì?
5. Redis hỏng thì RAG serving nên xử lý thế nào?

<details>
<summary>Đáp án gợi ý</summary>

1. Hai version tạo hai namespace/key khác nhau.
2. Request version mới vẫn đúng, nhưng entry cũ tích tụ và gây memory pressure.
3. Gần bằng toàn bộ TTL nếu dữ liệu đổi ngay sau khi entry được tạo.
4. Nhiều requests cùng miss rồi đồng thời tính cùng một kết quả.
5. Fail-open: bỏ qua cache và chạy full RAG pipeline.

</details>

## Bài tập thực hành đề xuất

Chạy lại `run_redis_semantics_only.py`, đổi TTL và corpus version, sau đó quan sát `TTL`, `EXISTS` và `GET`. Khi máy đủ tài nguyên, chạy `run_cache_semantics_practical.py` để so sánh latency của full RAG miss và cache hit.

## Checklist tự đánh giá

- [x] Hiểu cache-aside và exact-match key.
- [x] Thiết kế versioned namespace.
- [x] Phân biệt invalidation với expiration/deletion.
- [x] Hiểu stale answer và orphaned entry.
- [x] Nhận diện cache stampede và fail-open.
- [x] Chạy lab TTL và logical invalidation.

**Trạng thái: Week 6.1 hoàn thành.**
