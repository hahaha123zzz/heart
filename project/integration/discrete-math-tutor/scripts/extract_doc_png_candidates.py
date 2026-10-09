"""从旧版 .doc 中扫描完整 PNG 资源，供人工匹配教材图号。

此脚本只产生候选图，不能推断图片对应的段落；WMF、EMF 和 OLE 对象也不在扫描范围内。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SOURCE_DIR = Path(__file__).resolve().parents[3] / "server" / "data" / "textbook_raw"


def png_at(data: bytes, start: int) -> tuple[bytes, int, int] | None:
    if data[start:start + 8] != PNG_SIGNATURE:
        return None
    cursor = start + len(PNG_SIGNATURE)
    width = height = 0
    while cursor + 12 <= len(data):
        length = struct.unpack_from(">I", data, cursor)[0]
        if length > 64 * 1024 * 1024 or cursor + 12 + length > len(data):
            return None
        kind = data[cursor + 4:cursor + 8]
        payload = data[cursor + 8:cursor + 8 + length]
        expected_crc = struct.unpack_from(">I", data, cursor + 8 + length)[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != expected_crc:
            return None
        if kind == b"IHDR":
            width, height = struct.unpack_from(">II", payload)
        cursor += 12 + length
        if kind == b"IEND":
            return (data[start:cursor], width, height) if width and height else None
    return None


def scan(source_dir: Path, output_dir: Path | None = None) -> list[dict]:
    results: list[dict] = []
    for source in sorted(source_dir.glob("*.doc")):
        data = source.read_bytes()
        cursor = 0
        count = 0
        while (at := data.find(PNG_SIGNATURE, cursor)) >= 0:
            parsed = png_at(data, at)
            cursor = at + len(PNG_SIGNATURE)
            if parsed is None:
                continue
            image, width, height = parsed
            count += 1
            entry = {
                "source": source.name,
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "source_offset": at,
                "byte_length": len(image),
                "width": width,
                "height": height,
                "sha256": hashlib.sha256(image).hexdigest(),
                "review_status": "pending",
            }
            if output_dir is not None:
                output_dir.mkdir(parents=True, exist_ok=True)
                target = output_dir / f"{source.stem}-{count}.png"
                target.write_bytes(image)
                entry["filename"] = target.name
            results.append(entry)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(scan(args.source_dir, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
