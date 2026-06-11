"""ESPHome component for MicRadar R60ABD1 60 GHz breathing/sleep radar."""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart, sensor, binary_sensor, text_sensor
from esphome.const import (
    CONF_ID,
    DEVICE_CLASS_DISTANCE,
    DEVICE_CLASS_PRESENCE,
    STATE_CLASS_MEASUREMENT,
    UNIT_CENTIMETER,
    UNIT_BEATS_PER_MINUTE,
    ICON_EMPTY,
)

# ── HACS / ESPHome 元数据 ─────────────────────────────────────────────────────

CODEOWNERS    = ["@zomco"]
DEPENDENCIES  = ["uart"]
AUTO_LOAD     = ["sensor", "binary_sensor", "text_sensor"]

# ── C++ 命名空间 ──────────────────────────────────────────────────────────────

r60abd1_ns          = cg.esphome_ns.namespace("r60abd1")
R60ABD1Component    = r60abd1_ns.class_(
    "R60ABD1Component", cg.Component, uart.UARTDevice
)

# ── 配置键常量 ────────────────────────────────────────────────────────────────

# 校准参数
CONF_RADAR_X        = "radar_x"
CONF_RADAR_Y        = "radar_y"
CONF_RADAR_Z        = "radar_z"
CONF_YAW            = "yaw"
CONF_PITCH          = "pitch"
CONF_ROLL           = "roll"
CONF_POLYGON        = "polygon"

# 传感器
CONF_PRESENCE           = "presence"
CONF_MOTION_STATE       = "motion_state"
CONF_BODY_MOVEMENT      = "body_movement"
CONF_BODY_DISTANCE      = "body_distance"
CONF_RAW_X              = "raw_x"
CONF_RAW_Y              = "raw_y"
CONF_RAW_Z              = "raw_z"
CONF_ROOM_X             = "room_x"
CONF_ROOM_Y             = "room_y"
CONF_ROOM_Z             = "room_z"
CONF_IN_BOUNDARY        = "in_boundary"
CONF_BREATH_VALUE       = "breath_value"
CONF_BREATH_STATE       = "breath_state"
CONF_HEART_RATE         = "heart_rate"
CONF_IN_BED             = "in_bed"
CONF_SLEEP_STATE        = "sleep_state"
CONF_AWAKE_DURATION     = "awake_duration"
CONF_LIGHT_SLEEP_DUR    = "light_sleep_duration"
CONF_DEEP_SLEEP_DUR     = "deep_sleep_duration"
CONF_SLEEP_SCORE        = "sleep_score"
CONF_SLEEP_QUALITY      = "sleep_quality"

# ── 多边形顶点 Schema ─────────────────────────────────────────────────────────

POLYGON_POINT_SCHEMA = cv.Schema({
    cv.Required("x"): cv.float_,
    cv.Required("y"): cv.float_,
})

# ── 组件完整 Schema ───────────────────────────────────────────────────────────

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(R60ABD1Component),

            # ── 校准参数（编译期默认值；运行时可通过 number 实体覆盖）────────
            cv.Optional(CONF_RADAR_X,      default=0.0):   cv.float_,
            cv.Optional(CONF_RADAR_Y,      default=0.0):   cv.float_,
            cv.Optional(CONF_RADAR_Z,      default=220.0): cv.positive_float,
            cv.Optional(CONF_YAW,          default=0.0):   cv.float_range(-180, 180),
            cv.Optional(CONF_PITCH,        default=0.0):   cv.float_range(-90, 90),
            cv.Optional(CONF_ROLL,         default=0.0):   cv.float_range(-90, 90),
            cv.Optional(CONF_POLYGON,      default=[]):
                cv.ensure_list(POLYGON_POINT_SCHEMA),

            # ── 存在与运动 ─────────────────────────────────────────────────────
            cv.Optional(CONF_PRESENCE): binary_sensor.binary_sensor_schema(
                device_class=DEVICE_CLASS_PRESENCE,
            ),
            cv.Optional(CONF_MOTION_STATE): sensor.sensor_schema(
                icon="mdi:motion-sensor",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_BODY_MOVEMENT): sensor.sensor_schema(
                icon="mdi:run-fast",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_BODY_DISTANCE): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                icon="mdi:ruler",
                accuracy_decimals=0,
                device_class=DEVICE_CLASS_DISTANCE,
                state_class=STATE_CLASS_MEASUREMENT,
            ),

            # ── 原始坐标（雷达局部坐标系）────────────────────────────────────
            cv.Optional(CONF_RAW_X): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                icon="mdi:axis-x-arrow",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_RAW_Y): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                icon="mdi:axis-y-arrow",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_RAW_Z): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                icon="mdi:axis-z-arrow",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),

            # ── 变换后坐标（房间坐标系）──────────────────────────────────────
            cv.Optional(CONF_ROOM_X): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                icon="mdi:map-marker-radius",
                accuracy_decimals=1,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_ROOM_Y): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                icon="mdi:map-marker-radius",
                accuracy_decimals=1,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_ROOM_Z): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                icon="mdi:human-male-height",
                accuracy_decimals=1,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_IN_BOUNDARY): binary_sensor.binary_sensor_schema(
                icon="mdi:vector-polygon",
            ),

            # ── 呼吸 ──────────────────────────────────────────────────────────
            cv.Optional(CONF_BREATH_VALUE): sensor.sensor_schema(
                unit_of_measurement="次/min",
                icon="mdi:lungs",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_BREATH_STATE): text_sensor.text_sensor_schema(
                icon="mdi:lungs",
            ),

            # ── 心率 ──────────────────────────────────────────────────────────
            cv.Optional(CONF_HEART_RATE): sensor.sensor_schema(
                unit_of_measurement=UNIT_BEATS_PER_MINUTE,
                icon="mdi:heart-pulse",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),

            # ── 睡眠监测 ──────────────────────────────────────────────────────
            cv.Optional(CONF_IN_BED): binary_sensor.binary_sensor_schema(
                icon="mdi:bed",
            ),
            cv.Optional(CONF_SLEEP_STATE): text_sensor.text_sensor_schema(
                icon="mdi:sleep",
            ),
            cv.Optional(CONF_AWAKE_DURATION): sensor.sensor_schema(
                unit_of_measurement="min",
                icon="mdi:timer-outline",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_LIGHT_SLEEP_DUR): sensor.sensor_schema(
                unit_of_measurement="min",
                icon="mdi:sleep",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_DEEP_SLEEP_DUR): sensor.sensor_schema(
                unit_of_measurement="min",
                icon="mdi:sleep",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_SLEEP_SCORE): sensor.sensor_schema(
                icon="mdi:star-circle",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_SLEEP_QUALITY): text_sensor.text_sensor_schema(
                icon="mdi:star-circle-outline",
            ),
        }
    )
    .extend(uart.UART_DEVICE_SCHEMA)
    .extend(cv.COMPONENT_SCHEMA)
)

# ── 代码生成 ──────────────────────────────────────────────────────────────────

async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)

    # 校准参数（编译期写入）
    cg.add(var.set_radar_x(config[CONF_RADAR_X]))
    cg.add(var.set_radar_y(config[CONF_RADAR_Y]))
    cg.add(var.set_radar_z(config[CONF_RADAR_Z]))
    cg.add(var.set_yaw(config[CONF_YAW]))
    cg.add(var.set_pitch(config[CONF_PITCH]))
    cg.add(var.set_roll(config[CONF_ROLL]))

    # 多边形：逐点追加（避免传递 std::vector，与 ESPHome codegen 兼容）
    for pt in config.get(CONF_POLYGON, []):
        cg.add(var.add_polygon_point(pt["x"], pt["y"]))

    # sensor 传感器
    _sensor_map = {
        CONF_MOTION_STATE:    "set_motion_sensor",
        CONF_BODY_MOVEMENT:   "set_body_movement_sensor",
        CONF_BODY_DISTANCE:   "set_body_distance_sensor",
        CONF_RAW_X:           "set_raw_x_sensor",
        CONF_RAW_Y:           "set_raw_y_sensor",
        CONF_RAW_Z:           "set_raw_z_sensor",
        CONF_ROOM_X:          "set_room_x_sensor",
        CONF_ROOM_Y:          "set_room_y_sensor",
        CONF_ROOM_Z:          "set_room_z_sensor",
        CONF_BREATH_VALUE:    "set_breath_value_sensor",
        CONF_HEART_RATE:      "set_heart_rate_sensor",
        CONF_AWAKE_DURATION:  "set_awake_duration_sensor",
        CONF_LIGHT_SLEEP_DUR: "set_light_sleep_duration_sensor",
        CONF_DEEP_SLEEP_DUR:  "set_deep_sleep_duration_sensor",
        CONF_SLEEP_SCORE:     "set_sleep_score_sensor",
    }
    for conf_key, setter in _sensor_map.items():
        if conf_key in config:
            sens = await sensor.new_sensor(config[conf_key])
            cg.add(getattr(var, setter)(sens))

    # binary_sensor 传感器
    _binary_map = {
        CONF_PRESENCE:    "set_presence_sensor",
        CONF_IN_BOUNDARY: "set_in_boundary_sensor",
        CONF_IN_BED:      "set_in_bed_sensor",
    }
    for conf_key, setter in _binary_map.items():
        if conf_key in config:
            sens = await binary_sensor.new_binary_sensor(config[conf_key])
            cg.add(getattr(var, setter)(sens))

    # text_sensor 传感器
    _text_map = {
        CONF_BREATH_STATE:  "set_breath_state_sensor",
        CONF_SLEEP_STATE:   "set_sleep_state_sensor",
        CONF_SLEEP_QUALITY: "set_sleep_quality_sensor",
    }
    for conf_key, setter in _text_map.items():
        if conf_key in config:
            sens = await text_sensor.new_text_sensor(config[conf_key])
            cg.add(getattr(var, setter)(sens))