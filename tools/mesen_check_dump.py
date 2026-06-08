#!/usr/bin/env python3
"""Vérifie qu'un dump Mesen CPU (64 KiB) a été pris au bon moment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROM_SIG = bytes([0xA9, 0x00, 0x85, 0xFF, 0x20, 0xD8, 0xE0])  # static $51BA
JMP_TABLE = bytes([0x4C, 0x0C, 0xFE])  # JMP $FE0C @ $E0D8
COPY_LOOP = bytes([0x91, 0xFA])  # STA ($FA),Y @ $EA9C
JSR_E0D8 = bytes([0x20, 0xD8, 0xE0])


def check(path: Path) -> int:
    data = path.read_bytes()
    if len(data) != 0x10000:
        print(f"⚠ Taille {len(data)} o — attendu 65536 (export CPU memory complet).")

    ok = 0
    region = data[0x51BA : 0x51BA + 7]
    if region == ROM_SIG:
        print("✗ $51BA = encore le code ROM statique (dump trop tôt ou mauvaise zone)")
    elif JSR_E0D8 in data[0x5100:0x5300]:
        print("✓ $51xx contient JSR $E0D8 (stub installé)")
        ok += 1
    else:
        print(f"? $51BA = {region.hex()} (état inconnu — pas le ROM retail, pas le stub attendu)")

    if data[0xE0D8 : 0xE0D8 + 3] == JMP_TABLE:
        print("✓ $E0D8 = table JMP Hudson (runtime actif)")
        ok += 1
    else:
        print(f"✗ $E0D8 = {data[0xE0D8:0xE0DB].hex()} (pas la table JMP — mauvais moment)")

    fe = data[0xFE0C : 0xFE0C + 8]
    if fe == b"\x00" * 8 or fe == b"\xff" * 8:
        print(f"✗ $FE0C vide ({fe.hex()}) — décompresseur absent")
    else:
        print(f"✓ $FE0C = code présent ({fe.hex()}…)")
        ok += 1

    if data[0xEA9C : 0xEA9C + 2] == COPY_LOOP:
        print("✓ $EA9C = boucle copie active (tu es pendant l'install)")
    else:
        print(f"○ $EA9C = {data[0xEA9C:0xEA9E].hex()} (install terminée ou pas encore là)")

    print(f"\nScore : {ok}/3 checks essentiels")
    if ok >= 2:
        print("→ Dump exploitable pour la suite RE.")
    else:
        print("→ Refaire le dump au bon moment (voir docs ci-dessous).")
    return 0 if ok >= 2 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path, nargs="?", default=Path("work/mesen_e000.bin"))
    args = parser.parse_args()
    if not args.dump.is_file():
        print(f"Fichier introuvable : {args.dump}", file=sys.stderr)
        return 2
    print(f"Fichier : {args.dump}\n")
    return check(args.dump)


if __name__ == "__main__":
    raise SystemExit(main())
