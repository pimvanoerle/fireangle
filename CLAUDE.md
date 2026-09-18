# CLAUDE.md — fireangle

Context for Claude Code sessions in this repo.

## What this is

ESPHome-based bridge from the FireAngel WiSafe2 868 MHz fire alarm mesh into Home
Assistant at Huis. See `README.md` for the full picture.

Corresponds to **project 19** (`fireangelwisafe2_ha_bridge`) in the PARA brain at
`~/dev/claude/ipinch-brain/01_projects/19_fireangelwisafe2_ha_bridge/`. That brief
predates this repo and specs the Arduino + USB serial approach; this repo supersedes it
with ESP32 + ESPHome. Keep the brief's inventory table in sync with
`docs/device_inventory.md`.

## Things that are easy to get wrong

- **WiSafe2 is not WiFi.** It is a proprietary 868 MHz RF mesh. The bridge joins it with a
  harvested donor radio module, not over the network.
- **The radio is the SPI master, we are the slave.** And it frames every single byte in
  its own `_SS` cycle. This is the whole reason the ESP32 port is non-trivial.
- **Trigger `0x82` is heat, not fire.** The reference implementation conflates it with
  `0x81` (smoke). We do not — 7 smoke + 1 heat means the distinction is the point.
- **Missing-device reports are peer-sourced.** Offsets 1-3 of a `0xD2` frame are the
  *reporter*; the missing device is at offsets 6-8. And if the whole mesh dies, no report
  is generated at all — that is what the bridge heartbeat is for.
- **Entity state is deliberately sticky.** Alarms only transmit on events, so the last
  known state is the current state. Do not "fix" this by resetting to unknown.

## Working practice

- `tools/wisafe2.py` is the reference decoder; the C++ mirrors it. **Change both
  together.** Every new captured frame gets a test in `tests/test_wisafe2.py`.
- Run `python3 -m pytest tests/ -q` before committing.
- Never expose the emergency broadcast commands (protocol §3) as a user-facing control.
- Model IDs for FP1640W2-R and FP1740W2-R are **unknown** — capturing them is a Phase 1
  deliverable. Anything in the docs marked UNVERIFIED has not met real hardware.

## Reference material

Clone of the upstream project (captures, PCB, STL, original sketch):
`https://github.com/C19HOP/WiSafe2-to-HomeAssistant-Bridge`
