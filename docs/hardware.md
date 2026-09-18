# Hardware

## Bill of materials

| Item | Qty | Notes |
|------|-----|-------|
| Donor WiSafe2 radio module | 1 | Harvested from the buzzer — model TBC |
| ESP32 dev board | 1 | Must be classic ESP32 or ESP32-S3, **not** ESP8266 (no SPI slave) |
| Wire for antenna | 1 | 17.27 cm half-wave, or 8.64 cm quarter-wave |
| Enclosure | 1 | Reference STL exists; ours will differ (no Nano, no shifters) |

**No level shifters.** The reference design needs two 4-channel converters because the
ATmega328P runs at 5 V and the radio at 3.3 V. The ESP32 is natively 3.3 V, so the radio wires
straight to it. This is the first concrete win from the ESP32 choice.

## Donor module variants

Two PCB colours are documented:
- **red** — device-powered, no battery
- **black** — battery-powered; the battery can be removed and the module run from the ESP32's
  3.3 V rail instead, which avoids a battery that will eventually die inside our bridge

Identify which we have before wiring.

## Wiring (proposed)

The radio is the SPI **master**. Names below are from the ESP32's point of view.

| Radio pin | ESP32 (VSPI) | Direction | Notes |
|-----------|--------------|-----------|-------|
| `_SS`  | GPIO 5  | input  | Chip select, active low, toggles per byte |
| `SCK`  | GPIO 18 | input  | Clocked by the radio |
| `SDI`  | GPIO 23 | input  | Radio → ESP32 (radio's data out) |
| `SDO`  | GPIO 19 | output | ESP32 → radio |
| `IRQ`  | GPIO 21 | output | Request-to-send / ACK, driven by us |
| `VCC`  | 3V3     | —      | |
| `GND`  | GND     | —      | |
| `ANT`  | —       | —      | Bare wire, cut to length |

> Pin numbers are a starting point, not verified. Confirm against the chosen dev board before
> soldering — some boards strap GPIO 5 at boot.

## The ESP32 SPI-slave problem

**This is the main technical risk in the project. Read before ordering anything.**

The reference design used an ATmega328P for a specific reason: this protocol frames **every
individual byte** in its own `_SS` low/high cycle (see `docs/protocol.md` §1). On an AVR that
is trivial — you write the next byte into the `SPDR` register and the hardware shifts it out
whenever the master next clocks.

ESP-IDF's `spi_slave` driver is transaction-oriented. It expects you to queue a descriptor and
have DMA service a whole transfer. Queueing a fresh single-byte transaction between each `_SS`
cycle means the driver must turn around faster than the radio re-asserts `_SS`, and if it does
not, bytes are silently dropped. For a fire alarm bridge, silently dropping bytes is exactly the
failure mode we cannot accept.

Three routes, in preference order:

### A. Bit-banged SPI slave on a pinned core *(preferred)*

Handle `SCK` and `_SS` with GPIO interrupts, shift bits manually, and pin the task to core 1
with the WiFi stack on core 0. The ESP32 runs at 240 MHz against what is almost certainly a
slow radio clock, so there should be ample headroom — but **the SCK frequency is currently
unmeasured**, and that number decides whether this works.

**First hardware task: put a scope or logic analyser on `SCK` and measure it.** If SCK is under
~1 MHz this is comfortable. Above that it needs care.

### B. `spi_slave` with pre-queued transactions

Keep several single-byte transactions queued so one is always ready. Simpler, but leaves the
turnaround latency question to the driver, and failures will be intermittent — the worst kind.

### C. Hybrid — keep the Nano as an SPI front end

ATmega328P does the SPI slave exactly as the proven design does, ESP32 reads its UART and does
WiFi and the HA API. Falls back to known-good silicon for the hard part and still drops the USB
tether to the Pi. **This is the fallback if A and B both prove unreliable** — it costs a chip
and a little board space, nothing more.

Route A is what we build first, but the decision is not final until SCK is measured. Do not
design a PCB before then.

## Bring-up order

1. Identify the donor buzzer model; open it; photograph the PCB and the radio daughterboard.
2. Identify module variant (red/black) and locate `_SS` `SCK` `SDI` `SDO` `IRQ` `VCC` `GND`.
3. **Measure SCK frequency** with a logic analyser — this settles route A vs C.
4. Wire radio → ESP32 on a breadboard. Attach antenna.
5. Flash firmware in **raw hex passthrough mode** and confirm `init` returns `46 7E`.
6. Capture raw frames while pressing test on one alarm. Feed them through
   `tools/wisafe2.py` to confirm the decode matches reality.
7. **Record the FP1640W2-R and FP1740W2-R model IDs** — currently unknown (protocol §4).
8. Pair the bridge onto the mesh.
9. Walk the house pressing test on each alarm; record room → device ID in
   `docs/device_inventory.md`.
10. Switch firmware to decoded mode; entities appear in HA.

## Safety guardrail

The alarms are the life-safety system and are certified standalone. This bridge is an observer
that happens to also be a node. It must never be relied on, and a dead bridge must be visibly
dead — hence the heartbeat. See `README.md`.
