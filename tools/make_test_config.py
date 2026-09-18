#!/usr/bin/env python3
"""Generate an ESPHome config with alarms populated, for compile testing.

The shipped `wisafe2-bridge.yaml` has its `alarms:` block commented out, because the real
device IDs are not known until bring-up. That means a plain compile of it never exercises
the component's codegen path. This splices in two sample alarms -- one smoke, one heat --
so CI actually builds the entity-generating code.
"""

import argparse
import pathlib
import sys

SAMPLE_ALARMS = '''  alarms:
    - name: "CI Smoke"
      device: "2d8d01"
      kind: smoke
    - name: "CI Heat"
      device: "a76f18"
      kind: heat

'''

START = "  alarms:"
END = "# --- Bridge health"


def splice(source: str, alarms: str = SAMPLE_ALARMS) -> str:
    """Replace the commented-out alarms block with a populated one."""
    try:
        start = source.index(START)
        end = source.index(END)
    except ValueError as err:
        raise SystemExit(
            f"could not find the alarms block: expected {START!r} followed by {END!r}"
        ) from err
    if end < start:
        raise SystemExit(f"{END!r} appears before {START!r}; config layout changed")
    return source[:start] + alarms + source[end:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=pathlib.Path)
    parser.add_argument("dest", type=pathlib.Path)
    args = parser.parse_args()

    args.dest.write_text(splice(args.source.read_text()))
    print(f"wrote {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
