# Week 4.1 — Chunking strategy và overlap

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Tính chunk count, stride và duplicated content.
- Hiểu trade-off giữa boundary recall và retrieval redundancy.
- Phân tích section-aware chunking theo implementation thật.

## Tóm tắt một phút

Chunk nhỏ tăng specificity nhưng dễ mất context; chunk lớn giữ context nhưng gây nhiễu và tốn token. Overlap bảo vệ thông tin tại boundary nhưng tăng storage, embedding cost và near-duplicate results. Section-aware chunking ưu tiên ranh giới tự nhiên của tài liệu.

## Word-based chunking

```text
chunk_size = 600
overlap    = 100
stride     = 500
```

Với `N > chunk_size`:

```text
chunk_count = 1 + ceil((N - chunk_size) / stride)
```

Document 1.600 từ tạo 3 chunk và 1.800 indexed words. Nếu overlap tăng lên 300, stride còn 300, tạo 5 chunk và 2.800 indexed words.

## Section-aware strategy

- `<100` từ: đưa vào small-section buffer.
- `100–800` từ: giữ làm một chunk.
- `>800` từ: chia theo word-based chunking.
- Lọc metadata sections và abstract bị trùng.
- Thêm title + abstract header vào section chunks.

Header giúp mỗi chunk self-contained và giữ liên hệ với paper gốc, nhưng làm tăng embedding cost, lặp context và có thể khuếch đại term phổ biến trong BM25.

## Implementation mismatch

Docstring nói small section được ghép với section lân cận. Trong code hiện tại, small section ở đầu tài liệu được flush khi section kế tiếp đủ lớn; vì chưa có previous chunk, nó có thể trở thành chunk riêng thay vì ghép với section lớn kế tiếp.

Đây là lý do cần unit test bằng các cấu trúc section cụ thể, không chỉ tin vào mô tả.

## Lỗi thiết kế thường gặp

- Tăng overlap mà không đo near-duplicate rate.
- Chọn chunk size theo cảm tính, không dựa retrieval eval.
- Lặp header dài trong mọi chunk.
- Để nhiều chunk cùng paper chiếm toàn bộ top-K.
- Không kiểm thử first/last/small section edge cases.

## Câu hỏi ôn tập

1. Overlap bảo vệ thông tin nào?
2. Vì sao overlap quá lớn có thể làm top-K kém đa dạng?
3. Header lặp lại có lợi và hại gì?
4. Vì sao section boundary thường tốt hơn fixed-size boundary?

<details>
<summary>Đáp án gợi ý</summary>

1. Ngữ cảnh nằm sát ranh giới giữa hai chunk.
2. Nhiều chunk gần giống nhau có thể cùng được xếp hạng cao.
3. Giữ source context nhưng tăng cost, duplication và scoring bias.
4. Section boundary thường giữ một đơn vị ý nghĩa tự nhiên của tài liệu.

</details>

## Bài tập thực hành đề xuất

So sánh chunk count và duplication ratio cho overlap 0, 100 và 300 trên cùng document 1.600 từ.

## Checklist tự đánh giá

- [x] Tính đúng stride và chunk count.
- [x] Phân tích được overlap trade-off.
- [x] Hiểu section-aware strategy.
- [x] Phát hiện được mismatch giữa mô tả và implementation.

**Trạng thái: Week 4.1 hoàn thành.**
