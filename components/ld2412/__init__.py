import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart, binary_sensor, sensor
from esphome.const import (
    CONF_ID,
    DEVICE_CLASS_DISTANCE,
    DEVICE_CLASS_PRESENCE,
    UNIT_CENTIMETER,
)

DEPENDENCIES = ["uart"]
AUTO_LOAD = ["binary_sensor", "sensor"]

ld2412_ns = cg.esphome_ns.namespace("ld2412")
ld2412Component = ld2412_ns.class_("ld2412Component", cg.Component, uart.UARTDevice)

CONF_PRESENCE = "presence"
CONF_TARGET_STATE = "target_state"
CONF_MOVING_DISTANCE = "moving_distance"
CONF_MOVING_ENERGY = "moving_energy"
CONF_STATIONARY_DISTANCE = "stationary_distance"
CONF_STATIONARY_ENERGY = "stationary_energy"
CONF_LIGHT_SENSOR = "light"

# Gate Energy Sensors
CONF_GATE_MOVE_ENERGY = "gate_move_energy"
CONF_GATE_STILL_ENERGY = "gate_still_energy"

# Calibration parameters
CONF_RADAR_X = "radar_x"
CONF_RADAR_Y = "radar_y"
CONF_RADAR_Z = "radar_z"
CONF_YAW = "yaw"
CONF_PITCH = "pitch"
CONF_ROLL = "roll"
CONF_DISTANCE_MIN = "distance_min"
CONF_DISTANCE_MAX = "distance_max"

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(ld2412Component),
            cv.Optional(CONF_DISTANCE_MIN, default=0.0): cv.float_,
            cv.Optional(CONF_DISTANCE_MAX, default=0.0): cv.float_,
            
            # Entities
            cv.Optional(CONF_PRESENCE): binary_sensor.binary_sensor_schema(
                device_class=DEVICE_CLASS_PRESENCE,
            ),
            cv.Optional(CONF_TARGET_STATE): sensor.sensor_schema(
                accuracy_decimals=0,
            ),
            cv.Optional(CONF_MOVING_DISTANCE): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                device_class=DEVICE_CLASS_DISTANCE,
                accuracy_decimals=0,
            ),
            cv.Optional(CONF_MOVING_ENERGY): sensor.sensor_schema(
                accuracy_decimals=0,
            ),
            cv.Optional(CONF_STATIONARY_DISTANCE): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                device_class=DEVICE_CLASS_DISTANCE,
                accuracy_decimals=0,
            ),
            cv.Optional(CONF_STATIONARY_ENERGY): sensor.sensor_schema(
                accuracy_decimals=0,
            ),
            cv.Optional(CONF_LIGHT_SENSOR): sensor.sensor_schema(
                accuracy_decimals=0,
            ),
        }
    )
    .extend(
        {
            cv.Optional(f"g{x}"): cv.Schema(
                {
                    cv.Optional(CONF_GATE_MOVE_ENERGY): sensor.sensor_schema(
                        accuracy_decimals=0,
                    ),
                    cv.Optional(CONF_GATE_STILL_ENERGY): sensor.sensor_schema(
                        accuracy_decimals=0,
                    ),
                }
            )
            for x in range(14)
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(uart.UART_DEVICE_SCHEMA)
)

async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)

    # Calibration parameters
    cg.add(var.set_distance_min(config[CONF_DISTANCE_MIN]))
    cg.add(var.set_distance_max(config[CONF_DISTANCE_MAX]))

    if CONF_PRESENCE in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_PRESENCE])
        cg.add(var.set_presence_sensor(sens))
    if CONF_TARGET_STATE in config:
        sens = await sensor.new_sensor(config[CONF_TARGET_STATE])
        cg.add(var.set_target_state_sensor(sens))
    if CONF_MOVING_DISTANCE in config:
        sens = await sensor.new_sensor(config[CONF_MOVING_DISTANCE])
        cg.add(var.set_moving_distance_sensor(sens))
    if CONF_MOVING_ENERGY in config:
        sens = await sensor.new_sensor(config[CONF_MOVING_ENERGY])
        cg.add(var.set_moving_energy_sensor(sens))
    if CONF_STATIONARY_DISTANCE in config:
        sens = await sensor.new_sensor(config[CONF_STATIONARY_DISTANCE])
        cg.add(var.set_stationary_distance_sensor(sens))
    if CONF_STATIONARY_ENERGY in config:
        sens = await sensor.new_sensor(config[CONF_STATIONARY_ENERGY])
        cg.add(var.set_stationary_energy_sensor(sens))
    if CONF_LIGHT_SENSOR in config:
        sens = await sensor.new_sensor(config[CONF_LIGHT_SENSOR])
        cg.add(var.set_light_sensor(sens))
        
    for x in range(14):
        if gate_conf := config.get(f"g{x}"):
            if move_config := gate_conf.get(CONF_GATE_MOVE_ENERGY):
                sens = await sensor.new_sensor(move_config)
                cg.add(var.set_gate_move_sensor(x, sens))
            if still_config := gate_conf.get(CONF_GATE_STILL_ENERGY):
                sens = await sensor.new_sensor(still_config)
                cg.add(var.set_gate_still_sensor(x, sens))
