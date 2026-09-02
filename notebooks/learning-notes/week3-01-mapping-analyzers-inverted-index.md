# Week 3.1 — Mapping, analyzer và inverted index

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Chọn đúng mapping cho full-text search và exact filtering.
- Hiểu analyzer biến văn bản thành term như thế nào.
- Hiểu inverted index giúp retrieval nhanh hơn document scan.

## Tóm tắt một phút

`text` được analyze và dùng cho full-text/BM25; `keyword` giữ nguyên giá trị để exact match, filter, sort và aggregation. Analyzer tokenize, lowercase, loại stop words và stemming. Inverted index ánh xạ term đến các document/chunk chứa term đó.

## Mapping cốt lõi

```text
arxiv_id   → keyword
categories → keyword
title      → text + title.keyword
chunk_text → text
```

- `dynamic: strict` từ chối field lạ và giúp phát hiện schema drift.
- `match` phân tích query, phù hợp field `text`.
- `term/terms` không phân tích query, phù hợp field `keyword`.

## Analyzer và inverted index

```text
"Transformers are Learning"
  → tokenize → lowercase → stop words → stemming
  → ["transform", "learn"]
```

```text
Chunk A: "deep learning model"
Chunk B: "machine learning system"

deep     → [A]
machine  → [B]
learning → [A, B]
```

Posting list còn có term frequency, position và field-length statistics để BM25 tính điểm.

## Multi-field

```text
title         → full-text search
title.keyword → exact match, sorting, aggregation
```

Nếu `title` chỉ là keyword, tìm theo một phần tiêu đề sẽ kém hiệu quả. Nếu `categories` là text, analyzer có thể tách `cs.AI`, làm exact filter sai hoặc không ổn định.

## Câu hỏi ôn tập

1. Khi nào dùng `text` và khi nào dùng `keyword`?
2. `match` khác `term` ở điểm nào?
3. Vì sao `title` thường cần multi-field?
4. Inverted index khác quét toàn bộ document như thế nào?

<details>
<summary>Đáp án gợi ý</summary>

1. `text` cho full-text; `keyword` cho giá trị nguyên bản và exact operations.
2. `match` analyze query, còn `term` tìm đúng term đã index.
3. Cần cả full-text search và exact sort/aggregation.
4. Nó truy cập posting list theo term thay vì đọc lần lượt mọi document.

</details>

## Bài tập thực hành đề xuất

Chọn mapping cho `authors`, `published_date`, `section_title` và giải thích các query dự kiến trên từng field.

## Checklist tự đánh giá

- [x] Chọn đúng mapping cho bốn field chính.
- [x] Phân biệt `match` và `term`.
- [x] Hiểu multi-field.
- [x] Mô tả được analyzer và inverted index.

**Trạng thái: Week 3.1 hoàn thành.**
