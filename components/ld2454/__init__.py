"""ESPHome component for HLK-LD2454 24 GHz multi-target tracking radar."""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart, sensor, binary_sensor, button, switch, text_sensor
from esphome.const import (
    ENTITY_CATEGORY_CONFIG,
    CONF_ID,
    DEVICE_CLASS_DISTANCE,
    DEVICE_CLASS_PRESENCE,
    STATE_CLASS_MEASUREMENT,
    UNIT_CENTIMETER,
    ICON_EMPTY,
    CONF_FACTORY_RESET,
)

# ── HACS / ESPHome 元数据 ─────────────────────────────────────────────────────

CODEOWNERS    = ["@zomco"]
DEPENDENCIES  = ["uart"]
AUTO_LOAD     = ["sensor", "binary_sensor", "button", "switch", "text_sensor"]

# ── C++ 命名空间 ──────────────────────────────────────────────────────────────

ld2454_ns          = cg.esphome_ns.namespace("ld2454")
LD2454Component    = ld2454_ns.class_(
    "LD2454Component", cg.Component, uart.UARTDevice
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

# 全局传感器
CONF_PRESENCE       = "presence"
CONF_PRESENCE_TIMEOUT = "presence_timeout"
CONF_BOUNDARY_GATES_PRESENCE = "boundary_gates_presence"
CONF_TARGET_FRAME    = "target_frame"

# 控制实体
CONF_MULTI_TARGET   = "multi_target"
CONF_RESTART        = "restart"

# 自定义单位
UNIT_CM_PER_S       = "cm/s"
UNIT_DEGREES        = "°"

# ── 多边形顶点 Schema ─────────────────────────────────────────────────────────

POLYGON_POINT_SCHEMA = cv.Schema({
    cv.Required("x"): cv.float_,
    cv.Required("y"): cv.float_,
})

# ── 每目标传感器定义 ──────────────────────────────────────────────────────────
# (配置后缀, C++ setter 后缀, icon, unit, accuracy, device_class)

_TARGET_SENSOR_DEFS = [
    ("x",          "x",          "mdi:axis-x-arrow",         UNIT_CENTIMETER, 1, None),
    ("y",          "y",          "mdi:axis-y-arrow",         UNIT_CENTIMETER, 1, None),
    ("speed",      "speed",      "mdi:speedometer",          UNIT_CM_PER_S,   0, None),
    ("resolution", "resolution", "mdi:ruler",                UNIT_CENTIMETER, 1, None),
    ("distance",   "distance",   "mdi:map-marker-distance",  UNIT_CENTIMETER, 1, DEVICE_CLASS_DISTANCE),
    ("angle",      "angle",      "mdi:angle-acute",          UNIT_DEGREES,    1, None),
    ("room_x",     "room_x",     "mdi:map-marker-radius",    UNIT_CENTIMETER, 1, None),
    ("room_y",     "room_y",     "mdi:map-marker-radius",    UNIT_CENTIMETER, 1, None),
]

# (配置后缀, C++ setter 后缀, icon, device_class)
_TARGET_BINARY_SENSOR_DEFS = [
    ("active",      "active",      "mdi:radar",          None),
    ("in_boundary", "in_boundary", "mdi:vector-polygon", None),
]

# ── 动态构建每目标 Schema ─────────────────────────────────────────────────────

def _build_target_schema(n):
    """为目标 n (1-3) 生成所有传感器的 Schema 条目字典。"""
    entries = {}

    for suffix, _, icon, unit, accuracy, device_class in _TARGET_SENSOR_DEFS:
        key = f"target_{n}_{suffix}"
        schema_kwargs = {
            "icon": icon,
            "accuracy_decimals": accuracy,
            "state_class": STATE_CLASS_MEASUREMENT,
        }
        if unit:
            schema_kwargs["unit_of_measurement"] = unit
        if device_class:
            schema_kwargs["device_class"] = device_class
        entries[cv.Optional(key)] = sensor.sensor_schema(**schema_kwargs)

    for suffix, _, icon, device_class in _TARGET_BINARY_SENSOR_DEFS:
        key = f"target_{n}_{suffix}"
        schema_kwargs = {"icon": icon}
        if device_class:
            schema_kwargs["device_class"] = device_class
        entries[cv.Optional(key)] = binary_sensor.binary_sensor_schema(**schema_kwargs)

    return entries


# ── 组件完整 Schema ───────────────────────────────────────────────────────────

_target_entries = {}
for _n in range(1, 4):
    _target_entries.update(_build_target_schema(_n))

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(LD2454Component),

            # ── 校准参数 ──────────────────────────────────────────────────
            cv.Optional(CONF_RADAR_X,  default=0.0):   cv.float_,
            cv.Optional(CONF_RADAR_Y,  default=0.0):   cv.float_,
            cv.Optional(CONF_RADAR_Z,  default=150.0): cv.positive_float,
            cv.Optional(CONF_YAW,      default=0.0):   cv.float_range(-180, 180),
            cv.Optional(CONF_PITCH,    default=0.0):   cv.float_range(-90, 90),
            cv.Optional(CONF_ROLL,     default=0.0):   cv.float_range(-90, 90),
            cv.Optional(CONF_POLYGON,  default=[]):
                cv.ensure_list(POLYGON_POINT_SCHEMA),

            # ── 全局存在检测 ──────────────────────────────────────────────
            cv.Optional(CONF_PRESENCE): binary_sensor.binary_sensor_schema(
                device_class=DEVICE_CLASS_PRESENCE,
            ),
            cv.Optional(CONF_TARGET_FRAME): text_sensor.text_sensor_schema(
                icon="mdi:radar",
            ),
            cv.Optional(CONF_PRESENCE_TIMEOUT, default="5s"): cv.positive_time_period_milliseconds,
            # 边界外的目标（隔墙鬼影）默认不计入 presence
            cv.Optional(CONF_BOUNDARY_GATES_PRESENCE, default=True): cv.boolean,

            # ── 控制实体 ──────────────────────────────────────────────────
            cv.Optional(CONF_MULTI_TARGET): switch.switch_schema(
                ld2454_ns.class_("LD2454Switch", switch.Switch),
                icon="mdi:target-account",
            ),
            cv.Optional(CONF_FACTORY_RESET): button.button_schema(
                ld2454_ns.class_("LD2454Button", button.Button),
                icon="mdi:restart-alert",
                entity_category=ENTITY_CATEGORY_CONFIG,
            ),
            cv.Optional(CONF_RESTART): button.button_schema(
                ld2454_ns.class_("LD2454Button", button.Button),
                icon="mdi:restart",
                entity_category=ENTITY_CATEGORY_CONFIG,
            ),

            # ── 每目标传感器（动态生成） ──────────────────────────────────
            **_target_entries,
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

    # 校准参数
    cg.add(var.set_radar_x(config[CONF_RADAR_X]))
    cg.add(var.set_radar_y(config[CONF_RADAR_Y]))
    cg.add(var.set_radar_z(config[CONF_RADAR_Z]))
    cg.add(var.set_yaw(config[CONF_YAW]))
    cg.add(var.set_pitch(config[CONF_PITCH]))
    cg.add(var.set_roll(config[CONF_ROLL]))

    # 多边形顶点
    for pt in config.get(CONF_POLYGON, []):
        cg.add(var.add_polygon_point(pt["x"], pt["y"]))

    # 全局 binary_sensor
    if CONF_PRESENCE in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_PRESENCE])
        cg.add(var.set_presence_sensor(sens))

    if CONF_TARGET_FRAME in config:
        sens = await text_sensor.new_text_sensor(config[CONF_TARGET_FRAME])
        cg.add(var.set_target_frame_sensor(sens))

    # 每目标 sensor
    for n in range(1, 4):
        for suffix, setter_suffix, *_ in _TARGET_SENSOR_DEFS:
            key = f"target_{n}_{suffix}"
            if key in config:
                sens = await sensor.new_sensor(config[key])
                setter = f"set_target_{n}_{setter_suffix}_sensor"
                cg.add(getattr(var, setter)(sens))

        for suffix, setter_suffix, *_ in _TARGET_BINARY_SENSOR_DEFS:
            key = f"target_{n}_{suffix}"
            if key in config:
                sens = await binary_sensor.new_binary_sensor(config[key])
                setter = f"set_target_{n}_{setter_suffix}_sensor"
                cg.add(getattr(var, setter)(sens))

    # 全局超时设置
    cg.add(var.set_presence_timeout(config[CONF_PRESENCE_TIMEOUT]))
    cg.add(var.set_boundary_gates_presence(config[CONF_BOUNDARY_GATES_PRESENCE]))

    # 控制实体
    if CONF_MULTI_TARGET in config:
        sw = cg.new_Pvariable(config[CONF_MULTI_TARGET][CONF_ID])
        await switch.register_switch(sw, config[CONF_MULTI_TARGET])
        cg.add(sw.set_parent(var))
        cg.add(sw.set_switch_type(cg.RawExpression("esphome::ld2454::LD2454Switch::MULTI_TARGET")))
        cg.add(var.set_multi_target_switch(sw))


    if CONF_FACTORY_RESET in config:
        btn = cg.new_Pvariable(config[CONF_FACTORY_RESET][CONF_ID])
        await button.register_button(btn, config[CONF_FACTORY_RESET])
        cg.add(btn.set_parent(var))
        cg.add(btn.set_button_type(cg.RawExpression("esphome::ld2454::LD2454Button::FACTORY_RESET")))

    if CONF_RESTART in config:
        btn = cg.new_Pvariable(config[CONF_RESTART][CONF_ID])
        await button.register_button(btn, config[CONF_RESTART])
        cg.add(btn.set_parent(var))
        cg.add(btn.set_button_type(cg.RawExpression("esphome::ld2454::LD2454Button::RESTART")))
