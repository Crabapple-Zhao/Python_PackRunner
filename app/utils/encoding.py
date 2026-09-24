"""Subprocess-output decoding helpers."""

import locale


def decode_process_line(data) -> str:
    """优先按 UTF-8 解码，并兼容 Windows 本地编码。"""
    if isinstance(data, str):
        return data

    encodings = ["utf-8"]
    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)
    encodings.extend(["gb18030", "cp936"])

    tried = set()
    for encoding in encodings:
        key = encoding.lower()
        if key in tried:
            continue
        tried.add(key)
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue

    return data.decode("utf-8", errors="replace")
