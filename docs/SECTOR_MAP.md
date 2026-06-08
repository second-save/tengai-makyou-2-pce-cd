# Tengai Makyou II — Carte des secteurs (RE)

Analyse automatique de la piste 2 (banque primaire + miroir).

## Architecture du disque

- **Secteurs totaux** : 98,686 (192 Mo)
- **Miroir** : secteur `S` dupliqué à `S + 0x10000` pour la majeure partie du contenu
- **Pas de filesystem** : adressage direct par numéro de secteur (Hudson CD)

## Zones système et programme

| Secteurs | Rôle |
|----------|------|
| `0xE6` | Avertissement copyright Hudson |
| `0xE7` | IPL / en-tête CD (`TENGAI_MAKYO_2`) |
| `0xE8–0x16F` | Code programme (`TENGAI2.??`) |
| `0x14E` | Routine de chargement `YS.DATA.??` |
| `0x171` | Textes combat/UI (skills, personnages) |
| `0x196–0x198` | Table régions (尾張, 伊勢, 越後…) + menus |
| `0x5024–0x5027` | Crédits staff |
| `0x6A00–0x6DFF` | Artefacts de build (makefiles, sources) |

## Format texte repéré

| Préfixe | Usage |
|---------|-------|
| `0x01` + 4 octets | Label entité/zone (ex. `野良犬`) |
| `0x02` | Dialogue / menu court |
| `0x10` + arg | Dialogue avec `$0` (saut de ligne), `$n` (nom) |

## Secteurs événements / maps (`0x01` labels)

40 secteurs identifiés :

| Secteur | Entités | Textes CSV |
|---------|---------|------------|
| `0x02C9` | 野良犬 | 狂犬 | 6 |
| `0x03C9` | 野良犬 | 狂犬 | 0 |
| `0x03CF` | 骨ゼミ | 野良犬 | 狂犬 | 11 |
| `0x05CF` | 野良犬 | 5 |
| `0x0949` | 野良犬 | 狂犬 | 0 |
| `0x09CE` | 赤玉 | 化け根 | 鬼の華 | 骨ゼミ | 10 |
| `0x0A49` | 骨ゼミ | 0 |
| `0x0D51` | 双頭 | 化け根 | 1 |
| `0x0E4C` | 赤い爪跡 | 2 |
| `0x1150` | 双頭 | 9 |
| `0x14D1` | かけつぼ | 9 |
| `0x1C50` | かけつぼ | 2 |
| `0x2049` | 野良犬 | 狂犬 | 0 |
| `0x20D3` | かけつぼ | 5 |
| `0x2451` | かけつぼ | 2 |
| `0x27D1` | カチ割り | 絶対零度 | キツネ火 | 冷血天使 | つらら兵 | 氷の槍 | 冬の鬼 | 14 |
| `0x2A49` | 明けガラス | 青獣 | 呪い火 | 6 |
| `0x39CC` | 赤い白昼夢 | 背徳の穴 | 手長 | 母なる病巣 | 8 |
| `0x62C9` | 野良犬 | 狂犬 | 0 |
| `0x6349` | 野良犬 | 狂犬 | 0 |
| `0x102C9` | 野良犬 | 狂犬 | 0 |
| `0x103C9` | 野良犬 | 狂犬 | 0 |
| `0x103CF` | 骨ゼミ | 野良犬 | 狂犬 | 0 |
| `0x105CF` | 野良犬 | 0 |
| `0x10949` | 野良犬 | 狂犬 | 0 |
| `0x109CE` | 赤玉 | 化け根 | 鬼の華 | 骨ゼミ | 0 |
| `0x10A49` | 骨ゼミ | 0 |
| `0x10D51` | 双頭 | 化け根 | 0 |
| `0x10E4C` | 赤い爪跡 | 0 |
| `0x11150` | 双頭 | 0 |
| `0x114D1` | かけつぼ | 0 |
| `0x11C50` | かけつぼ | 0 |
| `0x12049` | 野良犬 | 狂犬 | 0 |
| `0x120D3` | かけつぼ | 0 |
| `0x12451` | かけつぼ | 0 |
| `0x127D1` | カチ割り | 絶対零度 | キツネ火 | 冷血天使 | つらら兵 | 氷の槍 | 冬の鬼 | 0 |
| `0x12A49` | 明けガラス | 青獣 | 呪い火 | 0 |
| `0x139CC` | 赤い白昼夢 | 背徳の穴 | 手長 | 母なる病巣 | 0 |
| `0x162C9` | 野良犬 | 狂犬 | 0 |
| `0x16349` | 野良犬 | 狂犬 | 0 |

## Blocs texte denses (hors maps)

| Secteur | Catégorie | Notes |
|---------|-----------|-------|
| `0x2356` | text_block | 17 strings; e.g. _E9徃r / 母子心中 |
| `0x0F56` | text_block | 14 strings; e.g. ･ 傲 / ﾎ7繊ﾏﾜ |
| `0x1352` | text_block | 12 strings; e.g. 8T剋 / あぶらぼう |
| `0x18D5` | text_block | 11 strings; e.g. Sヌルヌルの舌 / !$0は、$n長い舌を突き刺した! |
| `0x19D7` | text_block | 11 strings; e.g. R$0の体当り攻撃! / 肉の夢 |
| `0x1F51` | text_block | 11 strings; e.g. 2湘<玻術5 / な |
| `0x56EF` | text_block | 11 strings; e.g. 漾 / 澑 |
| `0x1A55` | text_block | 10 strings; e.g. hｼ絢 / 人面狩り |
| `0x1950` | text_block | 9 strings; e.g. r钁ygp ﾐ` / 赤尻 |
| `0x1B54` | text_block | 9 strings; e.g. 一角星 / Q$0は、$n角を振り上げ突っ込ん |
| `0x54ED` | text_block | 9 strings; e.g. 歩P / ｵ煢H |
| `0x2954` | text_block | 8 strings; e.g. !}紛 / は虫犬 |
| `0x3152` | text_block | 7 strings; e.g. 2ﾒ2"鋳 / 生グサ吐息 |
| `0x3954` | text_block | 6 strings; e.g. d泣く子いねか / 
$0の決死の一撃! |
| `0x3D56` | text_block | 6 strings; e.g. 魔海母子 / 3$0は$n黄泉の子守歌を歌った |
| `0x46CC` | text_block | 6 strings; e.g. 地底警察 / 広$0は$nイナズマを呼んだ! |
| `0x54EC` | text_block | 6 strings; e.g. 溝 / 兮 |
| `0x0B4D` | text_block | 5 strings; e.g. 小鬼 / 双頭 |
| `0x124E` | text_block | 5 strings; e.g. I'o唇 / 栫ﾄﾟ |
| `0x174F` | text_block | 5 strings; e.g. P｡倨0ｹ埴 / 恍惚の瞳 |
| `0x1750` | text_block | 5 strings; e.g. モイ / 儉 |
| `0x23CC` | text_block | 5 strings; e.g. トビモノ / _E9徃r |
| `0x0C4D` | text_sparse | 4 strings |
| `0x2D54` | text_sparse | 4 strings |
| `0x40CD` | text_sparse | 4 strings |
| `0x4557` | text_sparse | 4 strings |
| `0x49D0` | text_sparse | 4 strings |
| `0xF22A` | text_sparse | 4 strings |
| `0x0187` | text_sparse | 3 strings |
| `0x019A` | text_sparse | 3 strings |
| `0x0BCA` | text_sparse | 3 strings |
| `0x17CA` | text_sparse | 3 strings |
| `0x1BD4` | text_sparse | 3 strings |
| `0x214F` | text_sparse | 3 strings |
| `0x29CD` | text_sparse | 3 strings |
| `0x33CE` | text_sparse | 3 strings |
| `0x36D3` | text_sparse | 3 strings |
| `0x384D` | text_sparse | 3 strings |
| `0x3DCC` | text_sparse | 3 strings |
| `0x4151` | text_sparse | 3 strings |

## Références programme → secteurs

Le code à `0xE8` contient des constantes 16-bit pointant vers :
- `0x14E` — loader YS.DATA
- `0x171` — module combat
- `0x196` — table monde
- `0x2C9` — map/événement (野良犬)
- `0x5025` — crédits

## Fichiers générés

- `script/sector_map.csv` — liste détaillée
- `docs/SECTOR_MAP.md` — ce document
