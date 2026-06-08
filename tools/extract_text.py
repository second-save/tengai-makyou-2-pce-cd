#!/usr/bin/env python3
"""
Extract Japanese text from Tengai Makyou II (PCE-CD) to CSV.

This is an initial reverse-engineering tool. It recognizes several message
encodings observed in the disc, inspired by the Tenma III (Ziria) tools in
tenmatools/ but adapted for TM II's earlier format.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path

from tm2_disc import DEFAULT_TRACK2, load_user_data, offset_to_sector

# TM II reuses several control concepts from the Tenma engine family.
# High opcodes (0xEF-0xFF) match Ziria's table; TM II also uses '$' controls.
OPCODE_NAMES = {
    0xEF: "[ef]",
    0xF0: "[f0]",
    0xF1: "[f1]",
    0xF2: "[f2]",
    0xF3: "[f3]",
    0xF4: "[color]",
    0xF5: "[adpcm]",
    0xF6: "[f6]",
    0xF7: "[f7]",
    0xF8: "[f8]",
    0xF9: "[f9]",
    0xFA: "[fa]",
    0xFB: "[number]",
    0xFC: "[string]",
    0xFD: "[prompt]",
    0xFE: "\\n",
    0xFF: "[end]",
}

MAX_STRING_LEN = 512
MAX_MESSAGE_LEN = 1024

JAPANESE_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]")
def is_sjis_lead(b: int) -> bool:
    return (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC)


def read_sjis_string(data: bytes, pos: int, limit: int = MAX_STRING_LEN) -> tuple[str, int]:
    """Read Shift-JIS until a control byte or terminator."""
    out = bytearray()
    i = pos
    while i < len(data) and len(out) < limit:
        b = data[i]
        if b == 0x00:
            break
        if b >= 0xEF:
            break
        if b == 0x24:  # '$' control
            break
        if b < 0x20 and b not in (0x0A, 0x0D):
            break
        if 0x20 <= b <= 0x7E:
            out.append(b)
            i += 1
            continue
        if is_sjis_lead(b) and i + 1 < len(data):
            b2 = data[i + 1]
            if 0x40 <= b2 <= 0xFC and b2 != 0x7F:
                out.extend((b, b2))
                i += 2
                continue
        break
    text = out.decode("shift_jis", errors="replace")
    return text, i


def decode_message_body(data: bytes, pos: int, end: int) -> tuple[str, int]:
    """Decode message content with TM II '$' and high-opcode controls."""
    parts: list[str] = []
    i = pos
    end = min(end, pos + MAX_MESSAGE_LEN)
    while i < end:
        b = data[i]
        if b == 0x00:
            break
        if b == 0x24 and i + 1 < end:  # $X box/name control
            arg = data[i + 1]
            if arg == ord("0"):
                parts.append("\\n")
            elif arg == ord("n"):
                parts.append("$n")
            else:
                parts.append(f"[$" + chr(arg) + "]")
            i += 2
            continue
        if b >= 0xEF:
            name = OPCODE_NAMES.get(b, f"[{b:02X}]")
            parts.append(name)
            i += 1
            if b in (0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xFD):
                i += 1
            if b == 0xF5:
                i += 2
            continue
        if b == 0x72 and i + 1 < end and data[i + 1] == 0x24:
            i += 1
            continue
        if 0x20 <= b <= 0x7E or is_sjis_lead(b):
            text, i = read_sjis_string(data, i)
            if text:
                parts.append(text)
            else:
                i += 1
            continue
        i += 1
    return "".join(parts), i


@dataclass
class TextEntry:
    entry_type: str
    entry_id: str
    offset: int
    sector: int
    msg_type: int | None
    original: str
    notes: str = ""

    @property
    def has_japanese(self) -> bool:
        return bool(JAPANESE_RE.search(self.original))


def parse_label(data: bytes, pos: int) -> TextEntry | None:
    """Type 0x01: map/entity label (4-byte header + SJIS name)."""
    if data[pos] != 0x01:
        return None
    if pos + 5 >= len(data):
        return None
    name_start = pos + 5
    name, end = read_sjis_string(data, name_start)
    if not name or not JAPANESE_RE.search(name):
        return None
    if end >= len(data) or data[end] != 0x00:
        return None
    return TextEntry(
        entry_type="label",
        entry_id=f"label-0x{pos:X}",
        offset=pos,
        sector=offset_to_sector(pos),
        msg_type=0x01,
        original=name,
        notes="Type 0x01 area/entity label",
    )


def parse_simple_message(data: bytes, pos: int) -> TextEntry | None:
    """Type 0x02: short dialogue or menu string."""
    if data[pos] != 0x02:
        return None
    body_start = pos + 1
    if body_start < len(data) and data[body_start] == 0x72:
        body_start += 1
    text, end = decode_message_body(data, body_start, len(data))
    if not text or not JAPANESE_RE.search(text) or len(text) > MAX_STRING_LEN:
        return None
    if end >= len(data) or data[end] not in (0x00, 0x21):
        if not (text.endswith("!") or text.endswith("？")):
            return None
    return TextEntry(
        entry_type="string",
        entry_id=f"msg-0x{pos:X}",
        offset=pos,
        sector=offset_to_sector(pos),
        msg_type=0x02,
        original=text,
        notes="Type 0x02 message",
    )


def parse_rich_message(data: bytes, pos: int) -> TextEntry | None:
    """Type 0x10: dialogue with argument byte and $ controls."""
    if data[pos] != 0x10:
        return None
    if pos + 2 >= len(data):
        return None
    body_start = pos + 2
    text, end = decode_message_body(data, body_start, len(data))
    if not text or not JAPANESE_RE.search(text) or len(text) > MAX_STRING_LEN:
        return None
    if end < len(data) and data[end] == 0x00:
        pass
    elif not text.endswith(("!", "?", "？")):
        return None
    return TextEntry(
        entry_type="string",
        entry_id=f"msg-0x{pos:X}",
        offset=pos,
        sector=offset_to_sector(pos),
        msg_type=0x10,
        original=text,
        notes=f"Type 0x10 message (arg=0x{data[pos+1]:02X})",
    )


def parse_plain_string(data: bytes, pos: int) -> TextEntry | None:
    """Plain null-terminated Shift-JIS (menus, battle strings, etc.)."""
    if data[pos] == 0x00:
        return None
    if not (is_sjis_lead(data[pos]) or 0x20 <= data[pos] <= 0x7E):
        return None
    text, end = read_sjis_string(data, pos)
    if len(text) < 2 or len(text) > MAX_STRING_LEN or not JAPANESE_RE.search(text):
        return None
    if end >= len(data) or data[end] != 0x00:
        return None
    if any(ord(c) < 0x20 and c not in "\r\n" for c in text):
        return None
    return TextEntry(
        entry_type="plain",
        entry_id=f"plain-0x{pos:X}",
        offset=pos,
        sector=offset_to_sector(pos),
        msg_type=None,
        original=text,
        notes="Null-terminated Shift-JIS",
    )


def _add_entry(
    entries: list[TextEntry],
    seen: set[tuple[str, str]],
    entry: TextEntry | None,
) -> int:
    if entry is None or not entry.has_japanese:
        return 0
    key = (entry.entry_type, entry.original)
    if key in seen:
        return 0
    seen.add(key)
    entries.append(entry)
    return 1


def _is_likely_msg_start(data: bytes, pos: int) -> bool:
    if pos == 0:
        return True
    prev = data[pos - 1]
    return prev == 0x00 or prev == 0xFF


def extract_all(data: bytes) -> list[TextEntry]:
    entries: list[TextEntry] = []
    seen: set[tuple[str, str]] = set()

    i = 0
    while i < len(data):
        if data[i] == 0x00:
            i += 1
            continue

        if _is_likely_msg_start(data, i):
            b = data[i]
            if b == 0x01:
                _add_entry(entries, seen, parse_label(data, i))
            elif b == 0x02:
                _add_entry(entries, seen, parse_simple_message(data, i))
            elif b == 0x10:
                _add_entry(entries, seen, parse_rich_message(data, i))
            elif is_sjis_lead(b) or (0x20 <= b <= 0x7E):
                _add_entry(entries, seen, parse_plain_string(data, i))

        # Skip to next null terminator or advance one byte through binary
        if is_sjis_lead(data[i]) or (0x20 <= data[i] <= 0x7E) or data[i] in (0x01, 0x02, 0x10):
            while i < len(data) and data[i] != 0x00:
                i += 1
        else:
            i += 1

    entries.sort(key=lambda e: e.offset)
    return entries


def write_csv(entries: list[TextEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "type",
                "id",
                "offset",
                "sector",
                "msg_type",
                "original",
                "translation",
                "notes",
            ]
        )
        for e in entries:
            writer.writerow(
                [
                    e.entry_type,
                    e.entry_id,
                    f"0x{e.offset:X}",
                    f"0x{e.sector:X}",
                    "" if e.msg_type is None else f"0x{e.msg_type:02X}",
                    e.original,
                    "",
                    e.notes,
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=DEFAULT_TRACK2,
        help="Input track 2 BIN",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "script" / "tm2_text.csv",
        help="Output CSV file",
    )
    args = parser.parse_args()

    data = load_user_data(args.input)
    entries = extract_all(data)
    write_csv(entries, args.output)

    by_type: dict[str, int] = {}
    for e in entries:
        by_type[e.entry_type] = by_type.get(e.entry_type, 0) + 1

    print(f"Extracted {len(entries)} strings -> {args.output}")
    for t, n in sorted(by_type.items()):
        print(f"  {t}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
