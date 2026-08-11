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

# 安装校准参数（房间坐标系）
CONF_RADAR_X = "radar_x"
CONF_RADAR_Y = "radar_y"
CONF_RADAR_Z = "radar_z"
CONF_YAW = "yaw"
CONF_PITCH = "pitch"
CONF_ROLL = "roll"
CONF_DISTANCE_MIN = "distance_min"
CONF_DISTANCE_MAX = "distance_max"
CONF_BOUNDARY_GATES_PRESENCE = "boundary_gates_presence"

# 变换后实体
CONF_ROOM_X = "room_x"
CONF_ROOM_Y = "room_y"
CONF_ROOM_Z = "room_z"
CONF_IN_BOUNDARY = "in_boundary"

_ROOM_SENSOR_SCHEMA = sensor.sensor_schema(
    unit_of_measurement=UNIT_CENTIMETER,
    device_class=DEVICE_CLASS_DISTANCE,
    state_class=STATE_CLASS_MEASUREMENT,
    accuracy_decimals=1,
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(LD2411SComponent),
        # ── 安装校准 ────────────────────────────────────────────────────
        cv.Optional(CONF_RADAR_X, default=0.0): cv.float_,
        cv.Optional(CONF_RADAR_Y, default=0.0): cv.float_,
        cv.Optional(CONF_RADAR_Z, default=240.0): cv.float_,
        cv.Optional(CONF_YAW, default=0.0): cv.float_range(min=-180.0, max=180.0),
        cv.Optional(CONF_PITCH, default=0.0): cv.float_range(min=-90.0, max=90.0),
        cv.Optional(CONF_ROLL, default=0.0): cv.float_range(min=-90.0, max=90.0),
        # 1-D 雷达以距离门作为边界；0 = 不过滤
        cv.Optional(CONF_DISTANCE_MIN, default=0.0): cv.float_,
        cv.Optional(CONF_DISTANCE_MAX, default=0.0): cv.float_,
        # 边界外的目标默认不计入 presence
        cv.Optional(CONF_BOUNDARY_GATES_PRESENCE, default=True): cv.boolean,
        # ── 变换后实体 ──────────────────────────────────────────────────
        cv.Optional(CONF_ROOM_X): _ROOM_SENSOR_SCHEMA,
        cv.Optional(CONF_ROOM_Y): _ROOM_SENSOR_SCHEMA,
        cv.Optional(CONF_ROOM_Z): _ROOM_SENSOR_SCHEMA,
        cv.Optional(CONF_IN_BOUNDARY): binary_sensor.binary_sensor_schema(),
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

    # 安装校准参数
    cg.add(var.set_radar_x(config[CONF_RADAR_X]))
    cg.add(var.set_radar_y(config[CONF_RADAR_Y]))
    cg.add(var.set_radar_z(config[CONF_RADAR_Z]))
    cg.add(var.set_yaw(config[CONF_YAW]))
    cg.add(var.set_pitch(config[CONF_PITCH]))
    cg.add(var.set_roll(config[CONF_ROLL]))
    cg.add(var.set_distance_min(config[CONF_DISTANCE_MIN]))
    cg.add(var.set_distance_max(config[CONF_DISTANCE_MAX]))
    cg.add(var.set_boundary_gates_presence(config[CONF_BOUNDARY_GATES_PRESENCE]))

    for key, setter in (
        (CONF_ROOM_X, "set_room_x_sensor"),
        (CONF_ROOM_Y, "set_room_y_sensor"),
        (CONF_ROOM_Z, "set_room_z_sensor"),
    ):
        if key in config:
            sens = await sensor.new_sensor(config[key])
            cg.add(getattr(var, setter)(sens))

    if CONF_IN_BOUNDARY in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_IN_BOUNDARY])
        cg.add(var.set_in_boundary_sensor(sens))

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
