# Tổng kết Week 5 — Generation và complete RAG serving

Quay lại: [Mục lục sổ học tập](README.md)

## Kết quả đạt được

- Tính evidence budget và chọn context theo relevance, diversity, deduplication.
- Thiết kế prompt coi retrieved text là dữ liệu không đáng tin cậy, không phải instruction.
- Phân biệt schema validation, citation allowlist và claim-evidence grounding.
- Thiết kế retry có giới hạn và trả `insufficient_evidence` khi không thể tạo answer đáng tin cậy.
- Hiểu TTFT, total latency, SSE lifecycle, cancellation và cache policy.
- Chạy thành công RAG streaming thực tế với BM25 và Ollama.

## Tóm tắt một phút

Generation layer production không chỉ là gọi LLM. Hệ thống phải xây context trong token budget, chống prompt injection từ tài liệu, giới hạn output, kiểm chứng citation, stream đúng protocol, cancel khi client rời đi và chỉ cache answer đã hoàn tất validation. Retrieval có source không tự động đồng nghĩa answer grounded.

## Bằng chứng hoàn thành

- Practical hoàn tất: `completed=True`, không có stream error.
- TTFT `3.275s`, total latency `49.772s`.
- Output được giới hạn ở `128` token events.
- Đã nhận diện đúng các gap: `text/plain`, buffering, truncation và thiếu claim-level citation validation.

## Production gaps cần cải thiện

- Đổi media type và event protocol sang SSE chuẩn.
- Cancel Ollama khi client disconnect.
- Ghi completion/finish reason và không cache partial output.
- Thêm context packing, deduplication và giới hạn số chunk mỗi paper.
- Validate citation ở mức claim-evidence.
- Benchmark cùng cấu hình trước khi kết luận về hiệu năng.

## Câu hỏi tự kiểm tra

1. Khi nào API nên trả `insufficient_evidence`?
2. Vì sao output đúng JSON vẫn có thể sai về mặt grounding?
3. Khi nào một streamed answer được phép đưa vào cache?
4. Vì sao `sources` và `citations` là hai khái niệm khác nhau?

<details>
<summary>Đáp án gợi ý</summary>

1. Khi evidence không đủ hoặc output/citation không thể được sửa hợp lệ trong retry budget.
2. Schema chỉ kiểm tra hình dạng; claim và citation vẫn có thể không được context hỗ trợ.
3. Khi có completion signal, không bị cancel/truncate ngoài ý muốn và đã pass validation.
4. Source là tài liệu đã retrieve; citation là liên kết từ một claim đến evidence cụ thể.

</details>

## Bước tiếp theo

Week 6: Redis caching và Langfuse observability — thiết kế cache key, invalidation, fail-open và trace end-to-end.

**Trạng thái: Week 5 hoàn thành.**
