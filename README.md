# fireangle

A Home Assistant bridge for the **FireAngel WiSafe2** fire alarm mesh, built as an
ESPHome component.

Seven FireAngel Pro Connected smoke alarms (FP1640W2-R) and one heat alarm (FP1740W2-R)
protect the house. They are certified, mains-powered and interlinked over their own
868 MHz mesh — they need nothing from this project to do their job. This bridge joins that
mesh as one extra node and reports what it hears into Home Assistant.

## Safety guardrail

**The alarms are the life-safety system. This bridge is an observer.**

- The alarms are BS 5839-6 compliant and operate entirely standalone.
- Nothing here is load-bearing for safety. A dead bridge must never be a silent failure —
  hence the connectivity heartbeat and the offline alert.
- Emergency *broadcast* commands exist in the protocol and are documented, but are
  deliberately not exposed as buttons. Making every alarm in the house scream belongs on
  a bench, not on a dashboard.

## Why not the existing project?

[C19HOP/WiSafe2-to-HomeAssistant-Bridge](https://github.com/C19HOP/WiSafe2-to-HomeAssistant-Bridge)
did the hard work: reverse-engineering the radio protocol with a logic analyser. This
project owes it everything, and the protocol spec here is derived from those captures.

It differs in three ways:

1. **ESP32 + ESPHome instead of Arduino Nano + USB serial.** The bridge talks to HA over
   WiFi via the native API, so it can sit wherever the RF is best rather than being
   tethered by USB to the Pi. Being natively 3.3 V it also drops the two level shifters.
2. **Entities instead of templates.** Eight alarms needs ~24 hand-written template sensors
   in the serial approach. Here each alarm is four lines of YAML and the component
   generates its entities.
3. **Heat alarms decode as heat.** The reference maps trigger type `0x82` to `FIRE`
   alongside smoke's `0x81`. They are different events and the kitchen heat alarm should
   announce differently from a smoke alarm on the landing.

It also targets the **mains** FP1640W2-R / FP1740W2-R, which nobody has tested against
this protocol — the reference's captures are all battery models.

## Status

**Pre-hardware.** The protocol is specified and the decoder is written and tested against
the reference project's real logic-analyser captures. The SPI slave shifter is not yet
implemented — that waits on measuring the radio's clock. See `docs/hardware.md`.

| Piece | State |
|-------|-------|
| Protocol spec | Documented from captures |
| Frame decoder (Python) | Written, 23 tests passing |
| Frame decoder (C++) | Written, mirrors the Python |
| ESPHome component + codegen | Written, compiles clean for esp32/esp-idf |
| SPI slave shifter | **Not implemented** — blocked on measuring SCK |
| Pairing handshake | Not implemented |
| Hardware | Not built |

## Layout

```
docs/protocol.md          WiSafe2 SPI and frame-format specification
docs/hardware.md          BOM, wiring, the ESP32 SPI-slave problem, bring-up order
docs/device_inventory.md  Room → device ID map (to fill during bring-up)
tools/wisafe2.py          Reference frame decoder
tests/                    Decoder tests against real captures
firmware/esphome/         ESPHome component and device config
ha/packages/              Home Assistant automations, notifications, TTS
```

## Development

```bash
python3 -m pytest tests/ -q
```

The Python decoder in `tools/wisafe2.py` is the reference implementation — the C++ in
`firmware/esphome/components/wisafe2/wisafe2.cpp` mirrors it. Change both together, and
add the frame to `tests/test_wisafe2.py` when a new capture turns up.

## Licence

MIT. Protocol analysis derived from C19HOP's work, with thanks.
