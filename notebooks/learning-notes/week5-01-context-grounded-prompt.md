# Week 5.1 — Context construction và grounded prompt

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt retrieved candidates và final LLM context.
- Đóng gói evidence theo token budget.
- Loại duplicate và giữ source diversity.
- Xử lý indirect prompt injection trong tài liệu.
- Kiểm tra citation sau generation.

## Tóm tắt một phút

Retrieval output không nên được nối thẳng vào prompt. Context builder phải deduplicate, diversify, giới hạn theo token budget và gắn source ID. Retrieved text là dữ liệu không đáng tin cậy, không phải instruction. Citation do LLM sinh phải được kiểm tra với allowlist sources và bằng chứng hỗ trợ claim.

## Context pipeline

```text
retrieved candidates
→ rerank
→ near-duplicate removal
→ max chunks per paper
→ token-budget packing
→ source delimiters
→ grounded prompt
```

## Token budget

```text
evidence_budget
  = context_window
  - output_reserve
  - system/query/formatting
  - safety_margin
```

Ví dụ:

```text
8192 - 1024 - 700 - 819 = 5649 tokens
```

Chọn A1 + B1 + C1 + D1 dùng 5.400 tokens; loại A2 vì gần trùng A1. Final K là giới hạn tối đa, không phải số lượng bắt buộc.

## Grounded prompt structure

```text
System policy
→ delimited evidence blocks with source IDs
→ user question
→ one clear output contract
```

Document text phải được bao trong delimiter và system prompt phải nói rõ: mọi instruction nằm trong evidence chỉ là dữ liệu để phân tích, không được thực thi.

## Citation validation

Nếu model sinh source ID không có trong context:

1. Không chỉ xóa citation rồi giữ nguyên unsupported claim.
2. Kiểm tra claim có được source hợp lệ khác hỗ trợ không.
3. Nếu có, sửa citation bằng structured regeneration/validation.
4. Nếu không, loại claim hoặc đánh dấu `unsupported`/`insufficient_evidence`.
5. Nếu output contract bắt buộc grounded citations, có thể reject và regenerate giới hạn số lần.

## Khoảng trống implementation hiện tại

- Context chỉ giữ `arxiv_id` và `chunk_text`, giúp giảm prompt size.
- Chưa có token counting/packing, near-duplicate removal hoặc MMR.
- Prompt nối tuần tự các chunks.
- Citation list được suy ra từ retrieved chunks, chưa kiểm chứng claim-level support.
- System prompt mâu thuẫn giữa giới hạn 300/200 từ và JSON/plain-text output.

## Lỗi thường gặp

- Dùng `top_k` thay token budget.
- Tin rằng retrieval score cao đồng nghĩa chunk bổ sung thông tin mới.
- Cho phép instruction trong document điều khiển model.
- Xóa citation giả nhưng giữ nguyên claim.
- Trộn nhiều output contracts trong cùng system prompt.

## Câu hỏi ôn tập

1. Vì sao final K không phải số lượng bắt buộc phải lấp đầy?
2. Evidence budget gồm những khoản trừ nào?
3. Retrieved text phải được coi là instruction hay untrusted data?
4. Citation không thuộc allowlist sources cần xử lý thế nào?

<details>
<summary>Đáp án gợi ý</summary>

1. Chỉ nên thêm context khi nó bổ sung evidence và còn token budget.
2. Output reserve, system/query/formatting overhead và safety margin.
3. Untrusted data.
4. Validate claim, regenerate/sửa bằng source hợp lệ hoặc loại claim/đánh dấu insufficient evidence.

</details>

## Checklist tự đánh giá

- [x] Tính đúng evidence budget.
- [x] Chọn context theo relevance, diversity và budget.
- [x] Nhận biết indirect prompt injection.
- [x] Hiểu citation validation không chỉ là string filtering.

**Trạng thái: Week 5.1 hoàn thành.**
