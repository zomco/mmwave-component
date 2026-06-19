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

ld2410c_ns = cg.esphome_ns.namespace("ld2410c")
LD2410CComponent = ld2410c_ns.class_("LD2410CComponent", cg.Component, uart.UARTDevice)

CONF_PRESENCE = "presence"
CONF_TARGET_STATE = "target_state"
CONF_MOVING_DISTANCE = "moving_distance"
CONF_MOVING_ENERGY = "moving_energy"
CONF_STATIONARY_DISTANCE = "stationary_distance"
CONF_STATIONARY_ENERGY = "stationary_energy"
CONF_DETECTION_DISTANCE = "detection_distance"

# Spatial projection entities
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
CONF_DISTANCE_MIN = "distance_min"
CONF_DISTANCE_MAX = "distance_max"

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(LD2410CComponent),
            # Calibration parameters
            cv.Optional(CONF_RADAR_X, default=0.0): cv.float_,
            cv.Optional(CONF_RADAR_Y, default=0.0): cv.float_,
            cv.Optional(CONF_RADAR_Z, default=240.0): cv.float_,
            cv.Optional(CONF_YAW, default=0.0): cv.float_range(min=-180.0, max=180.0),
            cv.Optional(CONF_PITCH, default=0.0): cv.float_range(min=-90.0, max=90.0),
            cv.Optional(CONF_ROLL, default=0.0): cv.float_range(min=-90.0, max=90.0),
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
            cv.Optional(CONF_DETECTION_DISTANCE): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                device_class=DEVICE_CLASS_DISTANCE,
                accuracy_decimals=0,
            ),
            
            # Spatial Projection Entities
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
    if CONF_DETECTION_DISTANCE in config:
        sens = await sensor.new_sensor(config[CONF_DETECTION_DISTANCE])
        cg.add(var.set_detection_distance_sensor(sens))
        
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
