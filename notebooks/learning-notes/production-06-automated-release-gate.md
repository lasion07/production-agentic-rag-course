# Production 06 — Automated release gate

## Mục tiêu

Biến các kiểm tra production thành một cổng bắt buộc, tái lập được trước khi build và triển khai một image.

## Tóm tắt một phút

- Test xanh trên máy cá nhân là bằng chứng hữu ích nhưng chưa phải release control.
- Gate nhanh chạy trước: lock file, lint, unit/API tests và deterministic agent contracts.
- Gate có service thật dùng database/search/cache tạm để phát hiện sai migration, alias hoặc network contract.
- Evaluation dataset phải bất biến: khóa checksum, số items và model/prompt/retrieval/schema versions.
- `fail` và `blocked` đều phải làm CI thất bại; không được biến setup error thành pass.
- Fault test phải chạy graph/API thật; chỉ external dependencies mới được thay bằng deterministic adapters.
- Answer evaluation có model thật cần human-approved gold labels, staging environment và secret isolation.
- Image release phải định danh bằng digest. Tag giúp con người đọc; digest mới là immutable identity.
- Canary kiểm tra image mới trước promotion. Rollback trỏ lại digest cũ, không rebuild lại source cũ.

## Các tầng gate

1. **Quality:** `uv lock --check`, Ruff, unit và API contracts.
2. **Agent policy:** 6 cases, 18 deterministic checks, yêu cầu 100% pass.
3. **Service integration:** PostgreSQL migration/drift, OpenSearch aliases/mapping và Redis round trip.
4. **Artifact:** build image, SBOM, provenance, GHCR digest và release metadata.
5. **Hosted answer:** 7 answer cases chạy thủ công trên staging qua Langfuse sau human approval.

## Vì sao không tự động gọi model thật trên mọi pull request?

- Pull request từ fork không được nhận repository secrets.
- Chi phí và provider quota có thể biến CI thành nguồn gây quá tải.
- Model output có biến thiên; expected outputs chưa review không phải ground truth.
- Staging evaluation cần environment approval để biết ai đã cho phép gửi dữ liệu và tiêu tốn ngân sách.

## Invariants quan trọng

- Mọi third-party GitHub Action được pin bằng commit SHA.
- Deterministic gate không gọi OpenAI, Jina hoặc Langfuse.
- Thay dataset mà không cập nhật checksum/version làm manifest validation thất bại.
- Hosted gate yêu cầu pass rate 1.0 và không chạy khi review status chưa `approved`.
- Các service image của integration gate cũng được pin digest để môi trường CI không tự đổi.
- Hosted gate deploy đúng candidate digest và xác minh `APP_VERSION` khớp commit trước evaluation.
- Canary, promote và rollback chỉ chấp nhận `image@sha256:<digest>`; promote lỗi tự phục hồi digest trước đó.

## Câu hỏi ôn tập

1. Vì sao `blocked` phải làm release gate đỏ?
2. Tag image và digest image khác nhau thế nào?
3. Vì sao migration phải được thử trên database trống?
4. Tại sao answer dataset cần human review trước khi trở thành release ground truth?
5. Vì sao deterministic fault tests và hosted answer tests nên là hai jobs khác nhau?

## Đáp án ngắn

1. Vì contract chưa được thực thi; không có bằng chứng để cho phép release.
2. Tag có thể bị trỏ lại; digest gắn với đúng một artifact bất biến.
3. Để chứng minh revision chain dựng được schema mới từ đầu, không chỉ nâng cấp database đã có.
4. Gold label do AI tự tạo có thể sai và sẽ chặn một phiên bản đúng hoặc chấp nhận phiên bản sai.
5. Chúng khác về determinism, secrets, chi phí, dependency và cách xử lý failure.

## Việc vận hành còn lại

- Khôi phục đăng nhập GitHub CLI hoặc cấu hình trực tiếp trên GitHub.
- Chọn bốn CI jobs làm required status checks cho branch `main`.
- Gắn self-hosted runner nhãn `staging`, tạo protected environment `staging-evaluation` và thêm variables/secrets.
- Review cả 7 answer contracts, cập nhật trạng thái local + Langfuse, rồi chạy hosted gate lần đầu.
