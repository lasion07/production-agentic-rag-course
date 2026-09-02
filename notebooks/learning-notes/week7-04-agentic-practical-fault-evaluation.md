# Week 7.4 — Agentic RAG practical, fault injection và evaluation

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt health với endpoint readiness.
- Tách setup error, behavioral failure và blocked evaluation.
- Xây regression dataset từ requirements và observed failures.
- Fault-inject agent components mà không gọi external AI services.
- Chọn code evaluation trước semantic judge khi contract còn lỗi.

## Tóm tắt một phút

Health xanh không đảm bảo endpoint chạy được. Evaluation phải đi từ availability/contract → agent policy → semantic quality. Không gộp các checks khác nghĩa thành một generic quality score. Fault injection phải quan sát source hiện tại, không tạo simulator chỉ để pass. Dataset v0 gồm sáu high-signal cases và đã được upload lên Langfuse với IDs ổn định.

## Baseline thực tế

Infrastructure:

- API, PostgreSQL, OpenSearch và Ollama healthy.
- Corpus OpenSearch có 81 chunks.
- OpenSearch `yellow` do single-node replica, không đồng nghĩa retrieval hỏng.

Agentic endpoint:

```text
POST /api/v1/ask-agentic
→ HTTP 500 trong 19 ms
```

Failure xảy ra trước guardrail:

```text
get_agentic_rag_service
→ make_agentic_rag_service(model=...)
→ factory không nhận model
→ TypeError
```

Kết luận: dependency health khác endpoint readiness.

## Test baseline

```text
30 passed
2 failed
22 setup errors
```

Không tính đơn giản `30/54`:

- 22 errors do shared fixtures không tồn tại.
- 2 failures là API contract drift.
- Setup error không chứng minh product behavior fail.

Hai behavioral failures:

1. `rewritten_query` bị FastAPI response model loại bỏ.
2. Request model override không được truyền xuống agent service.

Ngoài ra, `top_k/use_hybrid/categories` không được truyền đúng nhưng response vẫn mô tả requested values, tạo false observability.

## Ba tầng evaluation

```text
1. Availability/contract
   dependency construction, parameter forwarding, schema, status

2. Agent policy
   route, attempts, fallback, stop condition

3. Semantic quality
   retrieval relevance, evidence support, answer quality
```

Không dùng LLM judge để đánh giá answer khi endpoint chưa tạo được answer/trace. Deterministic contract dùng code evaluator; semantic judge chỉ thêm sau manual review và calibration.

## Dataset v0

Tên Langfuse:

```text
production-agentic-rag-week7-regression-v0
```

- Dataset ID: `cmtjmji6k00njad0d50dt5ypg`.
- Sáu active items: `W7E-01` đến `W7E-06`.
- Source mix: course requirements + observed source failures.
- Item IDs ổn định để upsert không duplicate.

Cases:

1. Out-of-scope, zero retrieval.
2. Relevant ngay round đầu.
3. Irrelevant → rewrite → relevant.
4. Hai successful zero-result rounds.
5. Jina timeout → BM25 degraded fallback.
6. OpenSearch unavailable → HTTP 503.

Local artifacts:

- [Dataset JSON](../week7/agentic_eval_dataset_v0.json)
- [Fault-injection runner](../week7/run_agentic_fault_evals.py)

## Fault-injection result

```text
pass=3
fail=9
blocked=6
```

Không gọi đây là quality `3/18`; checks khác ý nghĩa và sáu response checks chưa thể chạy end-to-end.

Phát hiện chính:

- W7E-04: rewrite thừa, kết thúc bằng generic fallback thay vì insufficient evidence.
- W7E-05: Jina timeout chỉ một attempt, không BM25 fallback, exception propagate.
- W7E-06: hai OpenSearch timeouts bị ghi thành zero-result, `tool_failures=0`.

## Evaluators v0

- `route_contract_pass`: terminal route, business status, generation policy.
- `call_budget_pass`: rounds, attempts, failures và fallbacks.
- `response_contract_pass`: HTTP status, required fields, actual mode.

Chưa tạo LLM-as-a-judge vì chưa có human-labelled semantic outputs.

## Câu hỏi ôn tập

1. Health khác readiness thế nào?
2. Vì sao không gộp pass/fail/blocked thành một quality score?
3. False observability xảy ra khi nào?
4. Vì sao `tool_failures=0` sau hai timeouts là tín hiệu nguy hiểm?
5. Khi nào nên thêm semantic LLM judge?

<details>
<summary>Đáp án gợi ý</summary>

1. Health kiểm tra dependency riêng lẻ; readiness kiểm tra request path thực sự có thể phục vụ.
2. Chúng khác loại, trọng số và một số checks chưa thực thi được.
3. API báo requested configuration dù execution dùng configuration khác.
4. Lỗi đã bị che thành zero result nên graph route sai và alert không thấy failure.
5. Sau khi có valid outputs, observed semantic failure modes và human labels để calibration.

</details>

## Checklist tự đánh giá

- [x] Chạy health và endpoint baseline.
- [x] Phân loại test setup errors và behavior failures.
- [x] Thiết kế và duyệt dataset sáu cases.
- [x] Chạy deterministic fault injection.
- [x] Giải thích pass/fail/blocked đúng nghĩa.
- [x] Upload và xác minh 6/6 Langfuse dataset items.
- [x] Hoãn LLM judge đúng thời điểm.

Các lỗi source mới đã được ghi tại [Technical debt backlog](technical-debt-backlog.md).

**Trạng thái: Week 7.4 hoàn thành.**
