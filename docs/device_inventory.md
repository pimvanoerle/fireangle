# Device Inventory

Fill in the hex device ID for each alarm during bring-up step 9: press the test button on one
alarm, watch the decoded `TEST` event, record the `device` field.

IDs are lower-case hex, no separators (e.g. `2d8d01`).

## During installation — read this first

The mesh device IDs below get captured **later**, once the bridge is live (bring-up step 9:
press test on one alarm at a time and read the decoded `device` field). Nothing about the
install needs to wait for that.

But one thing is worth doing now, because the chance does not come back:

> **Photograph each alarm's rear label, with its room, before it goes on the ceiling.**

Once mounted, that label faces the ceiling and is unreadable without taking the unit down
again. If the printed serial turns out to correlate with the 3-byte mesh device ID, the
room→ID map falls out for free. If it does not correlate, we have lost nothing but a few
seconds per alarm. Drop the photos in `hardware/` as `alarm-<room>.jpg`.

Also worth recording as you go: the install date per unit. These have a 10-year life and
the replace-by date is otherwise buried on a hidden label.

## Alarms — 7 smoke + 1 heat

Huis is an upside-down house — living room, kitchen and dining are **upstairs**; bedrooms,
study and the main hallway are **downstairs**. Name rooms by what they are, not by floor.

## Bridge

| Field | Value |
|-------|-------|
| Donor device | FireAngel CP-LED = `W2-SVP-630L` (red PCB, Si4431 + PIC16LF1936) |
| Donor model ID | `c304` (expected — confirm from capture) |
| Bridge device ID | `a5b813` (default; change if it collides) |
| Impersonated model ID | `1103` (WST-630) — see protocol §5 |

## Not fitted

No CO alarm in this build. The original project brief listed one by the combi boiler plus an
optional bedroom unit; neither was ordered. The firmware still decodes CO frames (trigger
`0x41`) so adding one later needs no code change — just a row here.
