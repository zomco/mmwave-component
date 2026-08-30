import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart, binary_sensor, sensor
from esphome.const import (
    CONF_ID,
    CONF_UART_ID,
    CONF_DISTANCE,
    DEVICE_CLASS_DISTANCE,
    DEVICE_CLASS_PRESENCE,
    UNIT_CENTIMETER,
)

DEPENDENCIES = ["uart"]
AUTO_LOAD = ["binary_sensor", "sensor"]

ld6002_ns = cg.esphome_ns.namespace("ld6002")
LD6002Component = ld6002_ns.class_("LD6002Component", cg.Component, uart.UARTDevice)

CONF_PRESENCE = "presence"
CONF_RESPIRATION_RATE = "respiration_rate"
CONF_HEART_RATE = "heart_rate"
CONF_ROOM_X = "room_x"
CONF_ROOM_Y = "room_y"
CONF_ROOM_Z = "room_z"
CONF_IN_BOUNDARY = "in_boundary"

# Calibration parameters
CONF_RADAR_X = "radar_x"
CONF_RADAR_Y = "radar_y"
CONF_RADAR_Z = "radar_z"
CONF_YAW = "yaw"
CONF_PITCH = "pitch"
CONF_ROLL = "roll"
CONF_BOUNDARY_GATES_PRESENCE = "boundary_gates_presence"
CONF_DISTANCE_MIN = "distance_min"
CONF_DISTANCE_MAX = "distance_max"

UNIT_BPM = "bpm"

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(LD6002Component),
            # Calibration parameters
            cv.Optional(CONF_RADAR_X, default=0.0): cv.float_,
            cv.Optional(CONF_RADAR_Y, default=0.0): cv.float_,
            cv.Optional(CONF_RADAR_Z, default=240.0): cv.float_,
            cv.Optional(CONF_YAW, default=0.0): cv.float_range(min=-180.0, max=180.0),
            cv.Optional(CONF_PITCH, default=0.0): cv.float_range(min=-90.0, max=90.0),
            cv.Optional(CONF_ROLL, default=0.0): cv.float_range(min=-90.0, max=90.0),
            # 边界外的目标（隔墙鬼影）默认不计入 presence
            cv.Optional(CONF_BOUNDARY_GATES_PRESENCE, default=True): cv.boolean,
            cv.Optional(CONF_DISTANCE_MIN, default=0.0): cv.float_,
            cv.Optional(CONF_DISTANCE_MAX, default=0.0): cv.float_,
            
            # Entities
            cv.Optional(CONF_PRESENCE): binary_sensor.binary_sensor_schema(
                device_class=DEVICE_CLASS_PRESENCE,
            ),
            cv.Optional(CONF_DISTANCE): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                device_class=DEVICE_CLASS_DISTANCE,
                accuracy_decimals=1,
            ),
            cv.Optional(CONF_RESPIRATION_RATE): sensor.sensor_schema(
                unit_of_measurement=UNIT_BPM,
                accuracy_decimals=0,
            ),
            cv.Optional(CONF_HEART_RATE): sensor.sensor_schema(
                unit_of_measurement=UNIT_BPM,
                accuracy_decimals=0,
            ),
            cv.Optional(CONF_ROOM_X): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                device_class=DEVICE_CLASS_DISTANCE,
                accuracy_decimals=1,
            ),
            cv.Optional(CONF_ROOM_Y): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                device_class=DEVICE_CLASS_DISTANCE,
                accuracy_decimals=1,
            ),
            cv.Optional(CONF_ROOM_Z): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                device_class=DEVICE_CLASS_DISTANCE,
                accuracy_decimals=1,
            ),
            cv.Optional(CONF_IN_BOUNDARY): binary_sensor.binary_sensor_schema(),
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
    cg.add(var.set_radar_x(config[CONF_RADAR_X]))
    cg.add(var.set_radar_y(config[CONF_RADAR_Y]))
    cg.add(var.set_radar_z(config[CONF_RADAR_Z]))
    cg.add(var.set_yaw(config[CONF_YAW]))
    cg.add(var.set_pitch(config[CONF_PITCH]))
    cg.add(var.set_roll(config[CONF_ROLL]))
    cg.add(var.set_boundary_gates_presence(config[CONF_BOUNDARY_GATES_PRESENCE]))
    cg.add(var.set_distance_min(config[CONF_DISTANCE_MIN]))
    cg.add(var.set_distance_max(config[CONF_DISTANCE_MAX]))

    if CONF_PRESENCE in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_PRESENCE])
        cg.add(var.set_presence_sensor(sens))

    if CONF_DISTANCE in config:
        sens = await sensor.new_sensor(config[CONF_DISTANCE])
        cg.add(var.set_distance_sensor(sens))

    if CONF_RESPIRATION_RATE in config:
        sens = await sensor.new_sensor(config[CONF_RESPIRATION_RATE])
        cg.add(var.set_respiration_rate_sensor(sens))

    if CONF_HEART_RATE in config:
        sens = await sensor.new_sensor(config[CONF_HEART_RATE])
        cg.add(var.set_heart_rate_sensor(sens))

    if CONF_ROOM_X in config:
        sens = await sensor.new_sensor(config[CONF_ROOM_X])
        cg.add(var.set_room_x_sensor(sens))

    if CONF_ROOM_Y in config:
        sens = await sensor.new_sensor(config[CONF_ROOM_Y])
        cg.add(var.set_room_y_sensor(sens))

    if CONF_ROOM_Z in config:
        sens = await sensor.new_sensor(config[CONF_ROOM_Z])
        cg.add(var.set_room_z_sensor(sens))

    if CONF_IN_BOUNDARY in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_IN_BOUNDARY])
        cg.add(var.set_in_boundary_sensor(sens))
