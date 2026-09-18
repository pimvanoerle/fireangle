"""Decoder tests against the real captures in docs/protocol.md.

Every frame here came off a logic analyser on an actual WiSafe2 mesh, so these tests pin
our understanding of the protocol. If a test here fails, the spec is wrong, not the test.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from wisafe2 import DecodeError, FrameReader, decode, parse_hex  # noqa: E402


def d(text: str):
    return decode(parse_hex(text))


class TestTestEvent:
    def test_smoke_pass(self):
        e = d("70 2D 8D 01 81 01 ED 08 07 03 7E")
        assert e.kind == "TEST"
        assert e.device == "2d8d01"
        assert e.trigger == "SMOKE"
        assert e.result == "PASS"
        assert e.model == "ed08"
        assert e.battery == "OK"
        assert e.sequence == 0x03

    def test_smoke_fail_is_low_battery(self):
        e = d("70 2D 8D 01 81 00 ED 08 07 0E 7E")
        assert e.result == "FAIL"
        assert e.battery == "LOW"

    def test_heat_trigger_decodes_as_heat_not_fire(self):
        # FP1720W2-R, the battery sibling of our FP1740W2-R kitchen heat alarm.
        # The reference sketch reports this as FIRE; we must not.
        e = d("70 A7 6F 18 82 01 11 04 14 0E 7E")
        assert e.trigger == "HEAT"
        assert e.model == "1104"
        assert e.device == "a76f18"

    def test_carbon_monoxide(self):
        e = d("70 11 CE 01 41 01 78 03 03 0E 7E")
        assert e.trigger == "CARBON MONOXIDE"
        assert e.model == "7803"

    def test_all_triggers(self):
        e = d("70 60 1A 03 FF 01 C3 04 09 09 7E")
        assert e.trigger == "ALL"
        assert e.model == "c304"

    def test_wst630_variants_share_a_model(self):
        a = d("70 13 F4 3E 81 01 11 03 02 07 7E")
        b = d("70 06 F9 3E 81 01 11 03 02 0A 7E")
        assert a.model == b.model == "1103"
        assert a.device != b.device


class TestBaseEvent:
    def test_off_base_battery_ok(self):
        e = d("71 06 F9 3E 11 03 01 02 0F 7E")
        assert e.kind == "BASE"
        assert e.device == "06f93e"
        assert e.base == "OFF"
        assert e.battery == "OK"

    def test_on_base_low_battery(self):
        e = d("71 2D 8D 01 ED 08 47 07 0B 7E")
        assert e.base == "ON"
        assert e.battery == "LOW"

    def test_off_base_low_battery(self):
        e = d("71 2D 8D 01 ED 08 43 07 0F 7E")
        assert e.base == "OFF"
        assert e.battery == "LOW"

    def test_on_base_battery_ok(self):
        e = d("71 60 1A 03 C3 04 05 09 0D 7E")
        assert e.base == "ON"
        assert e.battery == "OK"

    def test_strobe_on_base(self):
        e = d("71 60 1A 03 C3 04 0F 09 0A 7E")
        assert e.base == "ON"
        assert e.model == "c304"


class TestEmergency:
    def test_fire_emergency(self):
        e = d("50 06 F9 3E 81 02 02 06 7E")
        assert e.kind == "EMERGENCY"
        assert e.is_emergency
        assert e.device == "06f93e"
        assert e.trigger == "SMOKE"

    def test_non_emergency_is_not_flagged(self):
        assert not d("71 06 F9 3E 11 03 01 02 0F 7E").is_emergency


class TestMissingDevice:
    def test_missing_id_comes_from_offset_six(self):
        # 60 1A 03 is the missing device (a W2-SVP-630); 2A 38 41 is the reporter.
        e = d("D2 2A 38 41 00 EF 60 1A 03 00 00 09 40 7E")
        assert e.kind == "MISSING"
        assert e.device == "601a03"
        assert e.base == "MISSING"
        assert e.battery == "MISSING"


class TestSilence:
    def test_silence(self):
        e = d("61 2D 8D 01 80 01 7E")
        assert e.kind == "SILENCE"
        assert e.device == "2d8d01"


class TestMalformed:
    def test_empty(self):
        with pytest.raises(DecodeError):
            decode(b"")

    def test_unterminated(self):
        with pytest.raises(DecodeError):
            d("70 2D 8D 01 81 01 ED 08 07 03")

    def test_unknown_type(self):
        with pytest.raises(DecodeError):
            d("FF 00 7E")

    def test_truncated(self):
        with pytest.raises(DecodeError):
            d("70 2D 8D 7E")

    def test_unknown_trigger_is_reported_not_swallowed(self):
        e = d("70 2D 8D 01 99 01 ED 08 07 03 7E")
        assert e.trigger == "UNKNOWN_99"


class TestFrameReader:
    def test_splits_on_terminator(self):
        r = FrameReader()
        frames = r.feed(parse_hex("50 06 F9 3E 81 02 02 06 7E 61 2D 8D 01 80 01 7E"))
        assert len(frames) == 2
        assert decode(frames[0]).kind == "EMERGENCY"
        assert decode(frames[1]).kind == "SILENCE"

    def test_reassembles_across_chunks(self):
        r = FrameReader()
        assert r.feed(parse_hex("50 06 F9")) == []
        frames = r.feed(parse_hex("3E 81 02 02 06 7E"))
        assert len(frames) == 1
        assert decode(frames[0]).device == "06f93e"

    def test_runaway_never_fabricates_a_frame(self):
        # Garbage must not be glued onto the front of the next real frame.
        r = FrameReader()
        r.feed(bytes([0x00] * 30))
        assert r.desyncs == 1
        # The frame that closes the desync is sacrificed...
        assert r.feed(parse_hex("50 06 F9 3E 81 02 02 06 7E")) == []
        # ...and the one after it decodes cleanly.
        frames = r.feed(parse_hex("50 06 F9 3E 81 02 02 07 7E"))
        assert len(frames) == 1
        assert decode(frames[0]).kind == "EMERGENCY"
        assert decode(frames[0]).device == "06f93e"
