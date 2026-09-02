# Week 5.2 — Generation controls và output validation

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Hiểu temperature, top-p và output limit.
- Phân biệt schema validity với factual grounding.
- Thiết kế citation allowlist và claim-evidence validation.
- Giới hạn repair retry và graceful degradation.

## Tóm tắt một phút

Structured output chỉ bảo đảm hình dạng, không bảo đảm nội dung đúng. Grounded RAG cần kiểm tra JSON, schema, citation allowlist và claim-evidence support. Unsupported claim phải được loại hoặc đánh dấu thiếu bằng chứng; repair generation phải có retry budget.

## Generation controls

- Temperature thấp thường phù hợp grounded QA hơn creative generation.
- Top-p giới hạn nucleus sampling.
- Output length phải có generation limit; prompt word limit chỉ là soft instruction.
- Thay đổi parameters phải được đánh giá bằng quality, groundedness và latency.

Implementation hiện dùng `temperature=0.7`, `top_p=0.9`, chưa có output-token limit rõ ràng.

## Validation pipeline

```text
JSON parsing
→ schema validation
→ citation allowlist
→ claim-evidence validation
→ response policy
```

Một JSON đúng schema vẫn có thể chứa citation giả và unsupported claims.

## Xử lý partial grounding

Nếu answer gồm:

- Claim X được source A hỗ trợ.
- Claim Y trích source C không có trong context.

Hệ thống có thể giữ X, loại Y và trả trạng thái partial/insufficient evidence. Không cần hủy phần answer đã grounded nếu product contract cho phép partial answer.

## Repair strategy

```text
invalid output
→ repair prompt với allowed source IDs
→ validate lại
→ tối đa 1–2 attempts
→ degraded/insufficient_evidence + trace
```

Không retry vô hạn vì tăng latency/load và model có thể lặp lại cùng failure mode.

## Confidence

Không nên tin trực tiếp confidence do model tự khai báo hoặc hardcode `medium`. Confidence nên dựa trên signals có thể đo:

- Retrieval/reranker quality.
- Tỷ lệ claims có evidence.
- Citation validity.
- Agreement giữa nhiều checks.
- Failure/degraded mode.

## Khoảng trống implementation hiện tại

- Structured output mặc định tắt.
- Plain response gán `confidence="medium"` cố định.
- Citation list lấy từ toàn bộ retrieved chunks.
- Chưa kiểm chứng claim-level support.
- Prompt có output contracts mâu thuẫn.

## Câu hỏi ôn tập

1. Schema pass có chứng minh answer grounded không?
2. Citation allowlist kiểm tra điều gì?
3. Unsupported claim có thể được xử lý thế nào trong partial answer?
4. Vì sao repair retry cần budget?

<details>
<summary>Đáp án gợi ý</summary>

1. Không; schema chỉ kiểm tra hình dạng/kiểu dữ liệu.
2. Citation có thuộc sources đã cung cấp trong context không.
3. Loại claim hoặc đánh dấu insufficient evidence, giữ các claims đã grounded.
4. Tránh retry loop, latency và dependency load tăng không giới hạn.

</details>

## Checklist tự đánh giá

- [x] Phân biệt format validity và factual grounding.
- [x] Phát hiện citation ngoài allowlist.
- [x] Xử lý được partial unsupported answer.
- [x] Thiết kế repair retry có giới hạn.

**Trạng thái: Week 5.2 hoàn thành.**
