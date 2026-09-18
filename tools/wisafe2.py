"""Decoder for WiSafe2 radio frames.

Reference implementation of the frame formats in docs/protocol.md. The ESPHome component
mirrors this logic in C++; this module exists so the decode can be tested against the
captured frames without any hardware attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

TERMINATOR = 0x7E

# Trigger types. 0x82 is the heat-alarm variant -- the reference sketch folds it into FIRE,
# which loses the smoke/heat distinction we need for per-room announcements.
TRIGGER_SMOKE = 0x81
TRIGGER_HEAT = 0x82
TRIGGER_CO = 0x41
TRIGGER_ALL = 0xFF

TRIGGERS = {
    TRIGGER_SMOKE: "SMOKE",
    TRIGGER_HEAT: "HEAT",
    TRIGGER_CO: "CARBON MONOXIDE",
    TRIGGER_ALL: "ALL",
}

MODELS = {
    "ed08": "FP2620W2",
    "1103": "WST-630",
    "1104": "FP1720W2-R",
    "7803": "W2-CO-10X",
    "c304": "W2-SVP-630",
}

# Status bits in the 0x71 base/battery frame.
BASE_ON_BIT = 0x04
LOW_BATTERY_BITS = 0x42


class DecodeError(ValueError):
    """Frame could not be decoded."""


@dataclass
class Event:
    """A decoded WiSafe2 event."""

    kind: str
    device: str
    model: Optional[str] = None
    trigger: Optional[str] = None
    result: Optional[str] = None
    base: Optional[str] = None
    battery: Optional[str] = None
    sequence: Optional[int] = None
    raw: bytes = field(default=b"", repr=False)

    @property
    def is_emergency(self) -> bool:
        return self.kind == "EMERGENCY"

    def as_dict(self) -> dict:
        d = {"kind": self.kind, "device": self.device}
        for name in ("model", "trigger", "result", "base", "battery", "sequence"):
            value = getattr(self, name)
            if value is not None:
                d[name] = value
        return d


def _hex(data: bytes) -> str:
    return data.hex()


def _model(data: bytes) -> str:
    return _hex(data)


def decode(frame: bytes) -> Event:
    """Decode one terminated WiSafe2 frame into an Event.

    Raises DecodeError on an unterminated, truncated or unrecognised frame.
    """
    if not frame:
        raise DecodeError("empty frame")
    if frame[-1] != TERMINATOR:
        raise DecodeError(f"frame not terminated with 0x7E: {_hex(frame)}")

    kind = frame[0]

    if kind == 0x70:
        return _decode_test(frame)
    if kind == 0x71:
        return _decode_base(frame)
    if kind == 0x50:
        return _decode_emergency(frame)
    if kind == 0x61:
        return _decode_silence(frame)
    if kind == 0xD2:
        return _decode_missing(frame)

    raise DecodeError(f"unknown frame type 0x{kind:02x}: {_hex(frame)}")


def _require(frame: bytes, length: int, what: str) -> None:
    if len(frame) < length:
        raise DecodeError(f"{what} frame too short ({len(frame)} < {length}): {_hex(frame)}")


def _decode_test(frame: bytes) -> Event:
    _require(frame, 11, "test")
    return Event(
        kind="TEST",
        device=_hex(frame[1:4]),
        trigger=TRIGGERS.get(frame[4], f"UNKNOWN_{frame[4]:02x}"),
        result="PASS" if frame[5] == 0x01 else "FAIL",
        model=_model(frame[6:8]),
        # A failed self-test is the alarm telling us its battery is flat.
        battery="OK" if frame[5] == 0x01 else "LOW",
        base="ON",
        sequence=frame[9],
        raw=frame,
    )


def _decode_base(frame: bytes) -> Event:
    _require(frame, 10, "base")
    status = frame[6]
    return Event(
        kind="BASE",
        device=_hex(frame[1:4]),
        model=_model(frame[4:6]),
        base="ON" if status & BASE_ON_BIT else "OFF",
        battery="LOW" if status & LOW_BATTERY_BITS else "OK",
        sequence=frame[8],
        raw=frame,
    )


def _decode_emergency(frame: bytes) -> Event:
    _require(frame, 9, "emergency")
    return Event(
        kind="EMERGENCY",
        device=_hex(frame[1:4]),
        trigger=TRIGGERS.get(frame[4], f"UNKNOWN_{frame[4]:02x}"),
        base="ON",
        sequence=frame[-2],
        raw=frame,
    )


def _decode_silence(frame: bytes) -> Event:
    _require(frame, 5, "silence")
    return Event(
        kind="SILENCE",
        device=_hex(frame[1:4]),
        base="ON",
        raw=frame,
    )


def _decode_missing(frame: bytes) -> Event:
    # The missing device's ID sits at offsets 6-8; offsets 1-3 identify the peer that
    # noticed it was gone.
    _require(frame, 14, "missing")
    return Event(
        kind="MISSING",
        device=_hex(frame[6:9]),
        base="MISSING",
        battery="MISSING",
        raw=frame,
    )


class FrameReader:
    """Reassembles a byte stream into terminated frames.

    On losing sync (a frame that runs past max_frame without a terminator) the reader
    discards everything up to and including the next terminator. That costs us one real
    frame, which is the right trade: alarms repeat emergency frames while in alarm, so a
    dropped frame arrives again shortly, whereas a frame assembled from garbage plus real
    bytes would be an entirely fabricated event.
    """

    def __init__(self, max_frame: int = 25) -> None:
        self.max_frame = max_frame
        self._buf = bytearray()
        self._resyncing = False
        self.desyncs = 0

    def feed(self, data: bytes) -> list[bytes]:
        """Push bytes in, get complete frames out."""
        frames = []
        for byte in data:
            if self._resyncing:
                # Throw bytes away until a terminator re-establishes a frame boundary.
                if byte == TERMINATOR:
                    self._resyncing = False
                continue

            self._buf.append(byte)
            if byte == TERMINATOR:
                frames.append(bytes(self._buf))
                self._buf.clear()
            elif len(self._buf) > self.max_frame:
                self._buf.clear()
                self._resyncing = True
                self.desyncs += 1
        return frames


def parse_hex(text: str) -> bytes:
    """Parse a capture line like '70 2D 8D 01 81 01 ED 08 07 03 7E' into bytes."""
    return bytes(int(tok, 16) for tok in text.split())
