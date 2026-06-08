# Tengai Makyou II (PCE-CD) — Reverse Engineering & Translation

Projet visant à localiser le texte japonais de **Far East of Eden: Tengai Makyou II: Manji Maru** (PC Engine CD, 1992), l'extraire en CSV et préparer une traduction anglaise.

## Contenu du dépôt

| Chemin | Description |
|--------|-------------|
| `Far East of Eden - Tengai Makyou II - Manji Maru (Japan)/` | Image disque (piste 2 = données, pistes 1/3+ = audio) |
| `tenmatools/` | Outils de la traduction fan de **Tengai Makyou III: Ziria** (LIPEMCO!/Supper) |
| `tools/` | Scripts Python pour TM II |
| `work/` | Fichiers générés (ISO extraite, etc.) |
| `script/` | CSV de texte extrait |

## Démarrage rapide

```bash
# 1. Extraire la piste données (2352 → 2048 octets/secteur)
python3 tools/extract_iso.py

# 2. Extraire le texte japonais en CSV
python3 tools/extract_text.py

# 3. Filtrer les faux positifs
python3 tools/filter_text.py

# 4. Cartographier les secteurs (maps, events, script)
python3 tools/map_sectors.py

# 5. Analyser le format YS.DATA (overlays Hudson / HDWRITE)
python3 tools/ys_data.py find-cdlen   # tailles réelles (cdlen équivalent)
python3 tools/ys_data.py
python3 tools/ys_data.py extract yav -o work/yav.bin

# 6. Parser overlays carte (segments tilemap / NPC / script)
python3 tools/overlay_parse.py info yav
python3 tools/overlay_parse.py parse-event 0x2C9 -o work/event_02c9
python3 tools/overlay_parse.py split wa1 -o work/wa1_split
```

Le CSV brut (`script/tm2_text.csv`, ~34 000 entrées) contient beaucoup de bruit.
Le CSV filtré (`script/tm2_text_filtered.csv`, ~1 400 entrées) est celui à utiliser pour la traduction.
Les entrées rejetées sont dans `script/tm2_text_rejected.csv` avec la raison du rejet.

Le CSV contient les colonnes :
`type`, `id`, `offset`, `sector`, `msg_type`, `original`, `translation`, `notes`.

## Ce que nous savons (RE initial)

### Structure du disque

- **Pas de système de fichiers ISO9660** classique : le moteur Hudson adresse le CD par numéros de secteurs codés en dur (comme Ziria).
- La piste 2 est en **MODE1/2352** ; les données utiles sont les 2048 octets/secteur (offset +16).
- Secteur `0x800` = 2048 octets (`0x800`), ~98 686 secteurs de données (~192 Mo).
- Artefacts de développement présents sur le disque (makefiles, `TENGAI2.PRG`, `MN_B01.BIN`, etc.) autour des secteurs `0x6Axx`.

### Encodage du texte

Le jeu appartient à la famille **Tenma/Hudson** et partage des concepts avec Ziria (tenmatools), mais le format est **plus ancien et différent** :

| Préfixe | Usage observé | Exemple |
|---------|---------------|---------|
| `0x01` + 4 octets | Nom de zone/entité | `野良犬` |
| `0x02` | Dialogue/menu court | `嵩木ﾊ oｰﾚk？` |
| `0x10` + 1 octet | Dialogue avec contrôles | `$0` = saut de ligne, `$n` = nom du personnage |
| SJIS + `0x00` | Chaînes menu/combat | `卍丸`, `戦闘防御`, `極楽` |

Contrôles `$` (TM II) ↔ opcodes `0xEF–0xFF` (Ziria, voir `tenmatools/tenma/table/`).

Exemple de dialogue décodé :
```
\x02r$0は$nうなっている!
→ ligne 1 + « は[nom]うなっている! »
```

### Ce qui ne s'applique **pas** tel quel

- **`tenma_scriptgen`** / **`tenma_mapscan`** : conçus pour Ziria (`tenma_02.iso`, secteurs maps `0x1137+`, en-têtes `0xC000–0xE000`). TM II n'utilise pas ce schéma.
- **`tenma_prep`** : offsets de modules spécifiques à Ziria.
- Le workflow CSV → `tenma_scriptbuild` → patch ISO reste une **cible** une fois le format TM II entièrement documenté.

### Outils tenmatools utiles plus tard

- `libpce/src/tenma/TenmaMsgDism.*` — désassembleur de messages (base pour un port TM II)
- `tenma/table/sjis_utf8_tenma_std.tbl` — table de caractères Ziria (référence)
- `discaster/` — reconstruction d'image CD
- `wla-dx/` — assembleur HuC6280 pour patches ASM

### Format YS.DATA (overlays Hudson)

Le jeu n'utilise pas de fichiers `YS.DATA.*` sur le disque — c'est un **namespace runtime**
pour des blocs sectorisés posés par `HDWRITE` au build. Le chargeur vit dans le secteur
`0x14E` (gabarit `YS.DATA.??`). Le catalogue `adpos_*` a été recouvré depuis les
artefacts de build (`0x6A00+`) :

```bash
python3 tools/ys_data.py list
python3 tools/ys_data.py extract wa1 -o work/wa1.bin
```

Voir [`docs/YS_DATA.md`](docs/YS_DATA.md), [`docs/CDLEN.md`](docs/CDLEN.md) et [`docs/OVERLAY_FORMAT.md`](docs/OVERLAY_FORMAT.md).

`cdlen.bin` n'est pas présent tel quel dans le ROM — les tailles réelles sont mesurées depuis le padding des slots (`find-cdlen`).

## Prochaines étapes

1. **Cartographier les secteurs** — identifier où sont stockés maps, script events, texte combat/menu (analyse du programme `TENGAI2` / tables de secteurs).
2. **Affiner l'extracteur** — réduire les faux positifs, parser les blocs maps comme Ziria le fait par région.
3. **Pointer tables** — repérer les tables de pointeurs vers le texte (critical pour la réinsertion).
4. **Port des outils C++** — adapter `TenmaMsgDism` pour TM II une fois le format validé.
5. **Traduction** — remplir la colonne `translation` du CSV, puis développer un `tm2_scriptbuild`.

## Références

- [tenmatools (GitHub)](https://github.com/suppertails66/tenmatools) — traduction Ziria
- [Redump](http://redump.org/) — vérification du dump (serial HCD1022)
- [TCRF](https://www.tcrf.net/Tengai_Makyou_II:_Manjimaru_(TurboGrafx-CD)) — contenu unused, character viewer

## Licence

Le jeu appartient à Hudson Soft / Konami / Red Company. Ce dépôt est un projet de recherche et de fan translation ; fournissez votre propre copie légale du jeu.
