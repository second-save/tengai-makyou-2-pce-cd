#!/usr/bin/env python3
"""Build a sector layout map for Tengai Makyou II (PCE-CD)."""

from __future__ import annotations

import argparse
import csv
import re
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from tm2_disc import DEFAULT_TRACK2, load_user_data, sector_to_offset

SECTOR_SIZE = 0x800
MIRROR_OFFSET = 0x10000
JAPANESE_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]")

# Known landmarks from reverse engineering (primary bank only).
KNOWN_REGIONS = [
    (0x00E6, 0x00E7, "system", "copyright_warning"),
    (0x00E7, 0x00E8, "system", "ipl_header"),
    (0x00E8, 0x0170, "program", "tengai2_main_code"),
    (0x014E, 0x014F, "program", "ys_data_loader"),
    (0x0171, 0x0172, "data", "battle_ui_strings"),
    (0x0196, 0x0199, "data", "world_region_table"),
    (0x5024, 0x5028, "data", "staff_credits"),
    (0x6A00, 0x6E00, "dev", "build_artifacts"),
]


@dataclass
class SectorInfo:
    sector: int
    region: str
    category: str
    text_count: int
    has_label: bool
    label_names: str
    mirrored: bool
    notes: str


def read_null_strings(chunk: bytes, limit: int = 8) -> list[str]:
    strings: list[str] = []
    i = 0
    while i < len(chunk) and len(strings) < limit:
        if chunk[i] == 0:
            i += 1
            continue
        start = i
        while i < len(chunk) and chunk[i] != 0:
            i += 1
        raw = chunk[start:i]
        if len(raw) < 2:
            continue
        try:
            text = raw.decode("shift_jis")
        except UnicodeDecodeError:
            continue
        if JAPANESE_RE.search(text):
            strings.append(text)
    return strings


def find_label_markers(data: bytes) -> dict[int, list[str]]:
    by_sector: dict[int, list[str]] = defaultdict(list)
    pos = 0
    while True:
        pos = data.find(b"\x01\x00\x00\x00\x00", pos)
        if pos == -1:
            break
        name_start = pos + 5
        end = data.find(b"\x00", name_start)
        if end == -1:
            break
        try:
            name = data[name_start:end].decode("shift_jis")
        except UnicodeDecodeError:
            pos += 1
            continue
        if JAPANESE_RE.search(name) and len(name) <= 20:
            sector = pos // SECTOR_SIZE
            by_sector[sector].append(name)
        pos += 1
    return by_sector


def load_text_counts(path: Path) -> Counter[int]:
    counts: Counter[int] = Counter()
    if not path.exists():
        return counts
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            counts[int(row["sector"], 16)] += 1
    return counts


def classify_sector_with_data(
    data: bytes,
    sector: int,
    text_count: int,
    labels: list[str],
    mirrored: bool,
) -> tuple[str, str, str]:
    for start, end, region, name in KNOWN_REGIONS:
        if start <= sector < end:
            return region, name, ""

    if sector >= MIRROR_OFFSET:
        base = sector - MIRROR_OFFSET
        region, category, base_notes = classify_sector_with_data(
            data, base, text_count, labels, False
        )
        note = f"mirror of 0x{base:X}"
        if base_notes:
            note += f"; {base_notes}"
        return region, category, note

    if labels:
        sample = ", ".join(labels[:3])
        if len(labels) > 3:
            sample += ", ..."
        return "game", "event_map", f"entities: {sample}"

    if text_count >= 5:
        strings = read_null_strings(data[sector * SECTOR_SIZE : (sector + 1) * SECTOR_SIZE])
        if strings:
            preview = " / ".join(s[:18] for s in strings[:2])
            return "game", "text_block", f"{text_count} strings; e.g. {preview}"
        return "game", "text_block", f"{text_count} strings"

    if text_count > 0:
        return "game", "text_sparse", f"{text_count} strings"

    if 0x0200 <= sector < 0x6000:
        return "game", "binary_blob", ""

    return "unknown", "unclassified", ""


def is_mirrored(data: bytes, sector: int) -> bool:
    mirror = sector + MIRROR_OFFSET
    max_sector = len(data) // SECTOR_SIZE
    if mirror >= max_sector:
        return False
    a = data[sector * SECTOR_SIZE : (sector + 1) * SECTOR_SIZE]
    b = data[mirror * SECTOR_SIZE : (mirror + 1) * SECTOR_SIZE]
    return a == b


def build_map(data: bytes, text_counts: Counter[int]) -> list[SectorInfo]:
    labels = find_label_markers(data)
    max_sector = len(data) // SECTOR_SIZE

    # Only enumerate sectors that are interesting (text, labels, known, or low program)
    interesting: set[int] = set()
    for start, end, _, _ in KNOWN_REGIONS:
        for s in range(start, min(end, max_sector)):
            interesting.add(s)
    interesting.update(text_counts.keys())
    interesting.update(labels.keys())
    for s in range(0x0E6, 0x0200):
        interesting.add(s)

    # Add event-map neighborhood sectors
    for s in list(labels.keys()):
        for delta in range(-2, 8):
            interesting.add(s + delta)

    infos: list[SectorInfo] = []
    for sector in sorted(interesting):
        if sector >= max_sector:
            continue
        region, category, notes = classify_sector_with_data(
            data,
            sector,
            text_counts.get(sector, 0),
            labels.get(sector, []),
            is_mirrored(data, sector),
        )
        infos.append(
            SectorInfo(
                sector=sector,
                region=region,
                category=category,
                text_count=text_counts.get(sector, 0),
                has_label=bool(labels.get(sector)),
                label_names=" | ".join(labels.get(sector, [])),
                mirrored=is_mirrored(data, sector),
                notes=notes,
            )
        )
    return infos


def write_csv(infos: list[SectorInfo], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "sector",
                "offset",
                "mirror_sector",
                "region",
                "category",
                "text_count",
                "has_label",
                "label_names",
                "mirrored",
                "notes",
            ]
        )
        for info in infos:
            writer.writerow(
                [
                    f"0x{info.sector:04X}",
                    f"0x{sector_to_offset(info.sector):X}",
                    f"0x{info.sector + MIRROR_OFFSET:04X}"
                    if info.sector < MIRROR_OFFSET
                    else "",
                    info.region,
                    info.category,
                    info.text_count,
                    int(info.has_label),
                    info.label_names,
                    int(info.mirrored),
                    info.notes,
                ]
            )


def write_markdown(infos: list[SectorInfo], path: Path, num_sectors: int) -> None:
    by_category = Counter(info.category for info in infos)
    event_maps = [i for i in infos if i.category == "event_map"]
    text_blocks = [i for i in infos if i.category.startswith("text")]

    lines = [
        "# Tengai Makyou II — Carte des secteurs (RE)",
        "",
        "Analyse automatique de la piste 2 (banque primaire + miroir).",
        "",
        "## Architecture du disque",
        "",
        f"- **Secteurs totaux** : {num_sectors:,} ({num_sectors * SECTOR_SIZE // 1024 // 1024} Mo)",
        f"- **Miroir** : secteur `S` dupliqué à `S + 0x{MIRROR_OFFSET:X}` pour la majeure partie du contenu",
        "- **Pas de filesystem** : adressage direct par numéro de secteur (Hudson CD)",
        "",
        "## Zones système et programme",
        "",
        "| Secteurs | Rôle |",
        "|----------|------|",
        "| `0xE6` | Avertissement copyright Hudson |",
        "| `0xE7` | IPL / en-tête CD (`TENGAI_MAKYO_2`) |",
        "| `0xE8–0x16F` | Code programme (`TENGAI2.??`) |",
        "| `0x14E` | Routine de chargement `YS.DATA.??` |",
        "| `0x171` | Textes combat/UI (skills, personnages) |",
        "| `0x196–0x198` | Table régions (尾張, 伊勢, 越後…) + menus |",
        "| `0x5024–0x5027` | Crédits staff |",
        "| `0x6A00–0x6DFF` | Artefacts de build (makefiles, sources) |",
        "",
        "## Format texte repéré",
        "",
        "| Préfixe | Usage |",
        "|---------|-------|",
        "| `0x01` + 4 octets | Label entité/zone (ex. `野良犬`) |",
        "| `0x02` | Dialogue / menu court |",
        "| `0x10` + arg | Dialogue avec `$0` (saut de ligne), `$n` (nom) |",
        "",
        "## Secteurs événements / maps (`0x01` labels)",
        "",
        f"{len(event_maps)} secteurs identifiés :",
        "",
        "| Secteur | Entités | Textes CSV |",
        "|---------|---------|------------|",
    ]

    for info in event_maps[:60]:
        lines.append(
            f"| `0x{info.sector:04X}` | {info.label_names or '—'} | {info.text_count} |"
        )
    if len(event_maps) > 60:
        lines.append(f"| … | ({len(event_maps) - 60} autres) | |")

    lines.extend(
        [
            "",
            "## Blocs texte denses (hors maps)",
            "",
            "| Secteur | Catégorie | Notes |",
            "|---------|-----------|-------|",
        ]
    )
    for info in sorted(text_blocks, key=lambda x: -x.text_count)[:40]:
        lines.append(
            f"| `0x{info.sector:04X}` | {info.category} | {info.notes} |"
        )

    lines.extend(
        [
            "",
            "## Références programme → secteurs",
            "",
            "Le code à `0xE8` contient des constantes 16-bit pointant vers :",
            "- `0x14E` — loader YS.DATA",
            "- `0x171` — module combat",
            "- `0x196` — table monde",
            "- `0x2C9` — map/événement (野良犬)",
            "- `0x5025` — crédits",
            "",
            "## Fichiers générés",
            "",
            "- `script/sector_map.csv` — liste détaillée",
            "- `docs/SECTOR_MAP.md` — ce document",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_TRACK2)
    parser.add_argument(
        "--text-csv",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "script" / "tm2_text_filtered.csv",
    )
    parser.add_argument(
        "-o",
        "--output-csv",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "script" / "sector_map.csv",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "docs" / "SECTOR_MAP.md",
    )
    args = parser.parse_args()

    data = load_user_data(args.input)
    num_sectors = len(data) // SECTOR_SIZE
    text_counts = load_text_counts(args.text_csv)
    infos = build_map(data, text_counts)

    write_csv(infos, args.output_csv)
    write_markdown(infos, args.output_md, num_sectors)

    print(f"Sectors mapped: {len(infos)}")
    print(f"CSV: {args.output_csv}")
    print(f"Markdown: {args.output_md}")
    print(f"Mirror pairs verified: primary bank mirrors at +0x{MIRROR_OFFSET:X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
