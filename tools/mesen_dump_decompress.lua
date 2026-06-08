-- Mesen2 — dump décompresseur Hudson au bon instant (CPU + MPR6 + Card RAM).
--
-- Usage :
--   1. Charger Tengai II (.cue) + syscard 3.0+
--   2. Script Window → Load → ce fichier
--   3. Poser UN breakpoint CPU (Execute) sur l'une de :
--        $FE1F  — juste avant JSR $FE2A (MPR6=banque 2, index segment actif)  ← recommandé
--        $CEC8  — 1er JSR de la chaîne $CDxx (handler segment 0)
--        $51BE  — 1er JSR $E0D8 du stub unpack (plus tôt, MPR6 parfois pas prêt)
--   4. Jouer jusqu'au chargement d'une zone (wa1, etc.)
--   5. À l'arrêt, les fichiers work/mesen_decomp_* sont réécrits automatiquement.
--
-- Valider ensuite :
--   python3 tools/mesen_check_decompress_dump.py

local WORK = os.getenv("HOME") .. "/Develop/tengai-makyou-2-pce-cd/work"

local OUT_CPU = WORK .. "/mesen_decomp_cpu.bin"       -- CPU $0000-$FFFF (64 KiB)
local OUT_C0 = WORK .. "/mesen_decomp_c000.bin"       -- CPU $C000-$DFFF (MPR6, 8 KiB)
local OUT_CARD = WORK .. "/mesen_decomp_cardram.bin"  -- Card RAM (32 KiB)
local OUT_META = WORK .. "/mesen_decomp_meta.txt"

local CPU_SIZE = 0x10000
local C0_START = 0xC000
local C0_SIZE = 0x2000
local CARD_SIZE = 0x8000 -- Super System Card ; Arcade Card = 192 KiB+ (voir ci-dessous)

local BP_HINTS = {
  { addr = 0xFE1F, note = "JSR $FE2A — dispatch segment (recommandé)" },
  { addr = 0xCEC8, note = "JSR $CEC8 — chaîne $CDxx segment 0" },
  { addr = 0xFE00, note = "prologue handler 0" },
  { addr = 0x51BE, note = "JSR $E0D8 stub $51BA (tôt)" },
}

local function readByte(addr, memType)
  local ok, val = pcall(function()
    return emu.read(addr, memType, false)
  end)
  if ok then
    return val
  end
  return nil
end

local function writeRange(path, startAddr, size, memType)
  local f, err = io.open(path, "wb")
  if not f then
    return false, err or "open failed"
  end
  for i = 0, size - 1 do
    local val = readByte(startAddr + i, memType)
    if val == nil then
      f:close()
      return false, string.format("read failed @ $%04X", startAddr + i)
    end
    f:write(string.char(val))
  end
  f:close()
  return true
end

local function nzCount(data, off, len)
  local n = 0
  for i = off, off + len - 1 do
    local b = string.byte(data, i)
    if b ~= 0x00 and b ~= 0xFF then
      n = n + 1
    end
  end
  return n
end

local function dumpCardRam(path)
  local memType = emu.memType.pceCardRam
  local ok, err = writeRange(path, 0, CARD_SIZE, memType)
  if ok then
    return CARD_SIZE, "pceCardRam"
  end
  -- Arcade Card (2048 KiB) — on ne dump que les 64 KiB bas (buffer pack souvent ici)
  memType = emu.memType.pceArcadeCardRam
  local arcadeSize = 0x10000
  ok, err = writeRange(path, 0, arcadeSize, memType)
  if ok then
    return arcadeSize, "pceArcadeCardRam"
  end
  return 0, err or "Card RAM indisponible"
end

local function cpuStateLines()
  local lines = {}
  local ok, st = pcall(function()
    return emu.getState()
  end)
  if not ok or st == nil then
    lines[#lines + 1] = "cpu state: (emu.getState indisponible)"
    return lines
  end
  if st.cpu ~= nil then
    local c = st.cpu
    lines[#lines + 1] = string.format(
      "PC=$%04X  A=$%02X  X=$%02X  Y=$%02X  SP=$%02X",
      c.pc or 0, c.a or 0, c.x or 0, c.y or 0, c.sp or 0
    )
  else
    lines[#lines + 1] = "cpu state: " .. tostring(st)
  end
  return lines
end

local function dumpAll()
  local mem = emu.memType.pceDebug
  if mem == nil then
    mem = emu.memType.cpuDebug
  end

  local ok, err = writeRange(OUT_CPU, 0, CPU_SIZE, mem)
  if not ok then
    emu.displayMessage("dump_decomp", "CPU: " .. (err or "?"))
    return
  end

  ok, err = writeRange(OUT_C0, C0_START, C0_SIZE, mem)
  if not ok then
    emu.displayMessage("dump_decomp", "C000: " .. (err or "?"))
    return
  end

  local cardSize, cardSrc = dumpCardRam(OUT_CARD)

  local cpuData = io.open(OUT_CPU, "rb"):read("*a")
  local c0Data = io.open(OUT_C0, "rb"):read("*a")

  local meta = io.open(OUT_META, "w")
  if meta then
    meta:write("Mesen2 decompress dump\n")
    for _, line in ipairs(cpuStateLines()) do
      meta:write(line .. "\n")
    end
    meta:write(string.format("cpu_nz=$C000 window: %d/%d\n", nzCount(c0Data, 1, #c0Data), #c0Data))
    meta:write(string.format("cpu_nz=$CD12 region: %d/256\n", nzCount(c0Data, 0x112 + 1, 256)))
    meta:write(string.format("cpu_nz=$FE0C entry: %d/32\n", nzCount(cpuData, 0xFE0C + 1, 32)))
    meta:write(string.format("card_ram: %s (%d bytes)\n", cardSrc, cardSize))
    meta:write("\nBreakpoints suggérés:\n")
    for _, bp in ipairs(BP_HINTS) do
      meta:write(string.format("  $%04X — %s\n", bp.addr, bp.note))
    end
    meta:close()
  end

  local msg = string.format(
    "CPU 64K + $C000 + Card(%s %dK)",
    cardSize > 0 and "OK" or "skip",
    cardSize / 1024
  )
  emu.displayMessage("dump_decomp", msg)
end

emu.addEventCallback(function()
  dumpAll()
end, emu.eventType.codeBreak)

emu.displayMessage(
  "dump_decomp",
  "Chargé — break @ $FE1F (ou $CEC8) → work/mesen_decomp_*.bin"
)
