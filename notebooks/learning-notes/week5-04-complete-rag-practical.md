# Week 5.4 — Complete RAG practical và đánh giá streaming

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Chạy end-to-end retrieval → context → Ollama → streaming response.
- Đo đúng TTFT và total latency.
- Phân biệt perceived latency với generation speed.
- Nhận diện giới hạn output, buffering và citation grounding.

## Tóm tắt một phút

Lần chạy thực tế đã hoàn tất với BM25, một chunk và một source. Người dùng thấy token đầu sau `3.275s`, nhưng phải chờ `49.772s` để nhận toàn bộ answer. Streaming cải thiện cảm nhận phản hồi nhờ TTFT thấp hơn total latency; nó không tự làm model sinh token nhanh hơn. Giới hạn `128` token events giúp chặn generation quá dài nhưng có thể cắt dở câu trả lời. `sources=1` chỉ chứng minh retrieval có một nguồn, chưa chứng minh từng claim trong answer được nguồn đó hỗ trợ.

## Bằng chứng thực hành

```text
content_type=text/plain; charset=utf-8
ttft_seconds=3.275
total_seconds=49.772
token_events=128 completed=True errors=0
mode=bm25 chunks=1 sources=1 answer_chars=719
```

Thời gian sau token đầu:

```text
49.772 - 3.275 = 46.497 giây
```

## Kiến thức cốt lõi

### 1. Streaming và latency

- **TTFT** đo thời gian người dùng bắt đầu thấy nội dung.
- **Total latency** đo thời gian nhận answer hoàn chỉnh.
- Streaming thường giảm **perceived latency**, không đảm bảo giảm total latency hoặc tăng tokens/second.
- Không được so sánh hai lần chạy như một A/B test nếu retrieval mode, `top_k`, model hoặc output limit khác nhau.

### 2. Buffering là gì?

Buffering nghĩa là browser, reverse proxy hoặc middleware tạm giữ nhiều chunk nhỏ trong bộ nhớ, đợi đủ dữ liệu hoặc đủ thời gian rồi mới chuyển tiếp. Server có thể đã sinh token, nhưng người dùng vẫn chưa thấy chúng nên lợi ích của streaming bị mất.

Để triển khai SSE đúng hơn:

- Dùng `Content-Type: text/event-stream`.
- Gửi event đúng định dạng và heartbeat khi cần.
- Tắt proxy buffering cho route streaming nếu hạ tầng yêu cầu.
- Kiểm tra thực tế tại client, không chỉ kiểm tra server log.

### 3. Output cap

Giới hạn generation giúp:

- Chặn output vô hạn hoặc quá dài.
- Giới hạn latency, tài nguyên và chi phí.
- Làm thời gian phục vụ dễ dự đoán hơn.

Rủi ro là answer có thể bị truncate. API nên lưu `done_reason` hoặc trạng thái tương đương để phân biệt hoàn tất tự nhiên với dừng do length limit; output bị cắt cần được đánh dấu hoặc retry có kiểm soát.

### 4. Citation grounding

Ba mức không được đánh đồng:

```text
retrieved source
→ citation trỏ tới source hợp lệ
→ claim thực sự được evidence trong source hỗ trợ
```

`sources=1` mới chỉ đạt mức đầu. Citation grounding cần tối thiểu:

- Citation xuất hiện trong answer.
- Citation nằm trong allowlist của context.
- Claim liên quan có evidence trong chunk được trích dẫn.
- Citation không được tự tạo hoặc chỉ gắn chung ở cuối answer.

## Luồng production đề xuất

```text
retrieve candidates
→ diversify và pack context
→ stream token events
→ phát hiện disconnect/cancel downstream
→ nhận completion reason
→ validate answer và citations
→ chỉ cache output hoàn chỉnh, hợp lệ
```

## Lỗi thường gặp

- Kết luận streaming làm generation nhanh hơn chỉ từ TTFT.
- Dùng `text/plain` rồi giả định mọi proxy đều chuyển từng chunk ngay lập tức.
- Xem `completed=True` là bằng chứng answer không bị cắt.
- Xem danh sách `sources` là bằng chứng citation grounding.
- So sánh latency giữa BM25/top-1 và hybrid/top-3 như cùng một cấu hình.

## Câu hỏi ôn tập

1. TTFT và total latency của lần chạy là bao nhiêu?
2. Vì sao streaming không đồng nghĩa model generation nhanh hơn?
3. Proxy buffering ảnh hưởng trải nghiệm thế nào?
4. Output cap giải quyết và tạo ra rủi ro gì?
5. `sources=1` đã đủ chứng minh grounded answer chưa?

<details>
<summary>Đáp án gợi ý</summary>

1. `3.275s` và `49.772s`.
2. Nó gửi phần output đã có sớm hơn; throughput và total generation time có thể không đổi.
3. Proxy giữ các chunk nhỏ rồi gửi theo lô, làm client thấy token muộn.
4. Giới hạn resource/latency nhưng có thể truncate answer.
5. Chưa; cần citation hợp lệ và claim-evidence support.

</details>

## Bài tập thực hành đề xuất

Đổi streaming response sang SSE chuẩn, thêm event `token`, `done`, `error`, rồi đo TTFT ở cả kết nối trực tiếp và qua reverse proxy. Ghi thêm `finish_reason` để phát hiện answer bị dừng vì giới hạn token.

## Checklist tự đánh giá

- [x] Chạy thành công complete RAG streaming.
- [x] Đo đúng TTFT và total latency.
- [x] Phân biệt streaming UX với generation throughput.
- [x] Hiểu buffering và output truncation.
- [x] Phân biệt retrieved source với citation grounding.

**Trạng thái: Week 5.4 hoàn thành.**
