# Week 7.2 — Agent state, nodes, conditional edges và routing

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt state thay đổi với runtime context/dependencies.
- Hiểu node trả về partial state update và reducer quyết định cách merge.
- Phân biệt edge cố định, conditional edge và tool routing.
- Thiết kế routing fail-safe bằng invariant và retry budget deterministic.
- Giữ evidence dùng để generate nhất quán với sources trả về API.

## Tóm tắt một phút

LangGraph có thể xem như state machine: node đọc state, thực hiện một trách nhiệm, trả partial update; reducer merge update; edge hoặc router chọn node tiếp theo. LLM phù hợp để đánh giá ngữ nghĩa, còn code phải kiểm tra invariant, attempts và deadline. Không được mặc định sang generation khi state thiếu hoặc mâu thuẫn. Documents dùng làm context, citations và API sources phải cùng một tập evidence.

## State và runtime context

```text
State   = dữ liệu thay đổi trong một lần chạy agent
Context = dependency và cấu hình tương đối ổn định
```

State có thể gồm:

- `messages`, `original_query`, `rewritten_query`
- `retrieval_attempts`
- `routing_decision`
- documents, sources và grading results

Context có thể gồm:

- OpenSearch, Ollama, embedding và tracing clients
- `top_k`, threshold, maximum attempts

Không đặt service client vào state: state nên dễ serialize, checkpoint, replay và test.

## Node và partial update

Một node không cần trả lại toàn bộ state:

```python
return {
    "retrieval_attempts": attempts + 1,
    "messages": [new_message],
}
```

Field không có reducer thường bị overwrite. Field dùng reducer như `add_messages` được merge theo quy tắc của reducer.

`HumanMessage` chứa rewritten query không chỉ phục vụ history/trace: node retrieve tiếp theo có thể đọc message mới nhất để thực sự tìm bằng query đã viết lại.

## Edge và conditional routing

```text
Unconditional edge: A luôn đi B
Conditional edge: router(state) chọn một nhánh hợp lệ
Tool routing: có tool call thì chạy ToolNode, không có thì đi nhánh khác
```

Mọi route mà router có thể trả về phải có trong mapping. Route thiếu mapping sẽ gây lỗi graph.

ToolNode là nơi thực thi tool retrieval; node `retrieve` có thể chỉ tạo tool call chứ chưa trực tiếp gọi OpenSearch.

## Semantic decision và deterministic policy

Tách hai trách nhiệm:

```text
Grading node (LLM): documents có relevant về mặt ngữ nghĩa không?
Router (code): state có hợp lệ không, còn retry không, được đi nhánh nào?
```

Ví dụ policy an toàn:

```python
if grade == "relevant" and relevant_documents:
    return "generate_answer"

if grade == "irrelevant" and attempts < max_attempts:
    return "rewrite_query"

return "insufficient_evidence"
```

Không dùng `generate_answer` làm default. Thiếu decision hoặc state mâu thuẫn có thể là node failure; generation lúc đó có nguy cơ hallucination.

## Invariant quan trọng

Trước generation cần đảm bảo:

```text
relevant_documents không rỗng
documents dùng để generate = documents đã được grade relevant
sources trả API = nguồn của documents thực sự dùng
attempts <= max_attempts
route thuộc allowlist
```

Hai tình huống dễ nhầm:

- `grade=irrelevant`, documents rỗng, còn attempts: đây là outcome hợp lệ → rewrite.
- `grade=relevant/generate`, nhưng relevant documents rỗng: state mâu thuẫn → trace invariant violation và fail-safe; không mặc định generate.

## Current value và history

Nếu cần cả kết quả hiện tại lẫn lịch sử, nên tách rõ:

```python
current_grading: GradingAttempt
grading_history: Annotated[list[GradingAttempt], operator.add]
```

Chỉ dùng một append-only list rồi lấy phần tử cuối vẫn hoạt động, nhưng contract kém rõ và các node downstream dễ dùng nhầm toàn bộ lịch sử.

## Data-flow gap cần tránh

Agent có thể grade/generate từ `ToolMessage`, nhưng API lại đọc `relevant_sources`. Nếu ToolNode không cập nhật field này, answer vẫn sinh được trong khi response có `sources=[]`.

Thiết kế đúng cần một nguồn evidence chuẩn, rồi derive đồng nhất:

```text
graded relevant documents
├─ context cho LLM
├─ citation allowlist
└─ sources trả về API
```

## Câu hỏi ôn tập

1. State khác Context ở đâu?
2. Field list không có reducer sẽ được merge thế nào?
3. Vì sao ToolNode có thể là nơi duy nhất thật sự gọi OpenSearch?
4. Khi nào nên rewrite, khi nào phải insufficient evidence?
5. Vì sao `generate_answer` không nên là default route?
6. Làm sao tránh answer có evidence nhưng API trả sources rỗng?

<details>
<summary>Đáp án gợi ý</summary>

1. State thay đổi theo execution; Context giữ dependencies và runtime config.
2. Update mới thường overwrite giá trị cũ.
3. Node trước đó chỉ tạo AI tool call; ToolNode mới thực thi tool.
4. Grade irrelevant và còn budget thì rewrite; hết budget hoặc state không an toàn thì insufficient evidence.
5. Missing/invalid state có thể dẫn đến generation không có evidence và hallucination.
6. Dùng cùng tập graded relevant documents để tạo context, citation allowlist và API sources.

</details>

## Bài tập thực hành đề xuất

Viết unit tests cho router với ít nhất các case:

- Relevant và documents không rỗng → generation.
- Irrelevant, attempts còn → rewrite.
- Irrelevant, hết attempts → insufficient evidence.
- Decision bị thiếu → fail-safe.
- Decision generate nhưng documents rỗng → invariant violation, không generation.

## Checklist tự đánh giá

- [x] Phân biệt State và Context.
- [x] Hiểu partial update và reducer.
- [x] Phân biệt node, ToolNode và router.
- [x] Đọc được unconditional/conditional edges.
- [x] Tách semantic grading khỏi deterministic routing.
- [x] Thiết kế retry budget và fail-safe route.
- [x] Phát hiện nguy cơ lệch giữa context và API sources.

**Trạng thái: Week 7.2 hoàn thành.**
