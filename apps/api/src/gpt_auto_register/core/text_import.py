from collections.abc import Iterator

CONTENT_MARKERS = {
    "=== 卡密内容 ===",
    "=== 邮箱内容 ===",
    "=== 账号内容 ===",
}
EXPORT_HEADERS = {
    "卡密导出",
    "邮箱导出",
    "账号导出",
}


def import_content_lines(text: str) -> Iterator[tuple[int, str]]:
    lines = [
        (line_number, raw_line.lstrip("\ufeff").strip())
        for line_number, raw_line in enumerate(text.splitlines(), start=1)
    ]
    marker_index = next(
        (index for index, (_, line) in enumerate(lines) if line in CONTENT_MARKERS),
        None,
    )
    candidates = lines[marker_index + 1 :] if marker_index is not None else lines
    for line_number, line in candidates:
        if not line or line in EXPORT_HEADERS or line.startswith("#"):
            continue
        yield line_number, line
