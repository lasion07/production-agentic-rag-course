# Week 7.7 — Candidate reranking và context selection

Quay lại: [Week 7.6](week7-06-llm-provider-abstraction-openai.md) · [Technical debt](technical-debt-backlog.md) · [Mục lục](README.md)

## Mục tiêu

- Phân biệt candidate K với final K.
- Đưa evidence quan trọng vào context thay vì chỉ lấy thẳng top K ban đầu.
- Giảm các chunks gần trùng nhau mà không áp dụng hard cap cứng theo paper.

## Tóm tắt một phút

Retriever lấy `candidate_k = final_k × 4`, sau đó selector chấm lại bằng ba tín hiệu: retrieval rank, lexical coverage và evidence phù hợp intent. Khi query hỏi số liệu, range hoặc percentage, chunk chứa numeric evidence được ưu tiên. Mỗi lần chọn tiếp theo có redundancy penalty theo Jaccard similarity, nên chunk gần trùng khó chiếm hết context. Selector chỉ sắp xếp evidence đã retrieve; nó không tạo claim mới.

## Luồng xử lý

```text
Query
  -> Hybrid/BM25 retrieve candidate K=12
  -> Query-aware relevance score
  -> Diversity penalty giữa các chunks
  -> Final K=3
  -> Grade -> Generate
```

Điểm utility rút gọn:

```text
relevance = rank_signal + lexical_coverage + intent_evidence
utility   = relevance - diversity_weight × max_similarity_to_selected
```

## Vì sao regression cũ thất bại?

- OpenSearch tìm đúng paper nhưng final top-3 không chứa chunk có `56.4–68.2%`.
- Langfuse trace xác nhận hai con số không vào generation input.
- Model nói evidence không đủ thay vì đoán; đây là grounded failure tốt hơn hallucination.
- Sửa prompt không thể bù cho missing evidence, vì vậy phải sửa retrieval/context selection.

## Kết quả thực hành

- OpenSearch trả 12 candidates; selector giữ 3 final chunks.
- Quantitative regression chuyển từ fail sang pass.
- Answer chứa đúng `56.4%–68.2%`, mô tả đúng cơ chế thêm noise rồi tiếp tục diffusion.
- Source đúng paper `2508.11110v1`.
- Langfuse trace: `d6e3366559202feefda9904ab921346a`.
- Full suite: 168 tests pass; sáu fault cases vẫn 18/18.

## Giới hạn production

- Heuristic numeric boost cần được đánh giá trên nhiều query, không chỉ một paper.
- Candidate K lớn làm tăng OpenSearch work và lượng dữ liệu rerank.
- Jaccard là lexical diversity, chưa đo semantic near-duplicate hoàn chỉnh.
- Bước tiếp theo có thể so sánh heuristic selector với cross-encoder hoặc hosted reranker bằng labeled dataset.

## Câu hỏi ôn tập

1. Vì sao tăng final K không tương đương candidate reranking?
2. Vì sao model không nên tự điền con số khi context thiếu quantitative evidence?
3. Diversity penalty giải quyết failure mode nào?
4. Khi nào numeric boost có thể gây false positive?

## Đáp án ngắn

1. Tăng final K gửi nhiều context thô hơn; reranking chọn lại evidence tốt nhất trước khi tiêu token LLM.
2. Vì đó là thông tin ngoài evidence và phá grounding contract.
3. Nhiều chunks gần trùng nhau chiếm hết context window.
4. Khi chunk có số liệu không liên quan, ví dụ năm xuất bản hoặc số mục tài liệu.

**Trạng thái: quantitative regression đã pass; cần mở rộng labeled answer dataset trước khi coi heuristic đã được hiệu chỉnh production.**
