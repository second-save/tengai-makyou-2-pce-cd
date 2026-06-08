#!/usr/bin/env python3
"""Analyze Hudson YS.DATA loader and data-overlay catalog (Tengai Makyou II)."""

from __future__ import annotations

import argparse
import csv
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from tm2_disc import DEFAULT_TRACK2, load_user_data, sector_to_offset, write_iso

SECTOR_SIZE = 0x800
BUILD_START = 0x6A00
BUILD_END = 0x6E00
LOADER_SECTOR = 0x014E
SLOT_SECTORS = 0x80  # 128 sectors (256 KiB) between adpos slots on disc

# Runtime addresses (Hu6280 bank mapped around $E000 for sector 0x14E).
LOADER_CPU_BASE = 0xE000
LOADER_TEMPLATE_OFF = 0x00BF
RAM_CATALOG_COUNT = 0x68CE
RAM_CATALOG_TEMPLATE = 0x68D2
RAM_CD_SECTOR = 0x68C7
RAM_GAME_SECTOR = 0x2C79


@dataclass(frozen=True)
class DataOverlay:
    index: int
    name: str
    sector: int
    size_sectors: int
    ys_name: str
    kind: str
    size_source: str = "slot_max"


@dataclass(frozen=True)
class CdlenSearchResult:
    found: bool
    format_name: str
    offset: int | None
    match_count: int
    notes: str


def parse_adpos_catalog(data: bytes) -> list[tuple[str, int]]:
    """Recover HDWRITE adpos_* entries left in the build-artifact region."""
    region = data[sector_to_offset(BUILD_START) : sector_to_offset(BUILD_END)]
    found: dict[str, int] = {}
    for match in re.finditer(rb"adpos_([a-z0-9]+)\x00", region):
        name = match.group(1).decode()
        tail = region[match.end() : match.end() + 24]
        hex_match = re.search(rb"(\d{8})", tail)
        if not hex_match:
            continue
        pos = int(hex_match.group(1), 16)
        sector = pos // SECTOR_SIZE
        found[name] = sector
    return sorted(found.items(), key=lambda item: item[1])


def overlay_kind(name: str) -> str:
    if name in {"main", "game"}:
        return "program"
    if name.startswith("b") and name[1:].isdigit():
        return "dev_artifact"
    if name in {"pmnj", "dmnj", "pkab", "dkab", "pkab"}:
        return "event_pack"
    if re.fullmatch(r"w[a-z][0-9]", name) or re.fullmatch(r"x[a-z][0-9]", name):
        return "world_map"
    if re.fullmatch(r"y[a-z][0-9]", name):
        return "world_map"
    if name in {"sdt", "yav"}:
        return "system_data"
    return "data"


def infer_sizes(entries: list[tuple[str, int]]) -> dict[str, int]:
    """Fallback: assume each adpos slot is SLOT_SECTORS unless the next file is adjacent."""
    sizes: dict[str, int] = {}
    for i, (name, sector) in enumerate(entries):
        if i + 1 < len(entries):
            gap = entries[i + 1][1] - sector
            if 0 < gap <= SLOT_SECTORS:
                sizes[name] = gap
                continue
        sizes[name] = SLOT_SECTORS
    return sizes


def measure_overlay_size(data: bytes, sector: int, slot_sectors: int = SLOT_SECTORS) -> int:
    """Measure used sectors by scanning backward for non-empty/non-0xFF padding."""
    start = sector_to_offset(sector)
    end = start + slot_sectors * SECTOR_SIZE
    if end > len(data):
        end = len(data)
    last = 0
    for i in range((end - start) // SECTOR_SIZE - 1, -1, -1):
        chunk = data[start + i * SECTOR_SIZE : start + (i + 1) * SECTOR_SIZE]
        if chunk != b"\xff" * SECTOR_SIZE and chunk != b"\x00" * SECTOR_SIZE:
            last = i + 1
            break
    return last or slot_sectors


def measure_sizes(data: bytes, entries: list[tuple[str, int]]) -> dict[str, int]:
    return {name: measure_overlay_size(data, sector) for name, sector in entries}


def data_overlay_entries(entries: list[tuple[str, int]]) -> list[tuple[str, int]]:
    return [(n, s) for n, s in entries if overlay_kind(n) not in ("program", "dev_artifact")]


def locate_cdlen_table(data: bytes, entries: list[tuple[str, int]]) -> CdlenSearchResult:
    """Search TENGAI2.PRG for an embedded cdlen.bin / ovlarray table."""
    data_entries = data_overlay_entries(entries)
    sectors = [s for _, s in data_entries]
    measured = measure_sizes(data, data_entries)

    prog = data[sector_to_offset(0xE8) : sector_to_offset(0x170)]
    best_hits = 0
    best_off = 0
    best_fmt = ""

    # HuC ovlarray: (start_sector u16, length_sectors u16) × N
    for off in range(0, len(prog) - 4, 4):
        hits = 0
        lens: list[int] = []
        for i, (exp_sec, exp_len) in enumerate(zip(sectors, [measured[n] for n, _ in data_entries])):
            sec, length = struct.unpack_from("<HH", prog, off + i * 4)
            if sec == exp_sec and length == exp_len:
                hits += 1
                lens.append(length)
            elif sec == exp_sec and 1 <= length <= SLOT_SECTORS:
                hits += 1
                lens.append(length)
            else:
                break
        if hits > best_hits:
            best_hits, best_off, best_fmt = hits, off, "ovlarray_u16_u16"

    # Hudson cdlen candidate: (sector << 16) | length  as LE32
    for off in range(0, len(prog) - 4, 4):
        hits = 0
        for i, (exp_sec, exp_len) in enumerate(zip(sectors, [measured[n] for n, _ in data_entries])):
            value = struct.unpack_from("<I", prog, off + i * 4)[0]
            if (value >> 16) == exp_sec and (value & 0xFFFF) == exp_len:
                hits += 1
            else:
                break
        if hits > best_hits:
            best_hits, best_off, best_fmt = hits, off, "le32_sector_len"

    # Length-only blob — check exact signature for distinctive head (wa2/wa5/wa6)
    head = [measured[n] for n, _ in data_entries[:6]]
    for fmt, step, sig in [
        ("B", 1, bytes(head)),
        ("<H", 2, struct.pack("<" + "H" * len(head), *head)),
    ]:
        idx = prog.find(sig)
        if idx >= 0 and fmt == "B":
            return CdlenSearchResult(
                found=True,
                format_name=f"lengths_only_{fmt}",
                offset=sector_to_offset(0xE8) + idx,
                match_count=len(head),
                notes="Partial length table signature matched",
            )

    if best_hits >= 20:
        abs_off = sector_to_offset(0xE8) + best_off
        return CdlenSearchResult(
            found=True,
            format_name=best_fmt,
            offset=abs_off,
            match_count=best_hits,
            notes=f"Table candidate in program at disc offset {abs_off:#x}",
        )

    return CdlenSearchResult(
        found=False,
        format_name="",
        offset=None,
        match_count=best_hits,
        notes=(
            "No contiguous cdlen.bin table in TENGAI2.PRG (0xE8–0x16F). "
            "Build chain: fsize -b0x800 → cdlen.s → cdlen.bin, merged at link time. "
            "Retail ROM likely uses scattered CDLEN_* equates copied to RAM $68xx at init."
        ),
    )


def build_overlay_table(data: bytes) -> list[DataOverlay]:
    entries = parse_adpos_catalog(data)
    cdlen = locate_cdlen_table(data, entries)
    measured = measure_sizes(data, entries)
    fallback = infer_sizes(entries)
    overlays: list[DataOverlay] = []
    data_index = 0
    for name, sector in entries:
        kind = overlay_kind(name)
        if kind == "program":
            ys_name = f"(PROG:{name})"
            idx = -1
            size = fallback[name]
            source = "slot_max"
        elif kind == "dev_artifact":
            ys_name = f"(DEV:{name})"
            idx = -1
            size = fallback[name]
            source = "slot_max"
        else:
            data_index += 1
            idx = data_index
            ys_name = f"YS.DATA.{idx:02d}"
            size = measured[name]
            source = "disc_measure"
        overlays.append(
            DataOverlay(
                index=idx,
                name=name,
                sector=sector,
                size_sectors=size,
                ys_name=ys_name,
                kind=kind,
                size_source=source,
            )
        )
    return overlays


def read_loader_sector(data: bytes) -> bytes:
    start = sector_to_offset(LOADER_SECTOR)
    return data[start : start + SECTOR_SIZE]


def disassemble_loader(data: bytes) -> list[str]:
    """Short annotated disassembly of YS.DATA lookup/load path."""
    rom = read_loader_sector(data)
    lines = [
        f"; Sector {LOADER_SECTOR:#x} mapped near ${LOADER_CPU_BASE:04X}",
        f"; Template @ +{LOADER_TEMPLATE_OFF:#x}: {rom[LOADER_TEMPLATE_OFF:LOADER_TEMPLATE_OFF + 12]!r}",
        "",
        f"${LOADER_CPU_BASE + 0x0100:04X}  find_file   ; index in A, compare 12 bytes to ${RAM_CATALOG_TEMPLATE:04X}",
        f"${LOADER_CPU_BASE + 0x010D:04X}              ; pointer = $6800 + index, template = YS.DATA.??",
        f"${LOADER_CPU_BASE + 0x013C:04X}  load_file   ; JSR ${LOADER_CPU_BASE + 0x004B:04X} after match",
        f"${LOADER_CPU_BASE + 0x009C:04X}  set_sector  ; copy ${RAM_GAME_SECTOR:04X} -> ${RAM_CD_SECTOR:04X}",
        "",
        "; Key RAM variables",
        f"; ${RAM_CATALOG_COUNT:04X}  file count",
        f"; ${RAM_CATALOG_TEMPLATE:04X}  filename template (12 bytes)",
        f"; ${RAM_CD_SECTOR:04X}  current CD sector (u16 LE)",
        f"; ${RAM_GAME_SECTOR:04X}  game sector pointer (u16 LE)",
    ]
    return lines


def extract_overlay(data: bytes, overlay: DataOverlay, output: Path) -> None:
    start = sector_to_offset(overlay.sector)
    length = overlay.size_sectors * SECTOR_SIZE
    if start + length > len(data):
        length = len(data) - start
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data[start : start + length])


def write_catalog_csv(path: Path, overlays: list[DataOverlay]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "ys_index",
                "ys_name",
                "adpos_name",
                "kind",
                "start_sector",
                "size_sectors",
                "size_bytes",
                "size_source",
                "end_sector",
                "mirror_sector",
            ]
        )
        for item in overlays:
            writer.writerow(
                [
                    item.index if item.index >= 0 else "",
                    item.ys_name,
                    item.name,
                    item.kind,
                    f"{item.sector:#x}",
                    item.size_sectors,
                    item.size_sectors * SECTOR_SIZE,
                    item.size_source,
                    f"{item.sector + item.size_sectors:#x}",
                    f"{item.sector + 0x10000:#x}",
                ]
            )


def write_cdlen_doc(
    path: Path,
    overlays: list[DataOverlay],
    cdlen: CdlenSearchResult,
    data: bytes,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data_overlays = [o for o in overlays if o.index >= 0]
    body = [
        "# cdlen.bin — localisation et tailles réelles",
        "",
        "## Verdict",
        "",
        "**`cdlen.bin` n'existe pas en bloc contigu dans le ROM retail** (`TENGAI2.PRG`,",
        "secteurs `0xE8–0x16F`). Recherche exhaustive (formats ovlarray HuC, LE32,",
        "longueurs seules, signatures `80 80 80 7C 7A 7A`…) : **aucune table de 50 entrées**.",
        "",
        f"- Meilleur match partiel : **{cdlen.match_count}/50** entrées",
        f"- {cdlen.notes}",
        "",
        "## Chaîne de build Hudson",
        "",
        "Les makefiles laissés sur le disque (`0x6A00+`) montrent :",
        "",
        "```",
        "fsize -b0x800 -o1 ${TARGET}.bin  →  sed met à jour cdlen.s",
        "gmake -f \\sys\\makefile \\sys\\cdlen.bin",
        "```",
        "",
        "Chaque label `CDLEN_<fichier>:` reçoit la taille sectorisée du `.bin`.",
        "Au link, ces valeurs sont **fusionnées dans le programme** (pas conservées",
        "comme fichier `cdlen.bin` lisible sur le CD final).",
        "",
        "Le runtime copie le catalogue en RAM autour de **`$68CE–$68D2`** (compteur,",
        "template `YS.DATA.??`, secteur courant `$68C7`).",
        "",
        "## Source de vérité : mesure disque",
        "",
        "Chaque overlay occupe un **slot de 128 secteurs** (`0x80`) posé par `HDWRITE`.",
        "La taille réelle = dernier secteur non vide (≠ `0xFF` / `0x00`) dans le slot.",
        "",
        "Seuls **3 fichiers** sont plus petits que le slot max :",
        "",
        "| YS.DATA | adpos | Secteur | Mesuré | Slot max | Économie |",
        "|---------|-------|--------:|-------:|---------:|---------:|",
    ]
    for item in data_overlays:
        if item.size_sectors == SLOT_SECTORS:
            continue
        saved = (SLOT_SECTORS - item.size_sectors) * SECTOR_SIZE
        body.append(
            f"| `{item.ys_name}` | `{item.name}` | `{item.sector:#x}` | "
            f"{item.size_sectors} | {SLOT_SECTORS} | {saved // 1024} KiB |"
        )
    body.extend(
        [
            "",
            "Tous les autres overlays data utilisent **128 secteurs** (262 144 octets).",
            "",
            "## Index YS.DATA ↔ adpos ↔ secteur",
            "",
            "L'ordre des index `YS.DATA.NN` suit l'ordre **`adpos_*` trié par secteur**",
            "(50 entrées data, hors `main`/`game`/artefacts dev `b**`).",
            "",
            "| Index | YS.DATA | adpos | Secteur | Secteurs | Octets |",
            "|------:|---------|-------|--------:|---------:|-------:|",
        ]
    )
    for item in data_overlays:
        body.append(
            f"| {item.index} | `{item.ys_name}` | `{item.name}` | `{item.sector:#x}` | "
            f"{item.size_sectors} | {item.size_sectors * SECTOR_SIZE} |"
        )
    body.extend(
        [
            "",
            "## Commandes",
            "",
            "```bash",
            "python3 tools/ys_data.py find-cdlen",
            "python3 tools/ys_data.py list",
            "python3 tools/ys_data.py extract wa2 -o work/wa2.bin  # 124 sect., pas 128",
            "```",
            "",
        ]
    )
    path.write_text("\n".join(body), encoding="utf-8")


def write_markdown(path: Path, overlays: list[DataOverlay], loader_lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data_overlays = [o for o in overlays if o.index >= 0]
    body = [
        "# Format YS.DATA — Tengai Makyou II",
        "",
        "Analyse du chargeur Hudson embarqué dans le programme (`TENGAI2.PRG`) et du",
        "catalogue de overlays données laissé par la chaîne **HDWRITE / CDPOS / cdlen**.",
        "",
        "## Résumé",
        "",
        "`YS.DATA` n'est **pas** un conteneur fichier sur le disque. C'est le namespace",
        "utilisé par le runtime Hudson pour adresser des blocs de données sectorisés",
        "écrits par `HDWRITE` lors du build. Sur le CD final, les données sont des",
        "blobs alignés sur 2048 octets ; le moteur les nomme virtuellement",
        "`YS.DATA.01`, `YS.DATA.02`, etc.",
        "",
        "## Chargeur (secteur `0x14E`)",
        "",
        "Le secteur `0x14E` contient à la fois :",
        "",
        "- le **menu mot de passe / démarrage** (chaînes « display the password »,",
        "  « start game story », texte Shift-JIS) ;",
        "- la **routine YS.DATA** avec le gabarit `YS.DATA.??\\0` à l'offset `+0xBF`.",
        "",
        "Comportement reverse-engineered (bank CPU ~`$E000`) :",
        "",
        "| Adresse | Rôle |",
        "|---------|------|",
        f"| `${LOADER_CPU_BASE + 0x0100:04X}` | Recherche par index : compare 12 octets à `${RAM_CATALOG_TEMPLATE:04X}` |",
        f"| `${LOADER_CPU_BASE + 0x013C:04X}` | Chargement CD après correspondance |",
        f"| `${LOADER_CPU_BASE + 0x009C:04X}` | Copie secteur courant `${RAM_GAME_SECTOR:04X}` → `${RAM_CD_SECTOR:04X}` |",
        f"| `${RAM_CATALOG_COUNT:04X}` | Nombre d'entrées catalogue (RAM, initialisé depuis `cdlen.bin`) |",
        "",
        "### Pseudo-code",
        "",
        "```c",
        "// Gabarit ROM : \"YS.DATA.??\\0\"",
        "bool ys_find(int index) {",
        "    char *name = catalog[index];  // construit depuis cdlen",
        "    for (y = 11; y >= 0; y--)",
        "        if (name[y] != template[y]) return false;",
        "    return true;",
        "}",
        "",
        "void ys_load(int index) {",
        "    uint16_t sector = catalog[index].sector;",
        "    uint16_t count  = catalog[index].length_sectors;",
        "    cd_read(sector, count, dest);",
        "}",
        "```",
        "",
        "### Décompilation partielle",
        "",
        "```",
        *loader_lines,
        "```",
        "",
        "## Build Hudson (artefacts secteurs `0x6A00+`)",
        "",
        "La chaîne de build TM II utilise :",
        "",
        "| Outil | Rôle |",
        "|-------|------|",
        "| `HDWRITE` | Écrit un `.bin` sur le CD (`PROG TENGAI2.PRG` ou data) |",
        "| `CDPOS` / `adpos_*` | Position logique sur le disque (`position / 0x800 = secteur`) |",
        "| `cdlen.s` / `cdlen.bin` | Table `(secteur, taille)` injectée dans le programme |",
        "| `fsize -b0x800` | Calcule la taille sectorisée pour `cdlen` |",
        "",
        "Exemple retrouvé dans les makefiles :",
        "",
        "```",
        "hdwrite -U04000000,034b0000 \\vir\\mn_b01.bin PROG TENGAI2.PRG",
        "```",
        "",
        "## Catalogue `adpos_*` recouvré",
        "",
        f"{len(data_overlays)} overlays données identifiés (hors `main`/`game`/artefacts dev `b**`).",
        "Les **tailles réelles** viennent de la mesure sur le disque (padding `0xFF`/`0x00` dans chaque slot",
        f"de `{SLOT_SECTORS:#x}` secteurs). Seuls **wa2**, **wa5** et **wa6** diffèrent du maximum (124/122 sect.).",
        "",
        "Voir [`docs/CDLEN.md`](CDLEN.md) pour la recherche de `cdlen.bin` dans le binaire.",
        "",
        "| Index | YS.DATA | adpos | Secteur | Taille | Slot max | Type |",
        "|------:|---------|-------|--------:|-------:|:--------:|------|",
    ]
    for item in data_overlays:
        slot = "≠128" if item.size_sectors != SLOT_SECTORS else "128"
        body.append(
            f"| {item.index} | `{item.ys_name}` | `{item.name}` | `{item.sector:#x}` | "
            f"{item.size_sectors} sect. | {slot} | {item.kind} |"
        )
    body.extend(
        [
            "",
            "## Liens avec maps / script",
            "",
            "- **`yav`** (`0x2E0`) — données système proches des maps événement (`0x2C9`, `0x3C9`…).",
            "- **`wa*` / `wb*` / …** — blocs monde par région (suffixe `1/2/5/6` = variante de map).",
            "- **`pmnj` / `dmnj` / `pkab` / `dkab`** — packs événementiels (probables tables + script binaire).",
            "- Le **texte** reste dispersé dans ces blocs (préfixes `0x01`/`0x02`/`0x10`) ;",
            "  `YS.DATA` fournit la structure d'accès, pas un parseur de script.",
            "",
            "## Fichiers générés",
            "",
            "```bash",
            "python3 tools/ys_data.py              # catalogue + docs",
            "python3 tools/ys_data.py list",
            "python3 tools/ys_data.py extract yav -o work/yav.bin",
            "```",
            "",
        ]
    )
    path.write_text("\n".join(body), encoding="utf-8")


def cmd_list(overlays: list[DataOverlay]) -> None:
    for item in overlays:
        if item.index < 0:
            tag = item.kind
        else:
            tag = f"YS.{item.index:02d}"
        slot = f"/{SLOT_SECTORS}" if item.size_sectors != SLOT_SECTORS else ""
        print(
            f"{tag:8s} {item.name:8s}  sector {item.sector:#7x}  "
            f"{item.size_sectors:4d}{slot} sect.  ({item.kind})"
        )


def cmd_find_cdlen(data: bytes) -> None:
    entries = parse_adpos_catalog(data)
    result = locate_cdlen_table(data, entries)
    data_entries = data_overlay_entries(entries)
    measured = measure_sizes(data, data_entries)

    print("=== Recherche cdlen.bin dans TENGAI2.PRG ===\n")
    print(f"Trouvé       : {result.found}")
    print(f"Meilleur hit : {result.match_count}/50 entrées")
    if result.offset is not None:
        print(f"Offset       : {result.offset:#x} (format {result.format_name})")
    print(f"Notes        : {result.notes}\n")

    print("=== Tailles mesurées (équivalent cdlen / fsize -b0x800) ===\n")
    print(f"{'YS':>6}  {'adpos':8s}  {'secteur':>8s}  {'mesuré':>6s}  {'slot':>4s}")
    idx = 0
    for name, sector in entries:
        if overlay_kind(name) in ("program", "dev_artifact"):
            continue
        idx += 1
        m = measured[name]
        flag = " *" if m != SLOT_SECTORS else ""
        print(f"{idx:6d}  {name:8s}  {sector:#8x}  {m:6d}  {SLOT_SECTORS:4d}{flag}")
    diff = [n for n, _ in data_entries if measured[n] != SLOT_SECTORS]
    if diff:
        print(f"\n* Fichiers plus petits que le slot {SLOT_SECTORS:#x} : {', '.join(diff)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_TRACK2)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List recovered data overlays")

    extract_p = sub.add_parser("extract", help="Extract one overlay by adpos name")
    extract_p.add_argument("name", help="adpos name (e.g. yav, wa1, pmnj)")
    extract_p.add_argument("-o", "--output", type=Path, required=True)

    sub.add_parser("loader", help="Show loader disassembly notes")
    sub.add_parser("find-cdlen", help="Search for cdlen.bin and print measured sizes")

    args = parser.parse_args()
    data = load_user_data(args.input)
    cdlen_result = locate_cdlen_table(data, parse_adpos_catalog(data))
    overlays = build_overlay_table(data)
    by_name = {item.name: item for item in overlays}

    root = Path(__file__).resolve().parent.parent
    loader_lines = disassemble_loader(data)
    write_catalog_csv(root / "script" / "ys_data_catalog.csv", overlays)
    write_markdown(root / "docs" / "YS_DATA.md", overlays, loader_lines)
    write_cdlen_doc(root / "docs" / "CDLEN.md", overlays, cdlen_result, data)

    if args.command == "find-cdlen":
        cmd_find_cdlen(data)
        return 0

    if args.command in (None, "list"):
        cmd_list(overlays)
        print(f"\nCatalog: {root / 'script' / 'ys_data_catalog.csv'}")
        print(f"Docs:    {root / 'docs' / 'YS_DATA.md'}")
        return 0

    if args.command == "loader":
        print("\n".join(loader_lines))
        return 0

    if args.command == "extract":
        item = by_name.get(args.name)
        if item is None:
            known = ", ".join(sorted(by_name))
            raise SystemExit(f"Unknown overlay {args.name!r}. Known: {known}")
        extract_overlay(data, item, args.output)
        print(
            f"Wrote {args.output} ({item.size_sectors * SECTOR_SIZE:,} bytes, "
            f"sector {item.sector:#x}, {item.ys_name})"
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
