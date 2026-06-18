"""ESPHome component for Ai-Thinker RD03E 24 GHz precise ranging radar."""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart, sensor, binary_sensor
from esphome.const import (
    CONF_ID,
    DEVICE_CLASS_DISTANCE,
    DEVICE_CLASS_PRESENCE,
    STATE_CLASS_MEASUREMENT,
    UNIT_CENTIMETER,
    ICON_EMPTY,
)

# ── HACS / ESPHome 元数据 ─────────────────────────────────────────────────────

CODEOWNERS    = ["@zomco"]
DEPENDENCIES  = ["uart"]
AUTO_LOAD     = ["sensor", "binary_sensor"]

# ── C++ 命名空间 ──────────────────────────────────────────────────────────────

rd03e_ns         = cg.esphome_ns.namespace("rd03e")
RD03EComponent   = rd03e_ns.class_(
    "RD03EComponent", cg.Component, uart.UARTDevice
)

# ── 配置键常量 ────────────────────────────────────────────────────────────────

# 校准参数
CONF_RADAR_X        = "radar_x"
CONF_RADAR_Y        = "radar_y"
CONF_RADAR_Z        = "radar_z"
CONF_YAW            = "yaw"
CONF_PITCH          = "pitch"
CONF_ROLL           = "roll"
CONF_DISTANCE_MIN   = "distance_min"
CONF_DISTANCE_MAX   = "distance_max"

# 传感器
CONF_PRESENCE       = "presence"
CONF_MOTION_STATE   = "motion_state"
CONF_DISTANCE       = "distance"
CONF_ROOM_X         = "room_x"
CONF_ROOM_Y         = "room_y"
CONF_ROOM_Z         = "room_z"
CONF_IN_BOUNDARY    = "in_boundary"

# ── 组件完整 Schema ───────────────────────────────────────────────────────────

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(RD03EComponent),

            # ── 校准参数（编译期默认值；运行时可通过 number 实体覆盖）────────
            cv.Optional(CONF_RADAR_X,      default=0.0):   cv.float_,
            cv.Optional(CONF_RADAR_Y,      default=0.0):   cv.float_,
            cv.Optional(CONF_RADAR_Z,      default=240.0): cv.positive_float,
            cv.Optional(CONF_YAW,          default=0.0):   cv.float_range(-180, 180),
            cv.Optional(CONF_PITCH,        default=0.0):   cv.float_range(-90, 90),
            cv.Optional(CONF_ROLL,         default=0.0):   cv.float_range(-90, 90),
            cv.Optional(CONF_DISTANCE_MIN, default=0.0):   cv.float_,
            cv.Optional(CONF_DISTANCE_MAX, default=0.0):   cv.float_,

            # ── 存在与运动 ─────────────────────────────────────────────────────
            cv.Optional(CONF_PRESENCE): binary_sensor.binary_sensor_schema(
                device_class=DEVICE_CLASS_PRESENCE,
            ),
            cv.Optional(CONF_MOTION_STATE): sensor.sensor_schema(
                icon="mdi:motion-sensor",
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
            cv.Optional(CONF_DISTANCE): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                icon="mdi:ruler",
                accuracy_decimals=0,
                device_class=DEVICE_CLASS_DISTANCE,
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
                icon="mdi:ruler-square-compass",
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
    cg.add(var.set_distance_min(config[CONF_DISTANCE_MIN]))
    cg.add(var.set_distance_max(config[CONF_DISTANCE_MAX]))

    # sensor 传感器
    _sensor_map = {
        CONF_MOTION_STATE:  "set_motion_state_sensor",
        CONF_DISTANCE:      "set_distance_sensor",
        CONF_ROOM_X:        "set_room_x_sensor",
        CONF_ROOM_Y:        "set_room_y_sensor",
        CONF_ROOM_Z:        "set_room_z_sensor",
    }
    for conf_key, setter in _sensor_map.items():
        if conf_key in config:
            sens = await sensor.new_sensor(config[conf_key])
            cg.add(getattr(var, setter)(sens))

    # binary_sensor 传感器
    _binary_map = {
        CONF_PRESENCE:    "set_presence_sensor",
        CONF_IN_BOUNDARY: "set_in_boundary_sensor",
    }
    for conf_key, setter in _binary_map.items():
        if conf_key in config:
            sens = await binary_sensor.new_binary_sensor(config[conf_key])
            cg.add(getattr(var, setter)(sens))
