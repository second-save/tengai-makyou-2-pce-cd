-- Mesen2 — dump runtime Hudson @ $E000-$E1FF on debugger break.
-- Usage: load Tengai II CD, set execution breakpoint @ $51BE (JSR $E0D8),
--        run Script Window → load this file. Each break writes work/mesen_e000.bin

local OUT = os.getenv("HOME") .. "/Develop/tengai-makyou-2-pce-cd/work/mesen_e000.bin"
local START = 0xE000
local SIZE = 0x200

local function dump()
  local f, err = io.open(OUT, "wb")
  if not f then
    emu.displayMessage("dump_e000", err or "open failed")
    return
  end
  for i = 0, SIZE - 1 do
    f:write(string.char(emu.read(START + i, emu.memType.pceDebug)))
  end
  f:close()
  emu.displayMessage("dump_e000", string.format("Wrote $%04X +%03X → %s", START, SIZE, OUT))
end

emu.addEventCallback(function()
  dump()
end, emu.eventType.codeBreak)

emu.displayMessage("dump_e000", "Loaded — breaks will dump $E000-$E1FF")
