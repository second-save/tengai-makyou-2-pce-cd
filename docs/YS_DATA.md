# Format YS.DATA — Tengai Makyou II

Analyse du chargeur Hudson embarqué dans le programme (`TENGAI2.PRG`) et du
catalogue de overlays données laissé par la chaîne **HDWRITE / CDPOS / cdlen**.

## Résumé

`YS.DATA` n'est **pas** un conteneur fichier sur le disque. C'est le namespace
utilisé par le runtime Hudson pour adresser des blocs de données sectorisés
écrits par `HDWRITE` lors du build. Sur le CD final, les données sont des
blobs alignés sur 2048 octets ; le moteur les nomme virtuellement
`YS.DATA.01`, `YS.DATA.02`, etc.

## Chargeur (secteur `0x14E`)

Le secteur `0x14E` contient à la fois :

- le **menu mot de passe / démarrage** (chaînes « display the password »,
  « start game story », texte Shift-JIS) ;
- la **routine YS.DATA** avec le gabarit `YS.DATA.??\0` à l'offset `+0xBF`.

Comportement reverse-engineered (bank CPU ~`$E000`) :

| Adresse | Rôle |
|---------|------|
| `$E100` | Recherche par index : compare 12 octets à `$68D2` |
| `$E13C` | Chargement CD après correspondance |
| `$E09C` | Copie secteur courant `$2C79` → `$68C7` |
| `$68CE` | Nombre d'entrées catalogue (RAM, initialisé depuis `cdlen.bin`) |

### Pseudo-code

```c
// Gabarit ROM : "YS.DATA.??\0"
bool ys_find(int index) {
    char *name = catalog[index];  // construit depuis cdlen
    for (y = 11; y >= 0; y--)
        if (name[y] != template[y]) return false;
    return true;
}

void ys_load(int index) {
    uint16_t sector = catalog[index].sector;
    uint16_t count  = catalog[index].length_sectors;
    cd_read(sector, count, dest);
}
```

### Décompilation partielle

```
; Sector 0x14e mapped near $E000
; Template @ +0xbf: b'YS.DATA.??\x00\x00'

$E100  find_file   ; index in A, compare 12 bytes to $68D2
$E10D              ; pointer = $6800 + index, template = YS.DATA.??
$E13C  load_file   ; JSR $E04B after match
$E09C  set_sector  ; copy $2C79 -> $68C7

; Key RAM variables
; $68CE  file count
; $68D2  filename template (12 bytes)
; $68C7  current CD sector (u16 LE)
; $2C79  game sector pointer (u16 LE)
```

## Build Hudson (artefacts secteurs `0x6A00+`)

La chaîne de build TM II utilise :

| Outil | Rôle |
|-------|------|
| `HDWRITE` | Écrit un `.bin` sur le CD (`PROG TENGAI2.PRG` ou data) |
| `CDPOS` / `adpos_*` | Position logique sur le disque (`position / 0x800 = secteur`) |
| `cdlen.s` / `cdlen.bin` | Table `(secteur, taille)` injectée dans le programme |
| `fsize -b0x800` | Calcule la taille sectorisée pour `cdlen` |

Exemple retrouvé dans les makefiles :

```
hdwrite -U04000000,034b0000 \vir\mn_b01.bin PROG TENGAI2.PRG
```

## Catalogue `adpos_*` recouvré

50 overlays données identifiés (hors `main`/`game`/artefacts dev `b**`).
Les **tailles réelles** viennent de la mesure sur le disque (padding `0xFF`/`0x00` dans chaque slot
de `0x80` secteurs). Seuls **wa2**, **wa5** et **wa6** diffèrent du maximum (124/122 sect.).

Voir [`docs/CDLEN.md`](CDLEN.md) pour la recherche de `cdlen.bin` dans le binaire.

| Index | YS.DATA | adpos | Secteur | Taille | Slot max | Type |
|------:|---------|-------|--------:|-------:|:--------:|------|
| 1 | `YS.DATA.01` | `sdt` | `0x260` | 128 sect. | 128 | system_data |
| 2 | `YS.DATA.02` | `yav` | `0x2e0` | 128 sect. | 128 | system_data |
| 3 | `YS.DATA.03` | `wa1` | `0x860` | 128 sect. | 128 | world_map |
| 4 | `YS.DATA.04` | `wa2` | `0x8e0` | 124 sect. | ≠128 | world_map |
| 5 | `YS.DATA.05` | `wa5` | `0xa60` | 122 sect. | ≠128 | world_map |
| 6 | `YS.DATA.06` | `wa6` | `0xae0` | 122 sect. | ≠128 | world_map |
| 7 | `YS.DATA.07` | `wb1` | `0xc60` | 128 sect. | 128 | world_map |
| 8 | `YS.DATA.08` | `wb2` | `0xce0` | 128 sect. | 128 | world_map |
| 9 | `YS.DATA.09` | `wb5` | `0xe60` | 128 sect. | 128 | world_map |
| 10 | `YS.DATA.10` | `wb6` | `0xee0` | 128 sect. | 128 | world_map |
| 11 | `YS.DATA.11` | `wc1` | `0x1060` | 128 sect. | 128 | world_map |
| 12 | `YS.DATA.12` | `wc2` | `0x10e0` | 128 sect. | 128 | world_map |
| 13 | `YS.DATA.13` | `wc5` | `0x1260` | 128 sect. | 128 | world_map |
| 14 | `YS.DATA.14` | `wc6` | `0x12e0` | 128 sect. | 128 | world_map |
| 15 | `YS.DATA.15` | `wg1` | `0x2060` | 128 sect. | 128 | world_map |
| 16 | `YS.DATA.16` | `wg2` | `0x20e0` | 128 sect. | 128 | world_map |
| 17 | `YS.DATA.17` | `wg5` | `0x2260` | 128 sect. | 128 | world_map |
| 18 | `YS.DATA.18` | `wg6` | `0x22e0` | 128 sect. | 128 | world_map |
| 19 | `YS.DATA.19` | `wh1` | `0x2460` | 128 sect. | 128 | world_map |
| 20 | `YS.DATA.20` | `wh2` | `0x24e0` | 128 sect. | 128 | world_map |
| 21 | `YS.DATA.21` | `wh5` | `0x2660` | 128 sect. | 128 | world_map |
| 22 | `YS.DATA.22` | `wh6` | `0x26e0` | 128 sect. | 128 | world_map |
| 23 | `YS.DATA.23` | `xi1` | `0x2860` | 128 sect. | 128 | world_map |
| 24 | `YS.DATA.24` | `xi2` | `0x28e0` | 128 sect. | 128 | world_map |
| 25 | `YS.DATA.25` | `xi5` | `0x2a60` | 128 sect. | 128 | world_map |
| 26 | `YS.DATA.26` | `xi6` | `0x2ae0` | 128 sect. | 128 | world_map |
| 27 | `YS.DATA.27` | `xj1` | `0x2c60` | 128 sect. | 128 | world_map |
| 28 | `YS.DATA.28` | `xj2` | `0x2ce0` | 128 sect. | 128 | world_map |
| 29 | `YS.DATA.29` | `xj5` | `0x2e60` | 128 sect. | 128 | world_map |
| 30 | `YS.DATA.30` | `xj6` | `0x2ee0` | 128 sect. | 128 | world_map |
| 31 | `YS.DATA.31` | `xk1` | `0x3060` | 128 sect. | 128 | world_map |
| 32 | `YS.DATA.32` | `xk2` | `0x30e0` | 128 sect. | 128 | world_map |
| 33 | `YS.DATA.33` | `xk5` | `0x3260` | 128 sect. | 128 | world_map |
| 34 | `YS.DATA.34` | `xk6` | `0x32e0` | 128 sect. | 128 | world_map |
| 35 | `YS.DATA.35` | `yo1` | `0x4060` | 128 sect. | 128 | world_map |
| 36 | `YS.DATA.36` | `yo2` | `0x40e0` | 128 sect. | 128 | world_map |
| 37 | `YS.DATA.37` | `yo5` | `0x4260` | 128 sect. | 128 | world_map |
| 38 | `YS.DATA.38` | `yo6` | `0x42e0` | 128 sect. | 128 | world_map |
| 39 | `YS.DATA.39` | `yp1` | `0x4460` | 128 sect. | 128 | world_map |
| 40 | `YS.DATA.40` | `yp2` | `0x44e0` | 128 sect. | 128 | world_map |
| 41 | `YS.DATA.41` | `yp5` | `0x4660` | 128 sect. | 128 | world_map |
| 42 | `YS.DATA.42` | `yp6` | `0x46e0` | 128 sect. | 128 | world_map |
| 43 | `YS.DATA.43` | `yq1` | `0x4860` | 128 sect. | 128 | world_map |
| 44 | `YS.DATA.44` | `yq2` | `0x48e0` | 128 sect. | 128 | world_map |
| 45 | `YS.DATA.45` | `yq5` | `0x4a60` | 128 sect. | 128 | world_map |
| 46 | `YS.DATA.46` | `yq6` | `0x4ae0` | 128 sect. | 128 | world_map |
| 47 | `YS.DATA.47` | `pmnj` | `0x5060` | 128 sect. | 128 | event_pack |
| 48 | `YS.DATA.48` | `dmnj` | `0x50e0` | 128 sect. | 128 | event_pack |
| 49 | `YS.DATA.49` | `pkab` | `0x5260` | 128 sect. | 128 | event_pack |
| 50 | `YS.DATA.50` | `dkab` | `0x52e0` | 128 sect. | 128 | event_pack |

## Liens avec maps / script

- **`yav`** (`0x2E0`) — données système proches des maps événement (`0x2C9`, `0x3C9`…).
- **`wa*` / `wb*` / …** — blocs monde par région (suffixe `1/2/5/6` = variante de map).
- **`pmnj` / `dmnj` / `pkab` / `dkab`** — packs événementiels (probables tables + script binaire).
- Le **texte** reste dispersé dans ces blocs (préfixes `0x01`/`0x02`/`0x10`) ;
  `YS.DATA` fournit la structure d'accès, pas un parseur de script.

## Fichiers générés

```bash
python3 tools/ys_data.py              # catalogue + docs
python3 tools/ys_data.py list
python3 tools/ys_data.py extract yav -o work/yav.bin
```
