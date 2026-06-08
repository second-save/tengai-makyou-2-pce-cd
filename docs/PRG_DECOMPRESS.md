# Décompression pack runtime — TENGAI2.PRG

Reverse de la chaîne **chargement overlay → décompression pack → segments ivm2h**
pour `yav`, `wa1`, etc.

## Résumé

| Élément | Adresse CPU | Fichier (TENGAI2.PRG) | Rôle |
|---------|-------------|------------------------|------|
| Chargeur YS.DATA (miroir) | `$E000`–`$E1xx` | `prog+0x33000` | Copie secteur `0x14E` en RAM |
| Décompresseur pack | **`$E0D8`** / **`$E0C9`** | `prog+0x330D8` (padding) / `$E0E0` effectif | Hudson runtime CD |
| Dispatcher 9 segments | **`$51BA`** | `prog+0x51BA` | Boucle `JSR $E0D8` |
| Variante partielle | `$2FEC1` | `prog+0x2FEC1` | Segments 1–8, `JMP $E0D8` |
| Métadonnées segment | `$5260` | `prog+0x5260` | Tables `$8A35` / `$8A90` → `JSR $E0C9` |
| Appel overlay `wa*` | — | `prog+0x41114` | `JSR $17B0` → `JSR $51BA` |

**Constat sur `$580` / `$581` :** la référence « `prog+0x880f` » est un **faux positif**.
À `prog+0x880f` on lit `80 05` comme u16 LE (`$0580`), mais c’est la **frontière**
entre deux pointeurs script (`$80D4` puis `$8105`) dans la table Hudson `f0/c0/d0/e0`
— pas une table de tailles ivm2h. Les vraies tailles max viennent de la spec build
`/vector+tpseg:6000,580` (voir `tools/hudson_pack.py` → `PACK_SEGMENTS`).

## Protocole `JSR $E0D8` (décompresseur)

Avant chaque appel, le dispatcher pose :

| ZP / abs | Rôle |
|----------|------|
| **`$FF`** | Index du segment dans le blob pack compressé (0, 2, 3, 4, 6, 7, 8, 9, …) |
| **`$F8` / `$F9`** | Adresse destination 16-bit LE (où écrire le segment décompressé) |
| **`$FC` / `$FD`** | Pointeur source 16-bit LE dans le buffer pack (initialisé tôt au boot, ex. `prog+0x00D2`) |
| **`$FFF5`** | Pointeur pack courant (abs) ; segment 3 fait `ADC $FFF5` pour une dest. dynamique |

Test minimal au boot (`prog+0x01F6`) :

```asm
; STA ZP$FF / JSR $E0D8 — segment 0, destination par défaut
$01F6  STA $FF
$01FB  JSR $E0D8
```

## Dispatcher `$51BA` (décompression complète overlay)

Désassemblage (Hu6280, adresse fichier = adresse CPU dans la banque programme) :

```asm
$51BA  LDA #$00
$51BC  STA $FF          ; segment 0
$51BE  JSR $E0D8

$51C1  LDA #$02
$51C3  STA $F8
$51C5  LDA #$02
$51C7  STA $FF          ; segment 2 → $0202
$51C9  JSR $E0D8

$51CC  LDA #$04
$51CE  CLC
$51CF  ADC $FFF5        ; dest = pack_ptr + 4
$51D2  STA $F8
$51D4  INA              ; ($1A)
$51D5  STA $F9
$51D7  LDA #$03
$51D9  STA $FF          ; segment 3
$51DB  JSR $E0D8

$51DE  LDA #$00
$51E0  STA $F8
$51E2  LDA #$80
$51E4  STA $F9
$51E6  LDA #$04
$51E8  STA $FF          ; segment 4 → $8000 (data1 ivm2h)
$51EA  JSR $E0D8

$51ED  LDA #$61
$51EF  STA $F8
$51F1  LDA #$82
$51F3  STA $F9
$51F5  LDA #$06
$51F7  STA $FF          ; segment 6 → $8261
$51F9  JSR $E0D8

$51FC  LDA #$0D
$51FE  STA $F8
$5200  LDA #$82
$5202  STA $F9
$5204  LDA #$07
$5206  STA $FF          ; segment 7 → $820D
$5208  JSR $E0D8

$520B  LDA #$D2
$520D  STA $F8
$520F  LDA #$81
$5211  STA $F9
$5213  LDA #$08
$5215  STA $FF          ; segment 8 → $81D2
$5217  JSR $E0D8

$521A  LDA #$02
$521C  STA $F8
$521E  LDA #$80
$5220  STA $F9
$5224  LDA #$09
$5226  STA $FF          ; segment 9 → $8002
$5226  JSR $E0D8
$5229  RTS

; variante (2e entrée) @ $522A : segment $0B
$522C  LDA #$0B
$522E  STA $FF
$5230  JSR $E0D8
```

### Correspondance ivm2h (hypothèse validée partiellement)

| Index `$FF` | Dest RAM | Segment ivm2h probable |
|:-----------:|:--------:|------------------------|
| 0 | (défaut) | en-tête / méta pack |
| 2 | `$0202` | table auxiliaire |
| 3 | `$FFF5+4` | `data2` / pointeur dynamique |
| 4 | **`$8000`** | **`data1`** (`max $600`) |
| 6 | `$8261` | `data3` ou ADPCM |
| 7 | `$820D` | suite carte |
| 8 | `$81D2` | suite carte |
| 9 | `$8002` | seconde banque `$8000` |
| `$0B` | (via `$522A`) | `adpcm_b` ? |

Les segments **tilemap `$6000/$580`** et **script `$0100/$581`** ne reçoivent pas
d’adresse explicite dans `$51BA` : ils sont probablement atteints via la dest.
par défaut du segment 0 ou via recopie ultérieure (`$17B0`, `$3821`).

## Chaîne d’appel overlay (`wa1`, …)

```
prog+0x41114  JSR $17B0    ; prépare banque / pointeurs ($E07B, cdlen)
              JSR $51BA    ; décompresse tous les segments pack
              JSR $3821    ; post-traitement
              JSR $5196    ; finalisation
```

`$17B0` saute dans le runtime Hudson (`JMP $E07B`, `JSR $E0A2`) et lit des
entrées **cdlen** en `$5031+x` → ZP `$36`–`$38` (secteur / taille overlay).

Chargement CD amont (`prog+0x400DF`) :

```asm
$400DF  STA $F5          ; index overlay dans le catalogue
$400E1  JSR $3836        ; lecture CD → buffer pack en RAM
```

## Runtime Hudson `$E000` (secteur `0x14E`)

Le programme contient un **miroir** du secteur chargeur :

- Gabarit `YS.DATA.??\0` : `prog+0x330BF` (= `$E0BF`)
- Base : **`prog+0x33000` ↔ `$E000`**

Fonctions repérées dans le miroir :

| CPU | Rôle |
|-----|------|
| `$E04B` | Prépare lecture CD (`JSR $6879`) |
| `$E057` | Lance décompression (`JSR $6872`, `JSR $4A20`) |
| `$E09C` | Copie `$2C79` → `$68C7` (secteur courant) |
| `$E100` | `find_file` (compare 12 octets à `$68D2`) |
| `$E13C` | `load_file` après correspondance catalogue |
| `$E0E0` | Entrée effective après padding `$E0D8`–`$E0DF` (`$00`…) |

**Note :** `$E0D8`–`$E0DF` sont des octets `$00` dans l’image statique (secteur
`0x14E` et miroir `prog+0x33000`). Le jeu appelle pourtant `JSR $E0D8` (19 refs
dans le PRG). Hypothèses : trampoline posé en RAM au boot Hudson, ou entrée
décalée vers `$E0E0`. L’algorithme bit-à-bit **n’est pas** dans le PRG aux
adresses appelées (`$5548`, `$746C` = padding `$FF` en ROM).

## `$5260` — tables segment `$8A35` / `$8A90`

Routine parallèle utilisant `JSR $E0C9` (sous-entrée du même runtime) :

- Lit métadonnées indexées par X dans `$8A35` / `$8A37`
- Compare `$FC` avec `$88` / `$38` (bornes du buffer pack)
- Sélectionne une taille / offset dans `$8A90`

Utile pour la suite RE (tailles réelles post-décompression, pas seulement max ivm2h).

## Ce qui n’est PAS le décompresseur pack

| Offset | Contenu réel |
|--------|----------------|
| `prog+0x8800` | Table **bytecode script** Hudson (pointeurs `$82xx`, opcodes `$F0/$C0/$D0/$E0`) |
| `prog+0x33F00` | Décodeur **texte SJIS** (filtres chiffres / lettres) |
| `prog+0x1E6E` | `LDA $0580` — accès **RAM absolue** `$0580`, pas `LDA #$580` |
| `prog+0xE0D8` (fichier) | Données, pas code (confusion avec adresse RAM) |

## Analyse `$FE0C` (dump `work/mesen_e000.bin`)

Le dump Mesen confirme que **`JSR $E0D8` → `JMP $FE0C`** via une table en
`$E0D8`–`$E0F0` (plus de padding `$00` statique).

```bash
python3 tools/mesen_disasm_fe0c.py work/mesen_e000.bin
python3 tools/mesen_check_dump.py work/mesen_e000.bin
```

### Chaîne d'appel

```
$51BA  STA $FF / STA $F8:$F9 / …
       JSR $E0D8
         → JMP $FE0C          ; index 0 — unpack segment pack
         → JMP $FE57          ; index 1 — variante (MPR6 = banque 3)
         → JMP $FE92          ; index 2 — vérif. en-tête AA/55 @ $18C1/$18C5
         → JMP $E6CF / $F730 … ; autres services Hudson CD
```

### Entrée `$FE0C` — dispatch par index `$FF`

Désassemblage HuC6280 (extrait) :

```asm
$FE0C  PHX
$FE0D  PHY
$FE0E  TMA #$40             ; lire MPR6
$FE10  PHA
$FE11  LDA #$02
$FE13  TAM #$40             ; MPR6 ← banque 2 ($C000–$DFFF)
$FE15  LDA zp$FF            ; index segment pack (posé par $51BA)
$FE17  CMP #$15             ; max 21 segments (0–20)
$FE19  BCS $FE22            ; index invalide → skip
$FE1B  ASL A                ; ×2 → offset table
$FE1C  TAX
$FE1D  LDA zp$F8            ; octet bas dest (passé aux handlers)
$FE1F  JSR $FE2A
$FE22  TAY / restaure MPR6 / PLY / PLX / RTS

$FE2A  JMP ($FE2D,X)        ; 21 handlers @ CPU $C0xx (vue $FExx + $3E00)
```

| ZP | Rôle confirmé |
|----|----------------|
| **`$FF`** | Index segment dans le blob pack |
| **`$F8` / `$F9`** | Destination LE (posée par `$51BA`) |
| **`$FC` / `$FD`** | Source pack (buffer compressé) |
| **`$FA`** | Pointeur d'écriture dest `(zp$FA),Y` côté stub `$51xx` |

**Alias banque :** avec `TAM #$40` / banque 2, une cible **`$C0xx`** correspond
à **`$FExx`** dans le dump (`+ $3E00`). Ex. handler seg. 0 : `$C000` → `$FE00`.

### Prologue segment 0 (`$FE00`) et chaîne `$FDCD`

Avant `$FE0C`, le handler 0 appelle une **série de sous-routines `$CDxx`**
(en banque MPR6), enchaînées depuis **`$FDCD`** / **`$FDDB`** :

```asm
$FDCD  BSR $FDA9            ; bascule MPR6 (save → bank 3 → restore)
       JSR $CD57
       …                    ; $CD92, $CDC3, $CDDB, $CE2E, $CE75, $CEC3
       JSR $CEC8            ; ← prologue $FE00
       JSR $CED2
       … → $FE0C
```

**`$FDA9`** : `TMA #$40` / `STA $22BB` / `LDA #03` / `TAM #$40` / `PLA` / `RTS`
— commutation MPR6 sauvegardée dans **`$22BB`**.

Les corps **`$CD12`–`$CED2`** ne sont **pas** visibles à `$CDxx` dans le dump
(MPR6 n'était pas en banque 2 au moment de l'export). Le cœur bitstream est
là — pas dans `$FE0C` lui-même (pas de `AND #$80` / LZSS évident dans
`$FE00`–`$FEC0`).

### I/O pack Card RAM (`$F730` / `$F76C`)

**`$F730`** copie les ZP vers des variables Hudson absolues :

| Abs | Source ZP |
|-----|-----------|
| `$224D`–`$224E` | `$FC`–`$FD` (source pack) |
| `$2250` | `$F8` (dest basse) |
| `$22C3`–`$22C4` | `$FA`–`$FB` |

**`$F76C`** dispatch sur **`$22C2`** (0–4) vers des routines qui pilotent
**`$1800`–`$1801`** (interface CD / buffer `@ $18000` Card RAM) — cohérent
avec les captures `LDA ($2A)` → `$18001`.

### Entrée `$FE92` — magie `AA 55`

Teste **`$18C5`=`$AA` et `$18C6`=`$55`** (sinon **`$18C1`/`$18C2`**) avant de
continuer ; retourne **`CLC`** si OK. Probable **signature d'en-tête pack** en
Card RAM (non capturée dans le dump CPU : zone `$18xx` = `$FF`).

### Résultat dump `mesen_decomp_*` (juin 2026)

| Élément | Statut |
|---------|--------|
| Dispatcher `$FE0C` / table 21 seg. | **OK** |
| Corps `$CD12`–`$CED2` (MPR6) | **OK** — 7685/8192 o non triviaux @ `$C000` |
| Card RAM | **OK** — 32 KiB, pas de `AA 55` en clair |
| Décompresseur Python sur `wa1.bin` | **Partiel** — émulateur HuC6280 `tools/hudson_huc6280.py` exécute le code MPR6 réel ; sortie ~19 o, pas encore valide |

```bash
python3 tools/mesen_check_decompress_dump.py   # score 5/6
python3 tools/mesen_disasm_cd.py               # carte $CDxx / bitstream
```

### Architecture algo (depuis `mesen_decomp_cpu.bin`)

**Driver segment `$CD12`** appelle en séquence :

| Routine | Rôle |
|---------|------|
| **`$CDF6`** | **VM bytecode** — octets `≥ $D0` dispatchés via table `@ $CE1D` |
| **`$D257`** | Bitstream littéral #1 (état `$255D` / `$24AF`, helpers `$D5E2`/`$D611`) |
| **`$D350`** | Backref quand tag `$25E1 & $F0 == $10` |
| **`$D422`** | Ajustement pointeurs (`$260D`, `$24EB`…) |
| **`$D510`** | Écriture segments décompressés vers dest |
| **`$D623` / `$D64D`** | Finalisation |

**Bitstream Hudson** (proche Ziria, pas identique Okumura) @ **`$C909`** / **`$D306`** :

```asm
; octet courant dans A (zp$EA)
AND #$80        ; test bit de commande
LSR A / LSR A / LSR A   ; 3 bits → zp$EB
; combiné avec nibble haut de $246E,X ou $25F9,X
```

Pas un simple `AND #$80` + 1 bit comme `tenma_mapdecmp.cpp` — **3 bits par pas** + état
en tables RAM `$24xx`–`$26xx`.

## Algorithme de compression

**Partiellement reversé** : code MPR6 capturé.

### Port strict (juin 2026)

**`tools/hudson_huc6280.py`** — émulateur HuC6280 minimal qui exécute le bytecode capturé
dans `work/mesen_decomp_cpu.bin` :

| Élément | Détail |
|---------|--------|
| Opcodes Hudson | `$44` BSR, `$62` CLA, `$22` SAX, `$B2` LDA (zp),Y, `$71` ADC (zp),Y, `$9E` STZ abs,X, … |
| Stubs | `$FF49` = lecture pack via `(zp$E8),Y` ; `$CF67` → BRK (fin VM : `JMP $CF5A` + `RTS` invalide) |
| Chaîne | `$CE07` (VM) → `$D257` → `$D350` → `$D422` → `$D510` |
| Intégration | `tools/hudson_vm.py` appelle l'émulateur par défaut (`use_emulator=True`) |

```bash
PYTHONPATH=tools python3 tools/hudson_huc6280.py wa1 --offset 0 -o work/huc6280_out.bin
PYTHONPATH=tools python3 tools/hudson_vm.py wa1 --offset 0x51f
```

**Blocage restant** : opcodes manquants dans `$D350`/`$D510`/`$D5E2`, routage sortie vers
destinations segment (`$8000`, `$0100`), init `$CDF6`/`$CD45` — sortie heuristique insuffisante.

Pistes restantes :

1. **Tracer `$CDF6`** sur un segment 0 de `wa1` (watch `$248B`/`$E8:$E9` source)
2. **Porter** la VM en Python dans `tools/hudson_pack.py`
3. **Comparer** nibble/3-bit stream avec Ziria (`tenma_mapdecmp.cpp`)

## Dumper le décompresseur `$CDxx` (Mesen2 — recommandé)

Pour capturer le **corps bitstream** (`$CD12`–`$CED2`) + **Card RAM** :

1. Lancer **Tengai II** (`.cue` + syscard 3.0+) dans **Mesen2**.
2. **Script Window → Load → `tools/mesen_dump_decompress.lua`**
3. Poser **un** breakpoint CPU (Execute) :
   - **`$FE1F`** ← recommandé (juste avant `JSR $FE2A`, MPR6 = banque 2)
   - ou **`$CEC8`** (1er `JSR` de la chaîne `$CDxx`)
4. Jouer jusqu’au **chargement d’une zone** (`wa1`, etc.) — pas pendant l’écran noir @ `$EA9C`.
5. À l’arrêt, le script écrit :

| Fichier | Contenu |
|---------|---------|
| `work/mesen_decomp_cpu.bin` | CPU `$0000`–`$FFFF` (64 KiB) |
| `work/mesen_decomp_c000.bin` | CPU `$C000`–`$DFFF` (fenêtre MPR6) |
| `work/mesen_decomp_cardram.bin` | Card RAM (32 KiB Super CD, ou 64 KiB Arcade) |
| `work/mesen_decomp_meta.txt` | PC, registres, score rapide |

6. Valider :

```bash
python3 tools/mesen_check_decompress_dump.py
```

Tu veux **≥ 3/6** checks, surtout **`$CD12+` non vide** dans le dump CPU ou C000.

## Dumper la RAM `$E000` (Mesen2)

1. Lancer **Tengai II** (`.cue` + syscard) dans **Mesen2**.
2. **Tools → Debugger** (cocher *Break when debugger is opened* si besoin).
3. Dans la fenêtre CPU : aller à **`$51BE`** (premier `JSR $E0D8` du unpack) → clic droit → **Toggle breakpoint**  
   (ou panneau Breakpoints → Add → type **CPU** / **Execute** @ `51BE`).
4. Lancer le jeu jusqu’au chargement d’une zone (ou s’arrêter tôt @ `$01FB` pour un boot minimal).
5. À l’arrêt : **Tools → Memory Tools → Memory Viewer** → liste **CPU memory** (ou équivalent PCE) → adresse **`E000`** → menu **Export** → `work/mesen_e000.bin` (plage `E000`–`E1FF`).

Script Lua automatique à chaque break :

```bash
# Dans Mesen2 : Script Window → Load → tools/mesen_dump_e000.lua
# Puis breakpoint @ $51BE ; le fichier work/mesen_e000.bin est réécrit à chaque arrêt.
```

Comparer au miroir statique : `python3 tools/prg_unpack_re.py dump-loader -o work/loader_e000.bin` — du **code 65C02** (pas seulement des `$00`) attendu en runtime @ `$E0E0`+.

## Commandes

```bash
# Rapport RE + dump miroir $E000
python3 tools/prg_unpack_re.py report
python3 tools/prg_unpack_re.py dump-loader -o work/loader_e000.bin

# Analyse décompresseur depuis dump Mesen
python3 tools/mesen_disasm_fe0c.py work/mesen_e000.bin
python3 tools/mesen_check_dump.py work/mesen_e000.bin

# Dump décompresseur $CDxx (script mesen_dump_decompress.lua)
python3 tools/mesen_check_decompress_dump.py
python3 tools/mesen_disasm_cd.py work/mesen_decomp_cpu.bin

# Tentative décompression (échoue tant que l'algo n'est pas branché)
python3 tools/hudson_pack.py decompress wa1 -o work/wa1_split
```

## Fichiers liés

- [`docs/OVERLAY_FORMAT.md`](OVERLAY_FORMAT.md) — format ivm2h / build
- [`docs/YS_DATA.md`](YS_DATA.md) — chargeur secteur `0x14E`
- [`tools/hudson_pack.py`](../tools/hudson_pack.py) — segments `PACK_SEGMENTS`
