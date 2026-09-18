"""Tests for the CI config splicer."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from make_test_config import splice  # noqa: E402

SHIPPED = ROOT / "firmware/esphome/wisafe2-bridge.yaml"


def test_splices_real_config():
    out = splice(SHIPPED.read_text())
    assert 'name: "CI Smoke"' in out
    assert 'name: "CI Heat"' in out
    assert "kind: heat" in out
    # The commented-out placeholders must be gone, not merely appended to.
    assert "______" not in out


def test_result_is_valid_yaml_structure():
    yaml = pytest.importorskip("yaml")

    class Loader(yaml.SafeLoader):
        pass

    # The config uses !secret, which is ESPHome-specific.
    Loader.add_constructor("!secret", lambda loader, node: "redacted")

    parsed = yaml.load(splice(SHIPPED.read_text()), Loader=Loader)
    alarms = parsed["wisafe2"]["alarms"]
    assert len(alarms) == 2
    assert {a["kind"] for a in alarms} == {"smoke", "heat"}
    assert {a["device"] for a in alarms} == {"2d8d01", "a76f18"}


def test_missing_markers_fail_loudly():
    with pytest.raises(SystemExit, match="could not find the alarms block"):
        splice("wisafe2:\n  id: bridge\n")


def test_reversed_markers_fail_loudly():
    with pytest.raises(SystemExit, match="appears before"):
        splice("# --- Bridge health\n  alarms:\n")
