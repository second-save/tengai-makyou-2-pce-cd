# cdlen.bin — localisation et tailles réelles

## Verdict

**`cdlen.bin` n'existe pas en bloc contigu dans le ROM retail** (`TENGAI2.PRG`,
secteurs `0xE8–0x16F`). Recherche exhaustive (formats ovlarray HuC, LE32,
longueurs seules, signatures `80 80 80 7C 7A 7A`…) : **aucune table de 50 entrées**.

- Meilleur match partiel : **0/50** entrées
- No contiguous cdlen.bin table in TENGAI2.PRG (0xE8–0x16F). Build chain: fsize -b0x800 → cdlen.s → cdlen.bin, merged at link time. Retail ROM likely uses scattered CDLEN_* equates copied to RAM $68xx at init.

## Chaîne de build Hudson

Les makefiles laissés sur le disque (`0x6A00+`) montrent :

```
fsize -b0x800 -o1 ${TARGET}.bin  →  sed met à jour cdlen.s
gmake -f \sys\makefile \sys\cdlen.bin
```

Chaque label `CDLEN_<fichier>:` reçoit la taille sectorisée du `.bin`.
Au link, ces valeurs sont **fusionnées dans le programme** (pas conservées
comme fichier `cdlen.bin` lisible sur le CD final).

Le runtime copie le catalogue en RAM autour de **`$68CE–$68D2`** (compteur,
template `YS.DATA.??`, secteur courant `$68C7`).

## Source de vérité : mesure disque

Chaque overlay occupe un **slot de 128 secteurs** (`0x80`) posé par `HDWRITE`.
La taille réelle = dernier secteur non vide (≠ `0xFF` / `0x00`) dans le slot.

Seuls **3 fichiers** sont plus petits que le slot max :

| YS.DATA | adpos | Secteur | Mesuré | Slot max | Économie |
|---------|-------|--------:|-------:|---------:|---------:|
| `YS.DATA.04` | `wa2` | `0x8e0` | 124 | 128 | 8 KiB |
| `YS.DATA.05` | `wa5` | `0xa60` | 122 | 128 | 12 KiB |
| `YS.DATA.06` | `wa6` | `0xae0` | 122 | 128 | 12 KiB |

Tous les autres overlays data utilisent **128 secteurs** (262 144 octets).

## Index YS.DATA ↔ adpos ↔ secteur

L'ordre des index `YS.DATA.NN` suit l'ordre **`adpos_*` trié par secteur**
(50 entrées data, hors `main`/`game`/artefacts dev `b**`).

| Index | YS.DATA | adpos | Secteur | Secteurs | Octets |
|------:|---------|-------|--------:|---------:|-------:|
| 1 | `YS.DATA.01` | `sdt` | `0x260` | 128 | 262144 |
| 2 | `YS.DATA.02` | `yav` | `0x2e0` | 128 | 262144 |
| 3 | `YS.DATA.03` | `wa1` | `0x860` | 128 | 262144 |
| 4 | `YS.DATA.04` | `wa2` | `0x8e0` | 124 | 253952 |
| 5 | `YS.DATA.05` | `wa5` | `0xa60` | 122 | 249856 |
| 6 | `YS.DATA.06` | `wa6` | `0xae0` | 122 | 249856 |
| 7 | `YS.DATA.07` | `wb1` | `0xc60` | 128 | 262144 |
| 8 | `YS.DATA.08` | `wb2` | `0xce0` | 128 | 262144 |
| 9 | `YS.DATA.09` | `wb5` | `0xe60` | 128 | 262144 |
| 10 | `YS.DATA.10` | `wb6` | `0xee0` | 128 | 262144 |
| 11 | `YS.DATA.11` | `wc1` | `0x1060` | 128 | 262144 |
| 12 | `YS.DATA.12` | `wc2` | `0x10e0` | 128 | 262144 |
| 13 | `YS.DATA.13` | `wc5` | `0x1260` | 128 | 262144 |
| 14 | `YS.DATA.14` | `wc6` | `0x12e0` | 128 | 262144 |
| 15 | `YS.DATA.15` | `wg1` | `0x2060` | 128 | 262144 |
| 16 | `YS.DATA.16` | `wg2` | `0x20e0` | 128 | 262144 |
| 17 | `YS.DATA.17` | `wg5` | `0x2260` | 128 | 262144 |
| 18 | `YS.DATA.18` | `wg6` | `0x22e0` | 128 | 262144 |
| 19 | `YS.DATA.19` | `wh1` | `0x2460` | 128 | 262144 |
| 20 | `YS.DATA.20` | `wh2` | `0x24e0` | 128 | 262144 |
| 21 | `YS.DATA.21` | `wh5` | `0x2660` | 128 | 262144 |
| 22 | `YS.DATA.22` | `wh6` | `0x26e0` | 128 | 262144 |
| 23 | `YS.DATA.23` | `xi1` | `0x2860` | 128 | 262144 |
| 24 | `YS.DATA.24` | `xi2` | `0x28e0` | 128 | 262144 |
| 25 | `YS.DATA.25` | `xi5` | `0x2a60` | 128 | 262144 |
| 26 | `YS.DATA.26` | `xi6` | `0x2ae0` | 128 | 262144 |
| 27 | `YS.DATA.27` | `xj1` | `0x2c60` | 128 | 262144 |
| 28 | `YS.DATA.28` | `xj2` | `0x2ce0` | 128 | 262144 |
| 29 | `YS.DATA.29` | `xj5` | `0x2e60` | 128 | 262144 |
| 30 | `YS.DATA.30` | `xj6` | `0x2ee0` | 128 | 262144 |
| 31 | `YS.DATA.31` | `xk1` | `0x3060` | 128 | 262144 |
| 32 | `YS.DATA.32` | `xk2` | `0x30e0` | 128 | 262144 |
| 33 | `YS.DATA.33` | `xk5` | `0x3260` | 128 | 262144 |
| 34 | `YS.DATA.34` | `xk6` | `0x32e0` | 128 | 262144 |
| 35 | `YS.DATA.35` | `yo1` | `0x4060` | 128 | 262144 |
| 36 | `YS.DATA.36` | `yo2` | `0x40e0` | 128 | 262144 |
| 37 | `YS.DATA.37` | `yo5` | `0x4260` | 128 | 262144 |
| 38 | `YS.DATA.38` | `yo6` | `0x42e0` | 128 | 262144 |
| 39 | `YS.DATA.39` | `yp1` | `0x4460` | 128 | 262144 |
| 40 | `YS.DATA.40` | `yp2` | `0x44e0` | 128 | 262144 |
| 41 | `YS.DATA.41` | `yp5` | `0x4660` | 128 | 262144 |
| 42 | `YS.DATA.42` | `yp6` | `0x46e0` | 128 | 262144 |
| 43 | `YS.DATA.43` | `yq1` | `0x4860` | 128 | 262144 |
| 44 | `YS.DATA.44` | `yq2` | `0x48e0` | 128 | 262144 |
| 45 | `YS.DATA.45` | `yq5` | `0x4a60` | 128 | 262144 |
| 46 | `YS.DATA.46` | `yq6` | `0x4ae0` | 128 | 262144 |
| 47 | `YS.DATA.47` | `pmnj` | `0x5060` | 128 | 262144 |
| 48 | `YS.DATA.48` | `dmnj` | `0x50e0` | 128 | 262144 |
| 49 | `YS.DATA.49` | `pkab` | `0x5260` | 128 | 262144 |
| 50 | `YS.DATA.50` | `dkab` | `0x52e0` | 128 | 262144 |

## Commandes

```bash
python3 tools/ys_data.py find-cdlen
python3 tools/ys_data.py list
python3 tools/ys_data.py extract wa2 -o work/wa2.bin  # 124 sect., pas 128
```
