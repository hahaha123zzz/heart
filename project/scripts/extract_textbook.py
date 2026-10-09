"""Extract searchable text from the supplied legacy .doc chapters.

7-Zip exposes the OLE streams. The piece-table parser follows the MS-DOC
Fib/Clx/PlcPcd layout; embedded Equation Editor objects are not decoded.
"""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "server" / "data" / "textbook_raw"
TARGET = ROOT / "server" / "data" / "textbook_text"
SEVEN_ZIP = Path(r"C:\Program Files\7-Zip\7z.exe")


def stream(path: Path, name: str) -> bytes:
    result = subprocess.run(
        [str(SEVEN_ZIP), "e", "-so", str(path), name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    if not result.stdout:
        raise ValueError(f"{path.name}: missing OLE stream {name}")
    return result.stdout


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def extract_text(path: Path) -> str:
    word = stream(path, "WordDocument")
    if u16(word, 0) != 0xA5EC:
        raise ValueError(f"{path.name}: not a supported WordDocument stream")
    table_name = "1Table" if u16(word, 0x0A) & 0x0200 else "0Table"
    table = stream(path, table_name)

    pos = 0x20
    csw = u16(word, pos)
    pos += 2 + csw * 2
    cslw = u16(word, pos)
    pos += 2
    lw_start = pos
    ccp_text = u32(word, lw_start + 3 * 4)
    pos += cslw * 4
    fc_lcb_count = u16(word, pos)
    pos += 2
    if fc_lcb_count <= 33:
        raise ValueError(f"{path.name}: missing fcClx in FIB")
    fc_clx, lcb_clx = struct.unpack_from("<II", word, pos + 33 * 8)
    if lcb_clx < 5 or fc_clx + lcb_clx > len(table):
        raise ValueError(f"{path.name}: invalid CLX bounds")

    cursor = fc_clx
    clx_end = fc_clx + lcb_clx
    while cursor < clx_end:
        tag = table[cursor]
        cursor += 1
        if tag == 1:  # Prc, formatting only
            size = u16(table, cursor)
            cursor += 2 + size
            continue
        if tag != 2:
            raise ValueError(f"{path.name}: unexpected CLX tag {tag}")
        plc_size = u32(table, cursor)
        cursor += 4
        if plc_size < 4 or (plc_size - 4) % 12:
            raise ValueError(f"{path.name}: invalid PlcPcd size")
        plc = table[cursor : cursor + plc_size]
        if len(plc) != plc_size:
            raise ValueError(f"{path.name}: truncated PlcPcd")
        count = (plc_size - 4) // 12
        cps = [u32(plc, i * 4) for i in range(count + 1)]
        pieces: list[str] = []
        for i in range(count):
            first, last = cps[i], min(cps[i + 1], ccp_text)
            if first >= ccp_text:
                break
            if last <= first:
                continue
            pcd = 4 * (count + 1) + 8 * i
            fc = u32(plc, pcd + 2)
            compressed = bool(fc & 0x40000000)
            offset = (fc & 0x3FFFFFFF) // 2 if compressed else fc & 0x3FFFFFFF
            byte_count = (last - first) * (1 if compressed else 2)
            raw = word[offset : offset + byte_count]
            if len(raw) != byte_count:
                raise ValueError(f"{path.name}: text piece outside WordDocument")
            pieces.append(raw.decode("cp1252" if compressed else "utf-16le"))
        text = "".join(pieces)
        text = text.replace("\r", "\n").replace("\x07", "\t")
        text = text.replace("\x01", " [公式或对象] ")
        text = "".join(
            char if char in "\n\t" or ord(char) >= 32 else " " for char in text
        )
        return text
    raise ValueError(f"{path.name}: no Pcdt in CLX")


def main() -> None:
    files = sorted(SOURCE.glob("*.doc"))
    if len(files) != 10:
        raise RuntimeError(f"Expected 10 chapter files, found {len(files)}")
    TARGET.mkdir(parents=True, exist_ok=True)
    for source in files:
        content = extract_text(source)
        if len(content.strip()) < 500:
            raise ValueError(f"{source.name}: suspiciously short extraction")
        target = TARGET / (source.stem + ".txt")
        target.write_text(content, encoding="utf-8")
        print(f"{source.name}: {len(content)} chars -> {target.name}")


if __name__ == "__main__":
    main()
