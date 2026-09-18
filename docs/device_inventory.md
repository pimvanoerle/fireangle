# Device Inventory

Fill in the hex device ID for each alarm during bring-up step 9: press the test button on one
alarm, watch the decoded `TEST` event, record the `device` field.

IDs are lower-case hex, no separators (e.g. `2d8d01`).

## Alarms — 7 smoke + 1 heat

| # | Room | Type | Model | Device ID | Model ID |
|---|------|------|-------|-----------|----------|
| 1 | _TBC_ | Smoke | FP1640W2-R | `______` | `____` |
| 2 | _TBC_ | Smoke | FP1640W2-R | `______` | `____` |
| 3 | _TBC_ | Smoke | FP1640W2-R | `______` | `____` |
| 4 | _TBC_ | Smoke | FP1640W2-R | `______` | `____` |
| 5 | _TBC_ | Smoke | FP1640W2-R | `______` | `____` |
| 6 | _TBC_ | Smoke | FP1640W2-R | `______` | `____` |
| 7 | _TBC_ | Smoke | FP1640W2-R | `______` | `____` |
| 8 | Kitchen | **Heat** | FP1740W2-R | `______` | `____` |

Huis is an upside-down house — living room, kitchen and dining are **upstairs**; bedrooms,
study and the main hallway are **downstairs**. Name rooms by what they are, not by floor.

## Bridge

| Field | Value |
|-------|-------|
| Donor device | CP-LED (red PCB, device-powered) |
| Donor model ID | _TBC_ |
| Bridge device ID | `a5b813` (default; change if it collides) |
| Impersonated model ID | `1103` (WST-630) — see protocol §5 |

## Not fitted

No CO alarm in this build. The original project brief listed one by the combi boiler plus an
optional bedroom unit; neither was ordered. The firmware still decodes CO frames (trigger
`0x41`) so adding one later needs no code change — just a row here.
