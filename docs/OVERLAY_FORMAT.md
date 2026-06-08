# Format des overlays carte (yav, wa*)

Analyse des blobs **YS.DATA** régionaux et des secteurs **event_map** associés.

## Architecture build Hudson

Chaque overlay (`yav`, `wa1`, …) est produit par :

```
$(LD) -b vir/wa1.bin /dataseg:0000,0 wa1.o mon/ef.o mp_wa1.o
sizechk 7 vir/wa1.bin
$(HDWRITE) -U$(PROGSIZE),adpos_wa1 vir/wa1.bin PROG TENGAI2.PRG
```

| Composant | Rôle |
|-----------|------|
| `wa1.o` | Données carte (mn\_*) |
| `mon/ef.o` | Événements communs région |
| `mp_wa1.o` | Métadonnées pack (`mp_*` = map pack) |
| `pack.awk` / `ivm2h.awk` | Concaténation + compression des segments |
| `HDWRITE` | Pose le `.bin` sur le CD (`adpos_*`) |

Artefacts visibles secteurs `0x6A00+` : catalogue du PC développeur Hudson listant
`LZSS.EXE`, `ZPRESS.EXE`, `MAPCV.EXE`, `MESCOM.EXE`, `ivm2h.awk`, `pack.awk`, etc.

**Important** : sur le CD **retail**, ce sont surtout des **entrées annuaire 32 o**
(nom + taille + horodatage). Les **binaires des outils ne sont pas embarqués** —
`work/lzss.exe` est un faux positif (`MZ` coincident dans le catalogue, pas un vrai EXE).

## Segments pack (ivm2h)

Spécification retrouvée dans les artefacts build (`/vector+tpseg:6000,580` …) :

| Segment | RAM | Taille max | Contenu probable |
|---------|-----|------------|------------------|
| `data1` | `$8000` | `$600` | Auxiliaire carte |
| `data2` | `$0000` | `$640` | Auxiliaire |
| `data3` | `$0000` | `$6E0` | Auxiliaire |
| `adpcm_a` | `$0000` | `$7C0` | Voix ADPCM |
| **`vector+tpseg`** | **`$6000`** | **`$580`** | **Tilemap / tuiles (VRAM `$6000`)** |
| **`evtseg+mstseg+messeg`** | **`$0100`** | **`$581`** | **Script + tables monstres/NPC + messages** |
| `vector2+data1` | `$6000` | `$580` | Seconde couche tilemap |
| `adpcm_b` | `$FF` | `$7FF` | ADPCM suite |

Les noms **`mstseg`** (monster) et **`messeg`** (message) indiquent que NPC/dialogues vivent dans le bloc script, pas dans le tilemap.

## État du décompression

Les overlays **`yav`** et **`wa1`** sur le CD final sont **compressés** (entropie élevée, pas d'en-tête LZSS/Okumura standard).

- LZSS Okumura (entêtes 0/2/4 o), PRS Sega, décompresseur maps Ziria : **échec**
- Exécution `LZSS.EXE` / `ZPRESS.EXE` : **impossible** sans les vrais binaires (absents du dump)

**Conséquence** : la séparation tilemap / NPC / script dans `yav.bin` / `wa1.bin` bruts
nécessite l'algorithme **ZPRESS/IVCOM** (outils build absents du retail) ou la routine
runtime **`JSR $E0D8`** dispatchée par **`$51BA`** dans `TENGAI2.PRG`.

Reverse détaillé : [`docs/PRG_DECOMPRESS.md`](PRG_DECOMPRESS.md) — le motif `$580` à
`prog+0x880f` est un faux positif (table bytecode script, pas tailles ivm2h).

Spécification ivm2h retrouvée sur le disque :

```
/vector+tpseg:6000,580 /evtseg+mstseg+messeg:100,581 … /adpcm:ff,7ff
```

## Format secteur event_map (référence 1×2048 o)

Les maps **jouables** repérées par `map_sectors.py` (ex. secteur **`0x2C9`**) ne sont **pas** embarquées dans `yav`/`wa1` — ce sont des secteurs CD autonomes, proches de `yav` (`0x2E0`).

Structure reverse-engineered (ex. `0x2C9`, entités 野良犬 / 狂犬) :

| Offset | Région | Taille typique |
|--------|--------|----------------|
| `0x000` | **`binary_header`** — tilemap / collision / bytecode (compressé ou encodé) | ~`0x76a` (1898 o) |
| `0x76a` | **`entity_labels`** — `\x01\x00\x00\x00\x00` + nom SJIS + `\x00` | variable |
| suite | **`npc_table`** — enregistrements binaires (coords, pointeurs `$82xx`…) | reste du secteur |

Marqueurs script TM II dans tout le secteur : `0x01` (label), `0x02` (dialogue court), `0x10` + arg (dialogue `$0` / `$n`).

## Correspondance yav ↔ maps

| Fichier | Secteur CD | Rôle |
|---------|------------|------|
| `yav` | `0x2E0` | Pack système / vecteurs région (128 sect.) |
| event `0x2C9` | `0x2C9` | Map 野良犬 (23 sect. avant `yav`) |
| `wa1` | `0x860` | Pack monde région 尾張 variante 1 |

Les overlays **`wa*`** agrègent les assets d'une **région** ; les secteurs **`0x2C9`**, **`0x3C9`**, … sont les **instances** chargées au runtime.

## Commandes

```bash
# Résumé overlay
python3 tools/overlay_parse.py info yav
python3 tools/overlay_parse.py info wa1

# Analyse JSON (+ chaînes SJIS survivantes)
python3 tools/overlay_parse.py parse wa1 -o work/wa1_parse

# Parser une map 1-secteur (format de référence)
python3 tools/overlay_parse.py parse-event 0x2C9 -o work/event_02c9

# Extraire blob + tenter décompression pack (segments vides si échec)
python3 tools/overlay_parse.py split yav -o work/yav_split
python3 tools/overlay_parse.py split wa1 -o work/wa1_split

# Catalogue outils build + tentative décompression dédiée
python3 tools/hudson_pack.py catalog -o work/tool_catalog.json
python3 tools/hudson_pack.py decompress wa1 -o work/wa1_split
```

## Prochaine étape RE

1. Extraire l'algo RAM Hudson **`$E0D8`** (trace Mednafen ou ZPRESS hors dump) — voir [`PRG_DECOMPRESS.md`](PRG_DECOMPRESS.md)
2. Brancher le décompresseur dans `hudson_pack.py` → remplir `{name}_{segment}.bin`
3. Valider tilemap (`tpseg`) vs script (`evtseg`) sur un `wa1` décompressé
4. Corréler pointeurs NPC avec `script/tm2_text_filtered.csv`

```bash
python3 tools/prg_unpack_re.py report
```
