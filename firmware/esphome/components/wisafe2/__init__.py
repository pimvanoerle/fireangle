"""ESPHome external component for the FireAngel WiSafe2 mesh.

Declare each alarm once under `alarms:` and this generates four entities per alarm:
an event text sensor, an emergency binary sensor, a battery problem sensor and an
on-base sensor. That replaces the 24 hand-written template sensors the serial-bridge
approach needs for eight alarms.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import pins
from esphome.components import binary_sensor, text_sensor
from esphome.const import (
    CONF_ID,
    CONF_NAME,
    CONF_TRIGGER_ID,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_PROBLEM,
    ENTITY_CATEGORY_DIAGNOSTIC,
)

CODEOWNERS = ["@pimvanoerle"]
DEPENDENCIES = ["binary_sensor", "text_sensor"]
AUTO_LOAD = ["binary_sensor", "text_sensor"]
MULTI_CONF = False

wisafe2_ns = cg.esphome_ns.namespace("wisafe2")
Wisafe2Component = wisafe2_ns.class_("Wisafe2Component", cg.Component)
Wisafe2Alarm = wisafe2_ns.class_("Wisafe2Alarm")

CONF_SS_PIN = "ss_pin"
CONF_SCK_PIN = "sck_pin"
CONF_SDI_PIN = "sdi_pin"
CONF_SDO_PIN = "sdo_pin"
CONF_IRQ_PIN = "irq_pin"
CONF_DEVICE_ID = "device_id"
CONF_MODEL_ID = "model_id"
CONF_RAW_MODE = "raw_mode"
CONF_ALARMS = "alarms"
CONF_DEVICE = "device"
CONF_KIND = "kind"

# Alarm kinds are informational -- they set the icon and let automations group by type.
# The wire protocol reports the trigger, so this is not used to interpret frames.
KINDS = ["smoke", "heat", "co"]

KIND_ICONS = {
    "smoke": "mdi:smoke-detector-variant",
    "heat": "mdi:thermometer-alert",
    "co": "mdi:molecule-co",
}


def _device_id(value):
    """A 24-bit WiSafe2 device ID, written as 6 hex digits (e.g. '2d8d01')."""
    value = cv.string_strict(value).strip().lower().replace(" ", "")
    if len(value) != 6:
        raise cv.Invalid(f"device ID must be 6 hex digits, got {len(value)}: {value!r}")
    try:
        return int(value, 16)
    except ValueError as err:
        raise cv.Invalid(f"device ID must be hex: {value!r}") from err


def _model_id(value):
    """A 16-bit model ID, written as 4 hex digits (e.g. '1103')."""
    value = cv.string_strict(value).strip().lower().replace(" ", "")
    if len(value) != 4:
        raise cv.Invalid(f"model ID must be 4 hex digits, got {len(value)}: {value!r}")
    try:
        return int(value, 16)
    except ValueError as err:
        raise cv.Invalid(f"model ID must be hex: {value!r}") from err


ALARM_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(Wisafe2Alarm),
        cv.Required(CONF_NAME): cv.string,
        cv.Required(CONF_DEVICE): _device_id,
        cv.Optional(CONF_KIND, default="smoke"): cv.one_of(*KINDS, lower=True),
    }
)


def _unique_devices(config):
    """Two alarms sharing a device ID would silently mirror each other's state."""
    seen = {}
    for alarm in config[CONF_ALARMS]:
        device = alarm[CONF_DEVICE]
        if device in seen:
            raise cv.Invalid(
                f"duplicate device ID {device:06x}: "
                f"{seen[device]!r} and {alarm[CONF_NAME]!r}"
            )
        seen[device] = alarm[CONF_NAME]
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(Wisafe2Component),
            cv.Required(CONF_SS_PIN): pins.internal_gpio_input_pin_schema,
            cv.Required(CONF_SCK_PIN): pins.internal_gpio_input_pin_schema,
            cv.Required(CONF_SDI_PIN): pins.internal_gpio_input_pin_schema,
            cv.Required(CONF_SDO_PIN): pins.internal_gpio_output_pin_schema,
            cv.Required(CONF_IRQ_PIN): pins.internal_gpio_output_pin_schema,
            cv.Optional(CONF_DEVICE_ID, default="a5b813"): _device_id,
            cv.Optional(CONF_MODEL_ID, default="1103"): _model_id,
            cv.Optional(CONF_RAW_MODE, default=False): cv.boolean,
            cv.Optional(CONF_ALARMS, default=[]): cv.ensure_list(ALARM_SCHEMA),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    _unique_devices,
)


async def _alarm_to_code(config, parent):
    alarm = cg.new_Pvariable(config[CONF_ID])
    cg.add(alarm.set_device(config[CONF_DEVICE]))

    name = config[CONF_NAME]
    icon = KIND_ICONS[config[CONF_KIND]]

    event = await text_sensor.new_text_sensor(
        {
            CONF_ID: cv.declare_id(text_sensor.TextSensor)(f"{config[CONF_ID]}_event"),
            CONF_NAME: f"{name} Event",
            "icon": icon,
            "disabled_by_default": False,
        }
    )
    cg.add(alarm.set_event_sensor(event))

    emergency = await binary_sensor.new_binary_sensor(
        {
            CONF_ID: cv.declare_id(binary_sensor.BinarySensor)(
                f"{config[CONF_ID]}_emergency"
            ),
            CONF_NAME: f"{name} Emergency",
            "device_class": DEVICE_CLASS_PROBLEM,
            "icon": icon,
            "disabled_by_default": False,
        }
    )
    cg.add(alarm.set_emergency_sensor(emergency))

    battery = await binary_sensor.new_binary_sensor(
        {
            CONF_ID: cv.declare_id(binary_sensor.BinarySensor)(
                f"{config[CONF_ID]}_battery"
            ),
            CONF_NAME: f"{name} Battery",
            "device_class": DEVICE_CLASS_BATTERY,
            "entity_category": ENTITY_CATEGORY_DIAGNOSTIC,
            "disabled_by_default": False,
        }
    )
    cg.add(alarm.set_battery_sensor(battery))

    base = await binary_sensor.new_binary_sensor(
        {
            CONF_ID: cv.declare_id(binary_sensor.BinarySensor)(f"{config[CONF_ID]}_base"),
            CONF_NAME: f"{name} On Base",
            "device_class": DEVICE_CLASS_PROBLEM,
            "entity_category": ENTITY_CATEGORY_DIAGNOSTIC,
            "disabled_by_default": False,
        }
    )
    cg.add(alarm.set_base_sensor(base))

    cg.add(parent.register_listener(alarm))


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    ss = await cg.gpio_pin_expression(config[CONF_SS_PIN])
    sck = await cg.gpio_pin_expression(config[CONF_SCK_PIN])
    sdi = await cg.gpio_pin_expression(config[CONF_SDI_PIN])
    sdo = await cg.gpio_pin_expression(config[CONF_SDO_PIN])
    irq = await cg.gpio_pin_expression(config[CONF_IRQ_PIN])
    cg.add(var.set_pins(ss, sck, sdi, sdo, irq))

    cg.add(var.set_device_id(config[CONF_DEVICE_ID]))
    cg.add(var.set_model_id(config[CONF_MODEL_ID]))
    cg.add(var.set_raw_mode(config[CONF_RAW_MODE]))

    for alarm in config[CONF_ALARMS]:
        await _alarm_to_code(alarm, var)
