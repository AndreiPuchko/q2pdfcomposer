import json


def extract_rows_from_chunk_data(data, string_delta):
    res = []

    row_count = len(data["level"])

    # for key, value in data.items():
    _text = ""
    _top = 999999999999
    _bottom = 0
    _last_top = 0
    for row in range(row_count):
        if data["level"][row] != 5:
            continue
        if data["top"][row] < _last_top:
            continue
        if data["top"][row] - _last_top > string_delta:
            res.append({"text": _text.strip(), "top": _top, "bottom": _bottom})
            _text = ""
            _top = 999999999999
            _bottom = 0
        if len(data["text"][row]) > 1:
            _text += " " + data["text"][row]
            _top = min(data["top"][row], _top)
            _bottom = max(data["top"][row] + data["height"][row], _bottom)
            _last_top = data["top"][row]
    res.append({"text": _text.strip(), "top": _top, "bottom": _bottom})
    # for x in res:
    #     print(x['top'], x["text"][:100])
    return res


def json_ocr(data, base_column=1, string_delta=59):
    grand_result = []
    for page in data:
        page_result = []
        for chunk in page:
            page_result.append(extract_rows_from_chunk_data(chunk, string_delta))
        for main_column_row in page_result[base_column - 1]:
            for index, other_column in enumerate(page_result):
                if index == base_column - 1:
                    continue
                for other_column_row in other_column:
                    if (
                        other_column_row["top"] >= main_column_row["top"]
                        and other_column_row["top"] <= main_column_row["bottom"]
                    ):
                        main_column_row[f"other_column_{index}"] = other_column_row["text"]
                    if f"other_column_{index}" not in main_column_row:
                        main_column_row[f"other_column_{index}"] = ""
            del main_column_row["bottom"]
            del main_column_row["top"]
        for row in page_result[base_column - 1]:
            # if len([1 for x in row.values() if len(x.strip())==0]) <= 1:
            grand_result.append(row)
    return grand_result


if __name__ == "__main__":
    data = json.load(open("temp/raw_ocr_data.json"))
    rez = json_ocr(data)
    print(rez[2])
