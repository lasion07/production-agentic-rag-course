# Week 3.2 — BM25 scoring

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Hiểu ba yếu tố chính tạo nên điểm BM25.
- Giải thích được vì sao lặp từ khóa không làm điểm tăng tuyến tính.
- Liên hệ document length và corpus statistics với relevance.

## Tóm tắt một phút

BM25 kết hợp độ hiếm của term, số lần term xuất hiện có bão hòa và điều chỉnh theo độ dài field. Term hiếm có sức phân biệt cao; term lặp nhiều tăng điểm với lợi ích giảm dần; document ngắn có mật độ term cao thường được ưu tiên hơn document dài tương đương.

## Ba thành phần

### TF saturation

Term xuất hiện nhiều giúp tăng điểm, nhưng lần xuất hiện thứ 20 có giá trị thấp hơn lần đầu. Cơ chế này hạn chế keyword stuffing.

### IDF

```text
term hiếm trong corpus     → IDF cao
term có trong hầu hết docs → IDF thấp
```

IDF phụ thuộc corpus hiện tại nên điểm có thể thay đổi khi index thay đổi.

### Length normalization

Cùng số lần xuất hiện, field ngắn thường có điểm cao hơn field dài vì mật độ term lớn hơn.

```text
BM25 ≈ IDF × TF đã bão hòa × điều chỉnh độ dài
```

## Ví dụ

Với query `transformer`:

- 10 occurrences được điểm cao hơn 3 occurrences, nhưng không cao theo tỷ lệ `10/3`.
- 3 occurrences trong 100 từ thường cao hơn 3 occurrences trong 500 từ.
- Nếu term xuất hiện trong 90% corpus, IDF thấp và term đó phân biệt kết quả kém.

## Giới hạn

BM25 không tự hiểu synonym, paraphrase hoặc quan hệ ngữ nghĩa nếu các term không trùng sau analysis. Đây là lý do hybrid retrieval kết hợp BM25 với vector search.

## Câu hỏi ôn tập

1. TF saturation ngăn vấn đề gì?
2. Vì sao term hiếm thường có trọng số cao?
3. Chunk size ảnh hưởng BM25 như thế nào?
4. Vì sao điểm BM25 không phải xác suất relevance tuyệt đối?

<details>
<summary>Đáp án gợi ý</summary>

1. Ngăn lặp/nhồi từ khóa làm điểm tăng tuyến tính vô hạn.
2. Term hiếm mang nhiều thông tin phân biệt document hơn.
3. Length normalization làm cùng term frequency có điểm khác nhau ở chunk ngắn và dài.
4. Điểm phụ thuộc corpus, analyzer, field length và cấu hình scoring.

</details>

## Bài tập thực hành đề xuất

So sánh ba chunk có term frequency và độ dài khác nhau, rồi dự đoán thứ hạng trước khi chạy `_explain` trong OpenSearch.

## Checklist tự đánh giá

- [x] Hiểu TF saturation.
- [x] Hiểu IDF.
- [x] Hiểu length normalization.
- [x] Giải thích được giới hạn semantic của BM25.

**Trạng thái: Week 3.2 hoàn thành.**
