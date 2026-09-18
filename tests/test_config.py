"""Tests for the ESPHome component's config validation.

These run without ESPHome installed by exercising the pure-Python validators directly.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

COMPONENT = (
    Path(__file__).resolve().parents[1]
    / "firmware/esphome/components/wisafe2/__init__.py"
)

esphome = pytest.importorskip("esphome", reason="ESPHome not installed")


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("wisafe2_component", COMPONENT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["wisafe2_component"] = module
    spec.loader.exec_module(module)
    return module


class TestDeviceId:
    def test_parses_lower_hex(self, mod):
        assert mod._device_id("2d8d01") == 0x2D8D01

    def test_parses_upper_hex(self, mod):
        assert mod._device_id("2D8D01") == 0x2D8D01

    def test_rejects_wrong_length(self, mod):
        import esphome.config_validation as cv

        with pytest.raises(cv.Invalid):
            mod._device_id("2d8d")

    def test_rejects_non_hex(self, mod):
        import esphome.config_validation as cv

        with pytest.raises(cv.Invalid):
            mod._device_id("zzzzzz")


class TestModelId:
    def test_parses(self, mod):
        assert mod._model_id("1103") == 0x1103

    def test_heat_model(self, mod):
        assert mod._model_id("1104") == 0x1104

    def test_rejects_wrong_length(self, mod):
        import esphome.config_validation as cv

        with pytest.raises(cv.Invalid):
            mod._model_id("110")


class TestDuplicateDevices:
    def test_rejects_duplicates(self, mod):
        import esphome.config_validation as cv

        config = {
            "alarms": [
                {"device": 0x2D8D01, "name": "Landing Smoke"},
                {"device": 0x2D8D01, "name": "Kitchen Heat"},
            ]
        }
        with pytest.raises(cv.Invalid, match="duplicate device ID 2d8d01"):
            mod._unique_devices(config)

    def test_accepts_distinct(self, mod):
        config = {
            "alarms": [
                {"device": 0x2D8D01, "name": "Landing Smoke"},
                {"device": 0xA76F18, "name": "Kitchen Heat"},
            ]
        }
        assert mod._unique_devices(config) is config
