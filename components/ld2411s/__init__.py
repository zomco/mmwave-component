import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart, sensor, binary_sensor
from esphome.const import (
    CONF_ID,
    CONF_DISTANCE,
    UNIT_CENTIMETER,
    STATE_CLASS_MEASUREMENT,
    DEVICE_CLASS_PRESENCE,
    DEVICE_CLASS_DISTANCE,
    DEVICE_CLASS_MOTION,
)

CODEOWNERS = ["@zomco"]
DEPENDENCIES = ["uart"]
AUTO_LOAD = ["sensor", "binary_sensor"]

ld2411s_ns = cg.esphome_ns.namespace("ld2411s")
LD2411SComponent = ld2411s_ns.class_("LD2411SComponent", cg.Component, uart.UARTDevice)

CONF_PRESENCE = "presence"
CONF_MOVING_TARGET = "moving_target"
CONF_MICRO_TARGET = "micro_target"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(LD2411SComponent),
        cv.Optional(CONF_DISTANCE): sensor.sensor_schema(
            unit_of_measurement=UNIT_CENTIMETER,
            device_class=DEVICE_CLASS_DISTANCE,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        cv.Optional(CONF_PRESENCE): binary_sensor.binary_sensor_schema(
            device_class=DEVICE_CLASS_PRESENCE,
        ),
        cv.Optional(CONF_MOVING_TARGET): binary_sensor.binary_sensor_schema(
            device_class=DEVICE_CLASS_MOTION,
        ),
        cv.Optional(CONF_MICRO_TARGET): binary_sensor.binary_sensor_schema(
            device_class=DEVICE_CLASS_MOTION,
        ),
    }
).extend(cv.COMPONENT_SCHEMA).extend(uart.UART_DEVICE_SCHEMA)

async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)

    if CONF_DISTANCE in config:
        sens = await sensor.new_sensor(config[CONF_DISTANCE])
        cg.add(var.set_distance_sensor(sens))

    if CONF_PRESENCE in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_PRESENCE])
        cg.add(var.set_presence_sensor(sens))
        
    if CONF_MOVING_TARGET in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_MOVING_TARGET])
        cg.add(var.set_moving_target_sensor(sens))

    if CONF_MICRO_TARGET in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_MICRO_TARGET])
        cg.add(var.set_micro_target_sensor(sens))
