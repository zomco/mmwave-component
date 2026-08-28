import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart, binary_sensor, sensor, text_sensor
from esphome.const import (
    CONF_ID,
    DEVICE_CLASS_DISTANCE,
    DEVICE_CLASS_PRESENCE,
    ENTITY_CATEGORY_DIAGNOSTIC,
    UNIT_CENTIMETER,
    UNIT_METER,
    UNIT_DEGREES,
    UNIT_SECOND,
)

DEPENDENCIES = ["uart"]
AUTO_LOAD = ["binary_sensor", "sensor", "text_sensor"]

ld2451_ns = cg.esphome_ns.namespace("ld2451")
LD2451Component = ld2451_ns.class_("LD2451Component", cg.Component, uart.UARTDevice)

CONF_PRESENCE = "presence"
CONF_ALARM = "alarm"
CONF_TARGET_COUNT = "target_count"
CONF_TARGET_FRAME = "target_frame"

# Calibration parameters
CONF_RADAR_X = "radar_x"
CONF_RADAR_Y = "radar_y"
CONF_RADAR_Z = "radar_z"
CONF_YAW = "yaw"
CONF_PITCH = "pitch"
CONF_ROLL = "roll"
CONF_DISTANCE_MIN = "distance_min"
CONF_DISTANCE_MAX = "distance_max"
CONF_BOUNDARY_GATES_PRESENCE = "boundary_gates_presence"

# Radar-side configuration read-back (protocol 1.2.4 / 1.2.6 / 1.2.7). These
# publish what the radar answered to a query, not what was written to it, so a
# rejected command is visible instead of silently assumed.
CONF_FIRMWARE_VERSION = "firmware_version"
CONF_DIRECTION_FILTER = "direction_filter"
CONF_MAX_DETECTION_DISTANCE = "max_detection_distance"
CONF_MIN_SPEED = "min_speed"
CONF_NO_TARGET_DELAY = "no_target_delay"
CONF_TRIGGER_COUNT = "trigger_count"
CONF_SNR_THRESHOLD = "snr_threshold"

UNIT_KM_PER_H = "km/h"

def target_schema(target_id):
    return cv.Schema({
        cv.Optional("distance"): sensor.sensor_schema(
            unit_of_measurement=UNIT_CENTIMETER,
            device_class=DEVICE_CLASS_DISTANCE,
            accuracy_decimals=2,
        ),
        cv.Optional("angle"): sensor.sensor_schema(
            unit_of_measurement=UNIT_DEGREES,
            accuracy_decimals=0,
        ),
        cv.Optional("speed"): sensor.sensor_schema(
            unit_of_measurement=UNIT_KM_PER_H,
            accuracy_decimals=0,
        ),
        cv.Optional("snr"): sensor.sensor_schema(
            accuracy_decimals=0,
        ),
        cv.Optional("x"): sensor.sensor_schema(
            unit_of_measurement=UNIT_CENTIMETER,
            device_class=DEVICE_CLASS_DISTANCE,
            accuracy_decimals=1,
        ),
        cv.Optional("y"): sensor.sensor_schema(
            unit_of_measurement=UNIT_CENTIMETER,
            device_class=DEVICE_CLASS_DISTANCE,
            accuracy_decimals=1,
        ),
        cv.Optional("room_x"): sensor.sensor_schema(
            unit_of_measurement=UNIT_CENTIMETER,
            device_class=DEVICE_CLASS_DISTANCE,
            accuracy_decimals=1,
        ),
        cv.Optional("room_y"): sensor.sensor_schema(
            unit_of_measurement=UNIT_CENTIMETER,
            device_class=DEVICE_CLASS_DISTANCE,
            accuracy_decimals=1,
        ),
        cv.Optional("room_z"): sensor.sensor_schema(
            unit_of_measurement=UNIT_CENTIMETER,
            device_class=DEVICE_CLASS_DISTANCE,
            accuracy_decimals=1,
        ),
        cv.Optional("in_boundary"): binary_sensor.binary_sensor_schema(),
    })

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(LD2451Component),
            # Calibration parameters
            cv.Optional(CONF_RADAR_X, default=0.0): cv.float_,
            cv.Optional(CONF_RADAR_Y, default=0.0): cv.float_,
            cv.Optional(CONF_RADAR_Z, default=240.0): cv.float_,
            cv.Optional(CONF_YAW, default=0.0): cv.float_range(min=-180.0, max=180.0),
            cv.Optional(CONF_PITCH, default=0.0): cv.float_range(min=-90.0, max=90.0),
            cv.Optional(CONF_ROLL, default=0.0): cv.float_range(min=-90.0, max=90.0),
            cv.Optional(CONF_DISTANCE_MIN, default=0.0): cv.float_,
            cv.Optional(CONF_DISTANCE_MAX, default=0.0): cv.float_,
            # 边界外的目标默认不计入 presence
            cv.Optional(CONF_BOUNDARY_GATES_PRESENCE, default=True): cv.boolean,
            
            # Globals
            cv.Optional(CONF_PRESENCE): binary_sensor.binary_sensor_schema(
                device_class=DEVICE_CLASS_PRESENCE,
            ),
            cv.Optional(CONF_ALARM): binary_sensor.binary_sensor_schema(),
            cv.Optional(CONF_TARGET_COUNT): sensor.sensor_schema(
                accuracy_decimals=0,
            ),
            cv.Optional(CONF_TARGET_FRAME): text_sensor.text_sensor_schema(
                icon="mdi:radar",
            ),

            # Configuration read-back
            cv.Optional(CONF_FIRMWARE_VERSION): text_sensor.text_sensor_schema(
                icon="mdi:chip",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_DIRECTION_FILTER): text_sensor.text_sensor_schema(
                icon="mdi:swap-horizontal",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_MAX_DETECTION_DISTANCE): sensor.sensor_schema(
                unit_of_measurement=UNIT_METER,
                device_class=DEVICE_CLASS_DISTANCE,
                accuracy_decimals=0,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_MIN_SPEED): sensor.sensor_schema(
                unit_of_measurement=UNIT_KM_PER_H,
                accuracy_decimals=0,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_NO_TARGET_DELAY): sensor.sensor_schema(
                unit_of_measurement=UNIT_SECOND,
                accuracy_decimals=0,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_TRIGGER_COUNT): sensor.sensor_schema(
                accuracy_decimals=0,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_SNR_THRESHOLD): sensor.sensor_schema(
                accuracy_decimals=0,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            
            # Targets
            cv.Optional("target_1"): target_schema("target_1"),
            cv.Optional("target_2"): target_schema("target_2"),
            cv.Optional("target_3"): target_schema("target_3"),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(uart.UART_DEVICE_SCHEMA)
)

async def setup_target(var, config, target_idx, target_key):
    if target_key not in config:
        return
    t_config = config[target_key]
    
    if "distance" in t_config:
        sens = await sensor.new_sensor(t_config["distance"])
        cg.add(var.set_target_distance_sensor(target_idx, sens))
    if "angle" in t_config:
        sens = await sensor.new_sensor(t_config["angle"])
        cg.add(var.set_target_angle_sensor(target_idx, sens))
    if "speed" in t_config:
        sens = await sensor.new_sensor(t_config["speed"])
        cg.add(var.set_target_speed_sensor(target_idx, sens))
    if "snr" in t_config:
        sens = await sensor.new_sensor(t_config["snr"])
        cg.add(var.set_target_snr_sensor(target_idx, sens))
    if "x" in t_config:
        sens = await sensor.new_sensor(t_config["x"])
        cg.add(var.set_target_x_sensor(target_idx, sens))
    if "y" in t_config:
        sens = await sensor.new_sensor(t_config["y"])
        cg.add(var.set_target_y_sensor(target_idx, sens))
    if "room_x" in t_config:
        sens = await sensor.new_sensor(t_config["room_x"])
        cg.add(var.set_target_room_x_sensor(target_idx, sens))
    if "room_y" in t_config:
        sens = await sensor.new_sensor(t_config["room_y"])
        cg.add(var.set_target_room_y_sensor(target_idx, sens))
    if "room_z" in t_config:
        sens = await sensor.new_sensor(t_config["room_z"])
        cg.add(var.set_target_room_z_sensor(target_idx, sens))
    if "in_boundary" in t_config:
        sens = await binary_sensor.new_binary_sensor(t_config["in_boundary"])
        cg.add(var.set_target_in_boundary_sensor(target_idx, sens))

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
    cg.add(var.set_boundary_gates_presence(config[CONF_BOUNDARY_GATES_PRESENCE]))

    if CONF_PRESENCE in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_PRESENCE])
        cg.add(var.set_presence_sensor(sens))
    if CONF_ALARM in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_ALARM])
        cg.add(var.set_alarm_sensor(sens))
    if CONF_TARGET_COUNT in config:
        sens = await sensor.new_sensor(config[CONF_TARGET_COUNT])
        cg.add(var.set_target_count_sensor(sens))
    if CONF_TARGET_FRAME in config:
        sens = await text_sensor.new_text_sensor(config[CONF_TARGET_FRAME])
        cg.add(var.set_target_frame_sensor(sens))

    if CONF_FIRMWARE_VERSION in config:
        sens = await text_sensor.new_text_sensor(config[CONF_FIRMWARE_VERSION])
        cg.add(var.set_firmware_version_sensor(sens))
    if CONF_DIRECTION_FILTER in config:
        sens = await text_sensor.new_text_sensor(config[CONF_DIRECTION_FILTER])
        cg.add(var.set_direction_filter_sensor(sens))
    if CONF_MAX_DETECTION_DISTANCE in config:
        sens = await sensor.new_sensor(config[CONF_MAX_DETECTION_DISTANCE])
        cg.add(var.set_max_detection_distance_sensor(sens))
    if CONF_MIN_SPEED in config:
        sens = await sensor.new_sensor(config[CONF_MIN_SPEED])
        cg.add(var.set_min_speed_sensor(sens))
    if CONF_NO_TARGET_DELAY in config:
        sens = await sensor.new_sensor(config[CONF_NO_TARGET_DELAY])
        cg.add(var.set_no_target_delay_sensor(sens))
    if CONF_TRIGGER_COUNT in config:
        sens = await sensor.new_sensor(config[CONF_TRIGGER_COUNT])
        cg.add(var.set_trigger_count_sensor(sens))
    if CONF_SNR_THRESHOLD in config:
        sens = await sensor.new_sensor(config[CONF_SNR_THRESHOLD])
        cg.add(var.set_snr_threshold_sensor(sens))

    await setup_target(var, config, 0, "target_1")
    await setup_target(var, config, 1, "target_2")
    await setup_target(var, config, 2, "target_3")
