# Week 3.3 — Query DSL, boosting và filtering

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt scoring query và non-scoring filter.
- Hiểu field boost tác động đến relevance ranking.
- Điều chỉnh recall/precision bằng operator và minimum match.

## Tóm tắt một phút

`must` xác định mức độ text match và đóng góp vào `_score`; `filter` chỉ quyết định document có đủ điều kiện hay không. Field boost thể hiện tầm quan trọng nghiệp vụ của từng field. `OR` tăng recall, còn `AND` hoặc `minimum_should_match` tăng precision.

## Query structure

```text
bool
  ├─ must: multi_match → scoring
  └─ filter: categories → không scoring
```

Mapping hiện tại ưu tiên:

```text
chunk_text^3 > title^2 > abstract^1
```

Boost không đảm bảo điểm cuối tăng đúng 2 hoặc 3 lần vì BM25 còn phụ thuộc TF, IDF, field length và cách `multi_match` kết hợp field.

## OR, AND và phrase

- `operator: or`: chỉ cần một term, recall cao hơn.
- `operator: and`: phải có tất cả term, precision cao hơn.
- `minimum_should_match`: kiểm soát số/tỷ lệ term tối thiểu linh hoạt hơn.
- `AND` không yêu cầu term đứng cạnh nhau hoặc đúng thứ tự; muốn vậy dùng phrase query.

## Ví dụ

Với query ba term và filter `cs.AI`:

- Document thuộc `cs.CL` bị loại dù text match rất tốt.
- Title khớp đủ term thường cao hơn abstract chỉ khớp một term nhờ coverage, field length và boost.
- Category filter không trực tiếp tăng `_score`.

## Lỗi thiết kế thường gặp

- Đưa exact category vào `must` rồi vô tình làm thay đổi score.
- Boost quá lớn khiến field importance lấn át textual relevance.
- Dùng `AND` và tưởng đó là exact phrase.
- Chọn `OR` nhưng không đặt ngưỡng match, làm kết quả quá rộng.
- Sort theo date làm relevance score không còn là thứ tự chính.

## Câu hỏi ôn tập

1. `must` và `filter` khác nhau thế nào?
2. Boost `title^2` có đảm bảo score tăng đúng hai lần không?
3. Khi nào dùng `minimum_should_match` thay cho `AND`?
4. Muốn tìm đúng cụm từ có thứ tự, nên dùng query nào?

<details>
<summary>Đáp án gợi ý</summary>

1. `must` vừa chọn vừa scoring; `filter` chỉ chọn điều kiện và không scoring.
2. Không; điểm cuối còn phụ thuộc BM25 và cách kết hợp field.
3. Khi muốn cân bằng recall/precision, ví dụ yêu cầu 2/3 term thay vì tất cả.
4. Phrase query, chẳng hạn `match_phrase`.

</details>

## Bài tập thực hành đề xuất

So sánh cùng query với `OR`, `AND` và `minimum_should_match: 75%`, rồi quan sát total hits và top results.

## Checklist tự đánh giá

- [x] Phân biệt scoring query và filter.
- [x] Hiểu field boosting.
- [x] Phân biệt OR, AND và phrase.
- [x] Điều chỉnh được precision/recall ở mức query.

**Trạng thái: Week 3.3 hoàn thành.**
