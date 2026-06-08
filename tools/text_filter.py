"""Heuristics to drop false positives from TM II text extraction."""

from __future__ import annotations

import re

JAPANESE_RE = re.compile(
    r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3000-\u303F\uFF00-\uFFEF]"
)
CTRL_TAG_RE = re.compile(
    r"\[(?:ef|f[0-9a-f]|color|adpcm|number|string|prompt|end)\]"
    r"|\\n|\$n|\[\$[^\]]+\]"
)
GARBAGE_CHAR_RE = re.compile(r"[\ufffd\u0000-\u0008\u000b\u000c\u000e-\u001f]")
SUSPICIOUS_ASCII_RE = re.compile(r"[;:<=>@\\|^`~]")
LONG_ASCII_RUN_RE = re.compile(r"[a-zA-Z]{3,}")

# Build/dev artifact sectors left on the disc image.
DEV_SECTOR_MIN = 0x6A00
DEV_SECTOR_MAX = 0x6DFF

# Minimum quality scores (higher = more likely real game text).
MIN_SCORE = {
    "label": 4.0,
    "plain": 5.0,
    "string": 8.0,
}


def strip_controls(text: str) -> str:
    return CTRL_TAG_RE.sub("", text)


def japanese_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(JAPANESE_RE.findall(text)) / len(text)


def japanese_char_count(text: str) -> int:
    return len(JAPANESE_RE.findall(text))


def quality_score(text: str, entry_type: str) -> float:
    if GARBAGE_CHAR_RE.search(text):
        return -1.0

    visible = strip_controls(text)
    if not visible:
        return -1.0

    jp_ratio = japanese_ratio(visible)
    jp_count = japanese_char_count(visible)

    if SUSPICIOUS_ASCII_RE.search(visible):
        return -1.0

    if LONG_ASCII_RUN_RE.search(visible) and jp_ratio < 0.75:
        return -1.0

    if re.search(r"[\u4E00-\u9FFF][&a-zA-Z0-9]$", visible):
        return -1.0

    score = jp_ratio * 10.0 + min(jp_count, 20) * 0.5

    if entry_type == "label":
        if jp_count < 1 or len(visible) > 24:
            return -1.0
        if jp_ratio < 0.55:
            return -1.0
        if re.search(r"[^ \u3000\u30A0-\u30FF\u3040-\u309F\u4E00-\u9FFF\uFF00-\uFFEF0-9a-zA-Z・ー]", visible):
            return -1.0
        return score + 5.0

    if entry_type == "plain":
        if len(visible) < 2 or jp_ratio < 0.5:
            return -1.0
        if len(visible) == 2 and jp_ratio < 0.9:
            return -1.0
        return score

    # Structured dialogue (0x02 / 0x10)
    short_npc_line = (
        len(visible) <= 24
        and "\\n" not in text
        and "$n" not in text
        and text.endswith(("？", "!", "！"))
        and jp_count >= 2
        and not re.search(r"\[(?:end|prompt|f[0-9]|adpcm|color|string|number|ef)\]", text)
    )
    if short_npc_line:
        return score + 8.0

    if jp_count < 3:
        return -1.0
    if jp_ratio < 0.45:
        return -1.0
    if re.search(r"[\u0400-\u04FF]", visible):
        return -1.0
    if re.search(r"\[(?:end|prompt|f[0-9]|adpcm|color|string|number|ef)\]", text):
        return -1.0
    if len(visible) > 80 and "$n" not in text:
        return -1.0
    if "[" in text and jp_count < 6:
        return -1.0
    if re.search(r"[*\"']", visible) and jp_ratio < 0.65:
        return -1.0

    has_valid_dialogue = (
        "$n" in text
        or re.search(r"\\n.{0,8}(は|の|に|が|を|、)", text) is not None
        or (
            len(visible) <= 24
            and jp_ratio >= 0.65
            and jp_count >= 3
            and text.endswith(("？", "!", "！"))
            and "\\n" not in text
        )
    )
    if not has_valid_dialogue:
        return -1.0

    dialogue_markers = any(token in text for token in ("\\n", "$n"))
    if dialogue_markers:
        score += 6.0
    elif jp_ratio < 0.68 or jp_count < 5:
        return -1.0

    if text.endswith(("!", "?", "！", "？")) or any(
        p in visible for p in ("は", "を", "に", "の", "が", "で", "。")
    ):
        score += 2.0

    return score


def is_dev_sector(sector: int) -> bool:
    return DEV_SECTOR_MIN <= sector <= DEV_SECTOR_MAX


def should_keep(row: dict) -> tuple[bool, str]:
    """Return (keep?, rejection reason)."""
    sector = int(row["sector"], 16)
    entry_type = row["type"]
    text = row["original"]

    if is_dev_sector(sector):
        return False, "dev/build sector"

    score = quality_score(text, entry_type)
    if score < MIN_SCORE.get(entry_type, 7.0):
        return False, f"low quality ({score:.1f})"

    return True, ""
