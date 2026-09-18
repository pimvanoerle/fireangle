# Hardware

## Bill of materials

| Item | Qty | Notes |
|------|-----|-------|
| Donor WiSafe2 radio module | 1 | Red PCB from a FireAngel CP-LED (`W2-SVP-630L`) — Si4431 + PIC16LF1936, device-powered |
| ESP32 dev board | 1 | Must be classic ESP32 or ESP32-S3, **not** ESP8266 (no SPI slave) |
| Wire for antenna | 1 | 17.27 cm half-wave, or 8.64 cm quarter-wave |
| Enclosure | 1 | Reference STL exists; ours will differ (no Nano, no shifters) |

**No level shifters.** The reference design needs two 4-channel converters because the
ATmega328P runs at 5 V and the radio at 3.3 V. The ESP32 is natively 3.3 V, so the radio wires
straight to it. This is the first concrete win from the ESP32 choice.

## Our donor: FireAngel CP-LED = W2-SVP-630L

Opened 2026-09-18. The rear label reads **FireAngel CP-LED Wi-Safe 2**, and the support
line gives the real part code: **W2-SVP-630L**.

That is the *same device family the reference project used as its donor* — C19HOP
recommends W2-SVP-630 strobe units as the cheap, plentiful source of modules, and tested
against exactly this model. We are on the proven path, not blazing a trail.

| Property | Value |
|----------|-------|
| Product | FireAngel CP-LED (strobe & vibrating pad control unit) |
| Part code | `W2-SVP-630L` |
| Host supply | 12 V DC, 0.2 A |
| Mesh model ID | almost certainly **`c304`** (reference captures for W2-SVP-630) |
| Standard | BS 5446-3:2015 |
| Batch | 20 21 5 |

The label's "Single Flash: Vibrating Pad is not connected" and the CO/Fire/Silence
indicators confirm it: this is the deaf-alert strobe controller, and it registers on the
mesh as trigger type `0xFF` (both fire and CO).

**The 12 V is the host's, not the module's.** The radio daughterboard is 3.3 V and was
device-powered off the host's regulated rail. Feed it 3.3 V from the ESP32 — never 12 V.
The "replace back up battery after 5 years" on the label refers to the host's backup cell
(the blue battery in the case), not the module, which confirms the red-PCB/no-battery read.

## What is on the radio module

Two chips, both clearly marked:

| Ref | Part | Role |
|-----|------|------|
| `U1` | **Si4431** (`BPS1R5`, date 2003) | Silicon Labs EZRadioPRO sub-GHz transceiver — the actual 868 MHz radio |
| `U2` | **PIC16LF1936** (`-I/SS`, date 2008W6S) | Microchip 8-bit MCU, 28-pin SSOP, 3.3 V "LF" variant |

So the module is *not* a bare transceiver — it is a PIC running FireAngel's WiSafe2 stack,
with the Si4431 as its radio. The PIC owns the encryption and mesh membership, which is
precisely why the donor approach works and why sniffing the air with a generic 868 MHz
receiver does not.

The PIC is SPI **master** toward the host board. That is the interface we impersonate.

### Do not confuse the ICSP pads with the host SPI

The module has a group of pads silkscreened `MCLR` `VDD` `GND` `DAT` `CLK`. That is the
**Microchip ICSP programming header** for the PIC (`DAT`=PGD, `CLK`=PGC) — it is not the
bus we want, and the `CLK` there is not our `SCK`.

**The host interface is the `SV1` edge header** along the bottom of the module, with `SV2`
as a smaller group to its left. `SV1` is where `_SS` `SCK` `SDI` `SDO` `IRQ` live.

Also on the board: `XTAL` (crystal for the Si4431), `RF_TUNE`, an `SW1` tact switch, a
status LED (`LED1`/`R29`), and `QSW_EX2`. The antenna is the white wire already attached —
**measure its length before removing it**; it tells us whether FireAngel tuned for half
wave (17.27 cm) or quarter wave (8.64 cm).

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

This protocol frames **every individual byte** in its own `_SS` low/high cycle (see
`docs/protocol.md` §1). On an AVR that is trivial — write the next byte into `SPDR` and the
hardware shifts it out. ESP-IDF's `spi_slave` driver is transaction-oriented and expects the
next descriptor queued before the master clocks, which is a poor fit.

### Revised risk: lower than first assessed

Identifying the module changed this picture. Two pieces of evidence:

**1. The master is a PIC16LF1936, not something fast.** Its MSSP in master mode clocks at
Fosc/4, Fosc/16, Fosc/64 or via TMR2. The PIC's ceiling is 32 MHz, and a battery-conscious
safety device will not be running flat out. The plausible range is:

| PIC Fosc | Fosc/4 | Fosc/16 | Fosc/64 |
|----------|--------|---------|---------|
| 32 MHz | 8 MHz | 2 MHz | 500 kHz |
| 8 MHz | 2 MHz | 500 kHz | 125 kHz |
| 4 MHz | 1 MHz | 250 kHz | 62.5 kHz |

Most of that space is comfortably bit-bangable on a 240 MHz ESP32.

**2. The reference implementation keeps up on a 16 MHz AVR — in Arduino abstractions.**
It polls `digitalRead(SS)` in a loop with `delayMicroseconds(5)` granularity, and Arduino's
`digitalRead` costs several microseconds by itself. For that to track the byte framing, the
inter-byte cadence must be tens of microseconds at minimum. An ESP32 has roughly 15× the
instruction throughput.

So route A below is now the expected outcome rather than a gamble. **Measure anyway** — the
per-bit clock inside a byte could still be fast even if the byte cadence is relaxed, and
that is the number that decides the shifting strategy.

### A. Bit-banged SPI slave on a pinned core *(expected)*

GPIO interrupts on `SCK` and `_SS`, shift bits manually, task pinned to core 1 with WiFi on
core 0. Comfortable if `SCK` is under ~1 MHz; needs care above that.

### B. `spi_slave` with pre-queued transactions

Keep several single-byte transactions queued. Simpler, but leaves turnaround latency to the
driver and failures will be intermittent — the worst kind.

### C. Hybrid — keep an ATmega328P as the SPI front end

The proven silicon does the hard part, ESP32 does WiFi and the HA API. Costs a chip and some
board space. **This is the fallback, and it is a perfectly good outcome** — it still drops
the USB tether to the Pi, which was most of the reason for moving off the reference design.

---

## Measuring SCK

**A multimeter cannot do this, including one with a Hz / frequency-counter mode.** Two
reasons:

1. **The signal is bursty, not periodic.** SPI `SCK` here is eight pulses, then idle until
   the next byte. A frequency counter assumes a continuous repeating waveform; against
   bursts it reads zero, or an average that means nothing. The number we want is the period
   *within* a burst.
2. **We need relationships, not a number.** The whole point is seeing how `_SS`, `SCK`,
   `SDI`, `SDO` and `IRQ` line up in time — which edge of `_SS` frames which byte, where the
   `IRQ` handshake falls. That is five signals at once, and no meter shows you that.

### What to get

A **cheap 8-channel USB logic analyser** — the Cypress FX2LP (CY7C68013A) clones, about
£8–12 on eBay/AliExpress, sold as "24MHz 8CH Logic Analyzer". Pair it with
**[PulseView/sigrok](https://sigrok.org/wiki/PulseView)**, which is free and open source,
and is exactly what C19HOP used to produce the captures this whole project is built on.

Sizing: you want roughly 10× oversampling of the clock. At 24 MSa/s that covers `SCK` up to
~2.4 MHz, which spans the plausible range above.

Two practical notes:

- **Do not sample all 8 channels at 24 MHz.** The FX2LP clones drop samples at full rate
  over USB 2.0. We need 5 channels, so drop to 6 and it streams reliably.
- **A scope is worse here**, unless it is a 4+ channel one with protocol decode. This is a
  timing-relationship problem, which is what a logic analyser is for.

If you would rather not buy anything: a spare ESP32 can be pressed into service as a crude
frequency counter via the pulse counter peripheral. It will get you an order of magnitude,
but not the framing, so you would still be guessing at the hard part. The £10 is worth it.

### Procedure

1. **Leave the module soldered in place** and power the CP-LED normally from 12 V. Probing
   it in situ, driven by its real host, is ground truth — far better than guessing after
   desoldering.
2. Clip the analyser's **GND** to the host board ground first, always.
3. Hook probes to the `SV1` header. **We do not yet know which pin is which — that is fine.**
   With 8 channels you can capture the whole header at once and identify pins from
   behaviour, no datasheet needed:
   - **`SCK`** — the only line with tight bursts of exactly 8 pulses
   - **`_SS`** — goes low around each burst and high between them
   - **`SDI` / `SDO`** — change state only while `SCK` is running; tell them apart by which
     one moves during a radio→host message versus a host→radio one
   - **`IRQ`** — pulses outside the `SCK` bursts, in the handshake pattern in protocol §1
   - **`VCC` / `GND`** — sit flat; identify with a meter first so you do not probe them
4. **Trigger some traffic**: press the test button on any paired alarm in the house. The
   mesh will light up and the module will pass frames to its host.
5. Capture, then in PulseView measure the period between two adjacent `SCK` rising edges
   inside one burst. **That number is the answer.** Also note the gap between bytes.
6. Save the capture into `hardware/` and add any newly observed frames as test cases in
   `tests/test_wisafe2.py`.

Bonus: this same capture will show the module's own frames, which gives us the `W2-SVP-630L`
model ID from real hardware rather than inference.

## Bring-up order

1. ~~Identify the donor device; open it.~~ **Done** — CP-LED, red PCB.
2. ~~Identify module variant (red/black).~~ **Done — red, device-powered.** Still to do:
   locate and label `_SS` `SCK` `SDI` `SDO` `IRQ` `VCC` `GND` `ANT` on the module.
3. **Measure SCK frequency** with a logic analyser, in situ — see "Measuring SCK".
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
