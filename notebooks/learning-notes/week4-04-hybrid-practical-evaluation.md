# Week 4.4 — Thực hành và đánh giá hybrid retrieval

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Chạy hoàn chỉnh chunking, embedding, indexing và hybrid serving.
- So sánh BM25-only, vector-only và hybrid retrieval.
- Nhận biết giới hạn của evaluation corpus nhỏ.
- Phát hiện và xử lý chunk monopolization.

## Tóm tắt một phút

Ba public arXiv papers được chia thành 81 chunks, embed bằng Jina v3 và index thành công vào OpenSearch. Sáu query đều đưa paper đúng lên hạng 1 ở cả ba chế độ. Kết quả xác nhận pipeline hoạt động nhưng chưa chứng minh hybrid tốt hơn vì corpus quá nhỏ và chưa có query mà hai retriever thất bại khác nhau. Vấn đề rõ nhất là nhiều chunks cùng paper chiếm toàn bộ top-K.

## Bằng chứng thực hành

- Jina preflight: xác thực thành công, vector 1.024 chiều.
- Papers processed: 3.
- Chunks/embeddings indexed: 81/81.
- Indexing errors: 0.
- OpenSearch size: khoảng 1,68 MB.
- FastAPI hybrid endpoint: HTTP 200, `search_mode=hybrid`.
- Quantization paper: 36 chunks.
- Tabularis paper: 29 chunks.
- Diffusion/code-repair paper: 16 chunks.

Evaluation gồm ba lexical queries và ba paraphrase queries. Trên tập nhỏ này, BM25, vector và hybrid đều đạt Recall@3 = 1 và MRR = 1.

## Cách đọc metrics

Với một relevant paper đứng hạng 1 và `K=3`:

```text
Precision@3 = 1/3
Recall@3    = 1/1 = 1
RR          = 1/1 = 1
```

Phải nêu rõ **đơn vị relevance** là chunk hay paper. Practical này đánh giá ở cấp paper sau khi khử trùng lặp `arxiv_id`. Nếu ba chunks cùng paper đều được coi là relevant độc lập ở cấp chunk, Precision@3 có thể được tính khác.

Thuật ngữ đúng là **MRR — Mean Reciprocal Rank**. MMR thường chỉ **Maximal Marginal Relevance**, một kỹ thuật đa dạng hóa kết quả.

## Vì sao chưa chứng minh hybrid tốt hơn?

- Corpus chỉ có ba papers với chủ đề khác nhau rõ rệt.
- Query được thiết kế gần sát nội dung paper mục tiêu.
- Chưa có failure slice: BM25 đúng/vector sai hoặc vector đúng/BM25 sai.
- MRR = 1 ở cả ba mode tạo ceiling effect, không còn khoảng để thấy cải thiện.
- Cần nhiều queries, multi-relevant labels, exact identifiers, paraphrases, ambiguous queries và negative queries.

## Chunk monopolization

Tăng final K đơn thuần không bảo đảm đa dạng: một paper vẫn có thể chiếm nhiều vị trí hơn và context gửi LLM sẽ lớn hơn.

Thiết kế phù hợp hơn:

```text
retrieve candidate_k lớn
        ↓
rerank / deduplicate / diversify
        ↓
giới hạn tối đa chunks mỗi paper
        ↓
final K nhỏ gửi vào LLM
```

Các kỹ thuật:

- Giới hạn 1–2 chunks mỗi `arxiv_id`.
- Group/collapse theo paper rồi chọn chunk tốt nhất.
- MMR để cân bằng relevance và diversity.
- Reranker đánh giá lại candidate pool.
- Parent-document retrieval: tìm chunk nhưng trả context được gom theo paper/section.

## Bias do số lượng chunks

Paper dài không tự động được BM25 cộng điểm chỉ vì dài; BM25 có length normalization trên từng chunk. Tuy nhiên paper có nhiều chunks nhận nhiều “vé xổ số” hơn để lọt top-K. Header title/abstract lặp trong mỗi chunk còn làm tăng lexical signal. Vector search cũng chịu exposure bias vì paper dài có nhiều vector đại diện hơn.

Vì vậy cần đo:

- Số chunks trên mỗi paper trong candidate pool và final results.
- Tỷ lệ unique papers trong top-K.
- Max chunks per paper.
- Retrieval quality theo độ dài paper.

## Lỗi production phát hiện được

- Jina key mẫu trả `401`; đây là lỗi xác thực không nên retry.
- Preflight query được thêm để fail fast trước khi gửi paper content.
- RRF pipeline hoạt động, nhưng setup hiện báo `rrf_pipeline=True` ở nhiều lần chạy vì code kiểm tra ingest pipeline thay vì search pipeline; thao tác PUT vẫn idempotent nhưng trạng thái báo cáo gây hiểu nhầm.

## Câu hỏi ôn tập

1. Vì sao MRR = 1 ở mọi mode có thể là ceiling effect?
2. Candidate K và final K khác nhau thế nào?
3. Vì sao tăng final K không đủ xử lý chunk monopolization?
4. Paper dài có thể nhận exposure bias ở cả BM25 và vector như thế nào?

<details>
<summary>Đáp án gợi ý</summary>

1. Mọi phương pháp đã đạt trần trên dataset quá dễ nên không thể quan sát chênh lệch.
2. Candidate K phục vụ recall trước reranking; final K là context nhỏ đã lọc và đa dạng hóa.
3. Các vị trí thêm vẫn có thể thuộc cùng paper, đồng thời tăng token/cost.
4. Paper dài tạo nhiều chunks/vectors hơn nên có nhiều cơ hội lọt vào candidate pool.

</details>

## Bài tập thực hành đề xuất

Lấy 30–50 candidates, áp dụng `max_chunks_per_paper=2`, sau đó so sánh unique-paper ratio và retrieval metrics với baseline không đa dạng hóa.

## Checklist tự đánh giá

- [x] Index thành công real embeddings cho ba papers.
- [x] Chạy BM25, vector và native hybrid RRF.
- [x] Đánh giá Precision@K, Recall@K và MRR.
- [x] Nhận biết giới hạn của corpus nhỏ.
- [x] Phân tích chunk monopolization và paper-length exposure bias.

**Trạng thái: Week 4.4 hoàn thành.**
