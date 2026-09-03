# Week 7.6 — LLM provider abstraction và OpenAI adapter

Quay lại: [Week 7.5](week7-05-evaluation-driven-hardening.md) · [Technical debt](technical-debt-backlog.md) · [Mục lục](README.md)

## Mục tiêu

- Tách business logic RAG khỏi SDK của một provider cụ thể.
- Dùng OpenAI làm hosted LLM để giảm CPU/RAM trên máy local.
- Giữ Ollama như một adapter có thể bật lại khi cần.

## Tóm tắt một phút

Application chỉ phụ thuộc vào contract `LLMClient`; factory chọn `OpenAIClient` hoặc `OllamaClient` từ cấu hình. OpenAI adapter dùng Responses API, chuẩn hóa text, streaming, usage và lỗi về cùng contract mà serving đang hiểu. Model hiệu lực phải nằm trong cache key và trace metadata. Việc đổi provider không được làm thay đổi retrieval, grounding, citation validation hay business status.

## Kiến trúc

```text
FastAPI / Agent graph / Telegram
              |
          LLMClient
         /         \
OpenAIClient       OllamaClient
Responses API      Local API
```

Các lớp trách nhiệm:

1. `LLMClient`: khai báo capability mà application cần.
2. Provider adapter: dịch request, response, streaming, usage và exception.
3. Factory: là nơi duy nhất quyết định provider theo `LLM_PROVIDER`.
4. Consumer: dùng `llm_client`, không import SDK/provider cụ thể.

## Contract quan trọng

- `default_model`: model mặc định của provider hiện hành.
- `generate()`: text generation chuẩn hóa.
- `generate_stream()`: phát delta và một completion event có usage.
- `get_langchain_model()`: phục vụ structured output trong LangGraph.
- `health_check()`: kiểm tra đúng provider/model đang cấu hình.
- `generate_rag_answer()`: giữ contract answer, sources, citations và usage.

## Cấu hình và vận hành

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.4-mini-2026-03-17
OPENAI_REASONING_EFFORT=none
```

- Không commit API key; dùng secret manager ở production.
- Ollama nằm trong Docker Compose profile `local-llm`, nên không khởi chạy mặc định.
- Bật lại local provider bằng `LLM_PROVIDER=ollama` và profile `local-llm`.
- Hosted LLM giảm tải inference runtime, nhưng API image vẫn lớn vì Docling/PyTorch thuộc ingestion.

## Correctness khi cutover

- Cache identity phải chứa model/provider version; nếu không có thể hit answer do model cũ sinh.
- Readiness phải kiểm tra provider hiện hành, không hard-code Ollama.
- Trace cần có `llm_provider`, model, latency, token usage và error type.
- Structured output pass schema chưa đủ: citation allowlist và evidence grounding vẫn phải kiểm tra riêng.
- Không gửi corpus ra provider ngoài nếu chưa có data-egress policy/approval.

## Kiểm chứng đã thực hiện

- OpenAI model health check thành công.
- Responses API trả đúng text và token usage.
- Structured output qua LangChain parse đúng Pydantic schema.
- API container healthy khi Ollama đã dừng.
- Docker build cache đã được prune (thu hồi 13,13 GB) và API đã rebuild/recreate thành công; database volumes không bị xóa.
- Corpus thực hành vẫn có 81 chunks thuộc đúng ba public arXiv papers.
- Full E2E `POST /api/v1/ask-agentic` qua Docker đạt HTTP 200 trong 10,31 giây: `business_status=success`, route `generate_answer`, hybrid search, 3 chunks, 1 source sau dedup, không retry/fallback/tool failure.
- Langfuse nhận trace `69fd54b1c72894bd742fefdf5f454f8a` gồm 22 observations và đúng một root `AGENT`; root metadata giữ business outcome/counters để filter dù nội dung bị che.
- Có đúng 3 `GENERATION` tương ứng guardrail, grading và answer; tổng 4.941 tokens, chi phí quan sát được khoảng 0,00537 USD. Span bao ngoài answer là `CHAIN`, nên không đếm đôi generation/cost.
- Privacy audit: input/output của toàn bộ observations đều là digest `{redacted, chars, sha256}`; raw query và chunks không xuất hiện trong Langfuse.
- 61 unit tests liên quan và 18/18 fault-injection contract checks pass. Full suite: 157 pass; một integration test gọi arXiv bị upstream rate-limit HTTP 429.

Sau khi học viên phê duyệt raw tracing cho corpus công khai, cấu hình local chuyển sang `LANGFUSE_CAPTURE_CONTENT=true`. Trace kiểm chứng `b1c65685ebefe7c06c2e2f48842aa829` có 22 observations, hiển thị được raw query và paper context, không còn input bị redacted. `.env.example` vẫn để `false` làm safe default cho môi trường mới/production.

## Bài học từ E2E thật

- Structured-output nodes cần output budget đủ lớn. Budget 32 tokens từng làm JSON guardrail bị cắt và query hợp lệ bị route nhầm thành `out_of_scope`; guardrail/grading/rewrite hiện dùng 128.
- OpenAI Responses có thể trả `AIMessage.content` dạng typed content blocks, nên adapter/API phải chuẩn hóa thành chuỗi.
- Answer generation cần budget riêng lớn hơn các node phân loại; hiện dùng 512 tokens để tránh câu trả lời bị cắt giữa chừng.
- Nhiều chunks của cùng paper không đồng nghĩa nhiều sources; danh sách sources phải deduplicate theo URL/paper.
- `span.id` không phải `trace.id`. API phải trả Langfuse trace ID 32 ký tự để feedback và audit tìm đúng trace.
- Trace Cloud có thể xuất hiện trễ do batch export/indexing; không nên tuyên bố delivery gap ngay ở lần đọc đầu tiên.
- Raw trace cải thiện debugging và evaluation, nhưng quyền phê duyệt phải dựa trên loại dữ liệu, access control và retention. Public corpus không tự động làm mọi user query an toàn để lưu.
- E2E thứ hai cho thấy model trả lời đúng cơ chế repair nhưng bỏ sót con số khi query hỏi “success range”; đây là regression case cho claim/citation evaluation, không phải lỗi provider connectivity.
- Model snapshot allowlist chặn request override ngoài chính sách trước khi gọi provider; output-token cap chặn call vượt ngân sách thay vì âm thầm clamp.
- Agent graph được construct một lần lúc startup. Health/readiness phản ánh đúng graph có dùng được hay không; request không tự construct lại một service lỗi.
- Quantitative-answer dataset được tách khỏi sáu fault cases vì nó đo answer grounding trên live corpus/model, còn fault dataset đo route và retry contracts một cách deterministic.
- RRF `pagination_depth` phải lớn hơn final K; nếu không mỗi subquery bị cắt theo `size` trước fusion. Cấu hình `hybrid_search_size_multiplier` hiện thực sự điều khiển cả fusion depth và vector candidate K.
- Hai quantitative E2E runs vẫn đỏ: đúng source nhưng claim `56.4–68.2%` không vào final context. Đây là retrieval/context-selection failure; prompt đã hành xử đúng khi không đoán số.
- Docker Desktop dừng hai lần quanh E2E/restart, củng cố ưu tiên tách dependency ingestion nặng khỏi serving image thay vì tiếp tục tăng tải trên máy học viên.

## Câu hỏi ôn tập

1. Vì sao không nên để router FastAPI import trực tiếp `OpenAIClient`?
2. Vì sao model hiệu lực phải tham gia cache key?
3. Hosted provider timeout thì business status nào phù hợp hơn: `insufficient_evidence` hay `generation_unavailable`?
4. Vì sao health check thành công vẫn chưa chứng minh RAG end-to-end đúng?
5. Khi nào nên giữ Ollama làm fallback, và khi nào fallback đó gây rủi ro vận hành?

## Đáp án ngắn

1. Router sẽ bị khóa vào provider và khó test/cutover.
2. Để không tái sử dụng answer được sinh bởi model hoặc prompt contract khác.
3. `generation_unavailable`; evidence có thể tồn tại nhưng generation gặp lỗi hạ tầng.
4. Health chỉ chứng minh kết nối/model access, chưa kiểm tra retrieval, prompt, grounding và output contract.
5. Giữ khi có đủ tài nguyên và policy cho local degradation; không nên tự fallback nếu máy thiếu RAM hoặc output quality/contract chưa tương đương.

## Bài tập đề xuất

- Viết contract test chạy cùng input qua OpenAI và Ollama adapters.
- Đặt timeout/cost budget theo node: guardrail, grading, rewrite và generation.
- Thêm model allowlist để request không thể chọn model ngoài chính sách.
- Thêm model allowlist và cost budget/alert; dùng trace E2E này làm baseline.
- Tách parser/Docling/PyTorch khỏi serving image để rebuild và cold start nhẹ hơn.

## Tài liệu chính thức

- [OpenAI GPT-5.4 mini model](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [OpenAI text generation và Responses API](https://developers.openai.com/api/docs/guides/text)
- [Langfuse observability best practices](https://langfuse.com/docs/observability/best-practices)

**Trạng thái: model allowlist, hard output budget và agent readiness đã triển khai; quantitative regression đang đỏ có chủ đích; còn cost alert, reranking/context selection và tối ưu serving image.**
