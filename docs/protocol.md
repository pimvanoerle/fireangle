# WiSafe2 Radio Module Protocol

Reverse-engineered specification of the SPI link between a FireAngel WiSafe2 radio module
and its host alarm board, plus the frame formats carried over that link.

**Provenance:** derived from the logic-analyser captures and analysis in
[C19HOP/WiSafe2-to-HomeAssistant-Bridge](https://github.com/C19HOP/WiSafe2-to-HomeAssistant-Bridge)
(`WiSafeCommunicationAnalysis/`), cross-checked against that project's Arduino sketch.
Everything marked **UNVERIFIED** has not been confirmed against our own hardware yet.

---

## 1. Physical layer

The radio module is a self-contained 868 MHz transceiver on a small daughterboard. It speaks
SPI to the host alarm board.

### The radio is the SPI MASTER

This is the single most important fact about the design. The radio drives `SCK` and `_SS`;
the alarm board (and therefore our bridge) is the **slave**. An `IRQ` line runs the other way,
from alarm to radio, as a request-to-send.

| Radio pin | Name  | Direction (relative to bridge) | Notes |
|-----------|-------|-------------------------------|-------|
| `_SS`     | CS    | in                            | Active low, toggles **per byte** |
| `SCK`     | Clock | in                            | Driven by radio |
| `SDI`     | MOSI  | in                            | Radio → bridge |
| `SDO`     | MISO  | out                           | Bridge → radio |
| `IRQ`     | IRQ   | out                           | Bridge → radio, request-to-send |
| `ANT`     | —     | —                             | Bare wire antenna |
| `VCC`     | —     | —                             | 3.3 V |
| `GND`     | —     | —                             | |

### Antenna

A plain wire soldered to `ANT`, cut for 868 MHz:
- **half wave:** 17.27 cm
- **quarter wave:** 8.64 cm

### Byte framing — the awkward part

There is no multi-byte transaction. Every single byte is its own `_SS` low/high cycle, with an
`IRQ` handshake around it.

**Bridge → radio (we want to send):**
```
bridge raises IRQ
radio pulls _SS low, runs SCK for 8 bits, reads our SDO byte
radio releases _SS high
bridge drops IRQ
bridge raises IRQ again for the next byte
```

**Radio → bridge (radio has something for us):**
```
radio pulls _SS low, runs SCK for 8 bits, drives SDI
radio releases _SS high
bridge pulses IRQ as an ACK
radio pulls _SS low again for the next byte
```

Frames are terminated by `0x7E`. Read bytes until `0x7E` to reassemble a frame.

> **Design consequence.** Per-byte `_SS` framing is why the reference build used an ATmega328P
> with its dead-simple `SPDR` register — you stage one byte and the hardware shifts it out. The
> ESP32's `spi_slave` driver is transaction-oriented and expects the next transaction queued
> before the master clocks, which is a poor fit for this pattern. See `docs/hardware.md` for
> how we handle it.

---

## 2. Frame formats — radio → bridge (inbound events)

All frames terminate with `0x7E`. Multi-byte device and model IDs are big-endian, rendered as
lower-case hex without separators (`2d8d01`).

### `0x70` — Test event (11 bytes)

A device's test button was pressed, or a network-wide test was triggered.

| Offset | Len | Field | Values |
|--------|-----|-------|--------|
| 0 | 1 | Frame type | `0x70` |
| 1-3 | 3 | Device ID | |
| 4 | 1 | Trigger type | `0x81` fire/smoke · `0x82` **heat** · `0x41` CO · `0xFF` all |
| 5 | 1 | Result | `0x01` pass · `0x00` fail (low battery) |
| 6-7 | 2 | Model ID | see §4 |
| 8 | 1 | ? | part of model ID, or extra status |
| 9 | 1 | Sequence | counts `0x00`–`0x0F`, wraps |
| 10 | 1 | Terminator | `0x7E` |

Observed:
```
70 2D 8D 01 81 01 ED 08 07 03 7E   FP2620W2 smoke, pass
70 2D 8D 01 81 00 ED 08 07 0E 7E   FP2620W2 smoke, FAIL (low battery)
70 13 F4 3E 81 01 11 03 02 07 7E   WST-630
70 11 CE 01 41 01 78 03 03 0E 7E   W2-CO-10X, CO
70 60 1A 03 FF 01 C3 04 09 09 7E   W2-SVP-630, both
70 A7 6F 18 82 01 11 04 14 0E 7E   FP1720W2-R HEAT  <-- trigger 0x82
```

> **Heat vs smoke.** `0x82` is the heat-alarm trigger type. The reference sketch maps both
> `0x81` and `0x82` to the string `FIRE`; we decode `0x82` as `HEAT` so the kitchen heat alarm
> announces distinctly. Confirmed present in the capture set, **UNVERIFIED** on FP1740W2-R.

### `0x71` — Base / battery event (10 bytes)

Alarm attached to or removed from its mounting base, or a battery state change.

| Offset | Len | Field | Values |
|--------|-----|-------|--------|
| 0 | 1 | Frame type | `0x71` |
| 1-3 | 3 | Device ID | |
| 4-5 | 2 | Model ID | |
| 6 | 1 | Status bits | see below |
| 7 | 1 | ? | always `0x02`-ish, varies by model |
| 8 | 1 | Sequence | |
| 9 | 1 | Terminator | `0x7E` |

Status byte (offset 6):
- bit 0 (`0x01`) — always set
- bit 2 (`0x04`) — **on base** when set, off base when clear
- bits 1+6 (`0x42`) — **low battery** when set

Observed:
```
71 06 F9 3E 11 03 01 02 0F 7E   WST-630, off base
71 2D 8D 01 ED 08 47 07 0B 7E   on base + low battery
71 2D 8D 01 ED 08 43 07 0F 7E   off base + low battery
71 60 1A 03 C3 04 05 09 0D 7E   on base, battery OK
```

### `0x50` — Emergency event (9-11 bytes)

**The one that matters.** A device is in alarm.

| Offset | Len | Field | Values |
|--------|-----|-------|--------|
| 0 | 1 | Frame type | `0x50` |
| 1-3 | 3 | Device ID | |
| 4 | 1 | Trigger type | `0x81` fire/smoke · `0x82` heat · `0x41` CO · `0xFF` all |
| 5-6 | 2 | ? | |
| 7 | 1 | Sequence | |
| 8 | 1 | Terminator | `0x7E` |

Observed:
```
50 06 F9 3E 81 02 02 06 7E   WST-630 fire emergency
```

### `0x61` — Silence event

A device's hush/silence button was pressed, or silence was commanded.

| Offset | Len | Field |
|--------|-----|-------|
| 0 | 1 | Frame type `0x61` |
| 1-3 | 3 | Device ID |
| 4+ | | trailing bytes, terminator `0x7E` |

### `0xD2` — Missing device report (14 bytes)

Another node on the mesh reports that a device it expected has gone silent. The **missing**
device's ID is at offsets 6-8 (not 1-3 — offsets 1-3 identify the reporter).

```
D2 2A 38 41 00 EF 60 1A 03 00 00 09 40 7E
   ^--reporter--^       ^--missing--^
```

> **Known weakness, inherited from FireAngel.** Missing-device detection is peer-reported. If
> the whole mesh goes away, nobody is left to report it. This is why `docs/hardware.md`
> insists on an independent bridge heartbeat — absence of the mesh is not absence of events.

---

## 3. Frame formats — bridge → radio (outbound commands)

We join the mesh as a node with our own device ID and a borrowed model ID, then transmit as
that node.

Replies from the radio are 2 bytes: `41 7E` = OK/ack, `46 7E` = retry/accepted-for-send.

### Radio init

Sent once at startup, before anything else. Two variants were observed; the reference uses the
first and notes it does not know which is correct.

```
D3 19 50 00 7E      init(1)  <- used
D3 14 8E 7E         init(2)
```
Expected reply: `46 7E`. If it does not arrive, the radio is not ready — reset and retry.

### Test broadcast (two-part)

```
Tx: 70 <dev0> <dev1> <dev2> <trigger> 01 <model0> <model1> 7E
Rx: 41 7E
Tx: 91 <dev0> <dev1> <dev2> <model0> <model1> <trigger> 05 <flags0> <flags1> 7E
```
`trigger` is `0x41` CO, `0x81` smoke, `0xFF` all.

### Emergency broadcast

```
Tx: 50 <dev0> <dev1> <dev2> <trigger> 00 7E
Rx: 46 7E
```
`trigger` `0x41` CO, `0x81` fire.

> **Do not expose these.** Broadcasting a real emergency onto a life-safety mesh from a
> home-brew bridge is a test-bench-only capability. See the guardrail in `README.md`.

### Silence broadcast

```
Tx: 61 <dev0> <dev1> <dev2> <trigger> 01 7E
Rx: 46 7E
```
`trigger` `0x40` as-CO, `0x80` as-smoke.

### Pairing

Check pairing state:
```
Tx: D3 03 7E
Rx: D4 .. <state> ....... 7E      (14 bytes; state at offset 2, non-zero = paired)
```

Enter pairing mode (only valid when currently unpaired):
```
Tx: D3 03 7E          -> confirm unpaired
Tx: D3 12 01 7E       -> expect 46 7E
Tx: (nothing)         -> expect 41 7E
Tx: 91 <dev0> <dev1> <dev2> <model0> <model1> FF 05 01 01 7E
    ... ~20 s window during which the network is joined ...
Tx: D3 03 7E          -> re-check, expect state non-zero
```

---

## 4. Model IDs

| Model ID | Device | Type |
|----------|--------|------|
| `ed08` | FP2620W2 | Smoke, battery, Pro Connected |
| `1103` | WST-630 | Smoke |
| `1104` | FP1720W2-R | **Heat**, battery |
| `7803` | W2-CO-10X | CO |
| `c304` | W2-SVP-630 | Strobe & vibrating pad |
| `????` | **FP1640W2-R** | **Smoke, mains — ours, UNKNOWN** |
| `????` | **FP1740W2-R** | **Heat, mains — ours, UNKNOWN** |

Capturing the two unknown model IDs is a Phase 1 deliverable: press test on one alarm of each
type and read the `model` field off the decoded frame.

---

## 5. Our bridge's identity

The bridge must present a device ID and a model ID to the mesh.

- **Device ID:** any value unique on the network. Reference sketch default `A5 B8 13`.
- **Model ID:** we must impersonate a known model — the mesh presumably rejects unknown ones.
  `1103` (WST-630) is the reference default and is the safest choice: it is a smoke alarm, so
  the mesh treats us as an ordinary smoke node.

> Impersonating `c304` (strobe) may cause other nodes to expect strobe-specific behaviour.
> Stick with `1103` unless there is a reason not to. **UNVERIFIED** either way.
