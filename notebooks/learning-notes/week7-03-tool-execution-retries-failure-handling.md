# Week 7.3 — Tool execution, retries và agent failure handling

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt infrastructure retry với semantic retry.
- Phân loại retryable và non-retryable errors.
- Thiết kế hybrid → BM25 fallback có trạng thái rõ ràng.
- Tách retrieval round khỏi physical dependency attempts.
- Chọn đúng terminal outcome: degraded, insufficient evidence hoặc unavailable.

## Tóm tắt một phút

Tool retry dùng lại cùng query khi dependency gặp lỗi tạm thời; semantic retry rewrite query khi retrieval đã thành công nhưng evidence không relevant. Empty result không phải infrastructure failure. Production tool cần structured outcome để phân biệt success, degraded và error. Tất cả retry phải bị chặn bởi shared deadline/call budget. Không đưa error message sang document grader như evidence.

## Execution flow hiện tại

GitNexus xác nhận luồng:

```text
retrieve node
→ ToolNode
→ retrieve_papers
→ Jina embed_query
→ OpenSearch search_unified
→ hybrid/BM25 query
```

`retrieve` chỉ tạo tool call và tăng counter; `ToolNode` mới thực thi retrieval.

## Hai loại retry

```text
Infrastructure retry:
cùng query + cùng operation + lỗi timeout/429/5xx

Semantic retry:
search thành công + evidence không relevant
→ rewrite query → retrieval round mới
```

Không rewrite query vì service timeout. Không infrastructure-retry chỉ vì search trả zero hits hợp lệ.

## Structured tool outcome

```text
status: success | degraded | error
documents
requested_mode
actual_mode
attempts
error_type
retryable
fallback_reason
```

Ví dụ:

- Hybrid thành công: `success/hybrid`.
- Jina lỗi, BM25 thành công: `degraded/bm25`.
- OpenSearch không thể kết nối: `error/retrieval_unavailable`.
- OpenSearch khỏe nhưng zero hits: `success`, documents rỗng.

## Failure taxonomy

Có thể retry có giới hạn:

- Timeout, connection reset.
- HTTP 429 theo `Retry-After`.
- HTTP 502/503/504.

Không retry:

- HTTP 400 do request sai.
- HTTP 401/403 do key hoặc permission.
- Schema/dimension mismatch.
- Programming error.

## Routing contract

```text
success + documents
→ grade documents

success + zero hits + còn round
→ rewrite query

success + zero hits + hết round
→ insufficient_evidence

degraded + documents
→ grade → grounded answer, degraded=true

error + retryable + còn tool budget
→ retry cùng query

error + không thể phục hồi
→ retrieval_unavailable
```

## HTTP và business status

- Grounded BM25 fallback: HTTP 200, `degraded`.
- Search thành công nhưng thiếu evidence: HTTP 200, `insufficient_evidence`.
- OpenSearch không khả dụng: HTTP 503, `retrieval_unavailable`.

Không gọi answer generation khi evidence rỗng.

## Budget và retry amplification

```text
client attempts × tool attempts × semantic rounds × whole-request attempts
```

Các lớp retry không được tự đặt budget độc lập. Trước retry phải kiểm tra:

```text
remaining deadline >= backoff + attempt timeout + finish reserve
```

Nếu `Retry-After` vượt remaining deadline thì không chờ trong request hiện tại.

## Circuit breaker

- `CLOSED`: dependency hoạt động bình thường.
- `OPEN`: fail-fast nhánh lỗi và fallback ngay.
- `HALF_OPEN`: cho một số probe kiểm tra phục hồi.

Zero hits hợp lệ không làm circuit breaker ghi failure.

## Counters cần tách

- `retrieval_rounds`: số query/query rewrite đã thử.
- `embedding_http_attempts`: số request Jina vật lý.
- `search_attempts`: số OpenSearch calls.
- `tool_failures`: dependency failures.
- `zero_result_rounds`: successful empty searches.
- `fallbacks_total`: số lần chuyển mode.

Ví dụ Jina timeout hai lần rồi BM25 trả ba documents:

```text
retrieval_rounds=1
embedding_http_attempts=2
search_attempts=1
fallbacks_total=1
documents_count=3
status=degraded
```

## Failure tests tối thiểu

1. Jina timeout → bounded retry → BM25 success.
2. Jina 401 → không retry → BM25 fallback + alert.
3. Hybrid pipeline lỗi nhưng BM25 khỏe.
4. OpenSearch connection timeout → retrieval unavailable.
5. Hai successful zero-result rounds → insufficient evidence, không round thứ ba.
6. Deadline không đủ → bỏ retry và cancel pending work.
7. Assert upper bound của external calls, không chỉ assert answer.

## Câu hỏi ôn tập

1. Tool retry khác semantic retry thế nào?
2. Vì sao `hits=[]` không thể biểu diễn cả zero result và service error?
3. Khi nào hybrid → BM25 được coi là graceful degradation?
4. Vì sao `ToolNode(handle_tool_errors=True)` chưa đủ an toàn?
5. `insufficient_evidence` khác `retrieval_unavailable` thế nào?

<details>
<summary>Đáp án gợi ý</summary>

1. Tool retry giữ nguyên query vì lỗi hạ tầng; semantic retry rewrite sau một search thành công nhưng không relevant.
2. Hai trạng thái cần route, response và alert khác nhau.
3. Khi BM25 chạy thành công và answer vẫn grounded; response phải ghi actual mode và degraded.
4. Error ToolMessage vẫn có thể bị đưa sang grader như context nếu không có post-tool router.
5. Một bên search đã thành công nhưng thiếu bằng chứng; bên kia không thể kiểm tra corpus vì dependency lỗi.

</details>

## Checklist tự đánh giá

- [x] Tách infrastructure retry và semantic retry.
- [x] Phân loại retryable/non-retryable errors.
- [x] Thiết kế hybrid → BM25 fallback.
- [x] Chọn đúng HTTP/business status.
- [x] Hiểu retry amplification và shared budget.
- [x] Thiết kế counters và failure-injection tests.
- [x] Phân biệt zero result với dependency failure.

Các lỗi source phát hiện trong bài đã được ghi tại [Technical debt backlog](technical-debt-backlog.md).

**Trạng thái: Week 7.3 hoàn thành.**
