# Human review packet — Week 7 answer contracts v0

## Mục đích

Tài liệu này giúp người duyệt kiểm tra nhanh các expected answers trong
`agentic_answer_eval_dataset_v0.json`. Các đoạn trích chỉ phục vụ human review:

Các đoạn trích bên dưới đã được chuẩn hoá khoảng trắng và một số PDF parsing
artifacts, nhưng không thay đổi từ ngữ hoặc số liệu.

- Không phải là expected output bắt buộc của model.
- Không được dùng để exact-match câu trả lời.
- Có thể lưu trong Langfuse item metadata để audit, nhưng không được truyền vào
  candidate task hay dùng làm exact-match ground-truth wording.
- Gold contract nằm ở claim, số liệu, source ID và citation; model được phép diễn đạt lại.

## W7A-01 — Diffusion repair range và phương pháp repair

- Gold chunk: `bf14b3d3-3a1d-4a79-8276-95619ea495f3:v1:c1`
- Paper: `2508.11110v1`
- Section: `1 Introduction`

Đoạn trích:

> “adding noise to a broken code snippet and resuming the diffusion process”

> “repair 56.4-68.2% of Python and Excel snippets across different noise levels”

Kết luận để duyệt: answer phải gắn khoảng `56.4–68.2%` với code repair và giải
thích cơ chế thêm noise rồi tiếp tục reverse diffusion/denoising.

## W7A-02 — Synthetic data và hiệu quả fine-tuning

- Gold chunk: `bf14b3d3-3a1d-4a79-8276-95619ea495f3:v1:c1`
- Paper: `2508.11110v1`
- Section: `1 Introduction`

Đoạn trích:

> “synthetic data has higher diversity and complexity compared to existing data generators and GPT-4o”

> “higher performance observed (+2.5 - 3.5%) when fine-tuning different models”

Kết luận để duyệt: answer phải nói synthetic data đa dạng và phức tạp hơn các
generator được so sánh, đồng thời ghi mức cải thiện fine-tuning `2.5–3.5%`.

## W7A-03 — Các thuật toán tối ưu cho PAR

- Gold chunk: `e47250e9-0148-494f-9971-6a1a15fda960:v1:c22`
- Paper: `2508.11112v1`
- Section: `5.2 Comparison of different optimization algorithms and PAR variants (Part 1)`

Đoạn trích:

> “three algorithms: proximal gradient (PG), accelerated proximal gradient (acc_PG), and ADMM”

Kết luận để duyệt: answer phải liệt kê đủ proximal gradient, accelerated
proximal gradient và ADMM.

## W7A-04 — Critical points và quantization

- Gold chunk: `e47250e9-0148-494f-9971-6a1a15fda960:v1:c26`
- Paper: `2508.11112v1`
- Section: `6 Conclusion and future directions`

Đoạn trích:

> “every critical point of the PARO objective is at least (1 - n/d)-quantized”

> “highly quantized solutions in the overparameterized regime where d ≫ n”

Kết luận để duyệt: answer phải liên hệ tỷ lệ quantization với `n/d`; khi số
tham số `d` lớn hơn nhiều số mẫu `n`, các critical points có mức quantization cao.

## W7A-05 — Quy mô corpus và mức cải thiện của TaFo

- Gold chunk: `3eaf8051-5893-485c-9f15-8552ca91e11f:v1:c3`
- Paper: `2508.11121v1`
- Section: `1 Introduction`

Đoạn trích:

> “a corpus of 1.8 Million spreadsheet”

> “15.6%-26.5% higher execution match accuracy on our benchmark”

Kết luận để duyệt: answer phải gắn `1.8 million` với quy mô corpus và
`15.6–26.5%` với mức TaFo vượt các baselines trên execution-match accuracy.

## W7A-06 — Cơ chế predictive formatting của TaFo

- Gold chunk: `3eaf8051-5893-485c-9f15-8552ca91e11f:v1:c3`
- Paper: `2508.11121v1`
- Section: `1 Introduction`

Đoạn trích:

> “predictively suggests conditional formatting rules without the need for communicating any intent”

> “combining a purely symbolic generator, a purely neural generator, and a neuro-symbolic generator”

Diễn giải evidence còn lại: chunk mô tả TaFo học cả rule trigger và formatting
properties, đồng thời không yêu cầu formatted examples hoặc natural-language
instructions từ người dùng.

Kết luận để duyệt: answer có thể diễn đạt khác nguyên văn nhưng phải giữ đủ ba
ý: neuro-symbolic, dự đoán rule cùng visual properties, và không cần user specification.

## W7A-07 — Attribution chéo hai paper

Gold evidence gồm hai chunk:

1. `bf14b3d3-3a1d-4a79-8276-95619ea495f3:v1:c1` — Diffusion paper:
   `56.4–68.2%` là repair success range.
2. `3eaf8051-5893-485c-9f15-8552ca91e11f:v1:c3` — TaFo paper:
   `15.6–26.5%` là performance-improvement range.

Kết luận để duyệt: answer phải nêu đủ cả hai khoảng và không được đảo nguồn.

## Checklist phê duyệt

Với mỗi case, xác nhận:

- Expected claim được đoạn trích hỗ trợ trực tiếp.
- Số liệu và đơn vị/phạm vi không bị đổi nghĩa.
- Required source/citation trỏ đúng paper.
- Contract không bắt model phải sao chép nguyên văn đoạn trích.
