import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart, binary_sensor, sensor, text_sensor
from esphome.const import (
    CONF_ID,
    DEVICE_CLASS_DISTANCE,
    DEVICE_CLASS_PRESENCE,
    UNIT_CENTIMETER,
    UNIT_SECOND,
)

DEPENDENCIES = ["uart"]
AUTO_LOAD = ["binary_sensor", "sensor", "text_sensor"]

ld2410c_ns = cg.esphome_ns.namespace("ld2410c")
LD2410CComponent = ld2410c_ns.class_("LD2410CComponent", cg.Component, uart.UARTDevice)

CONF_PRESENCE = "presence"
CONF_TARGET_STATE = "target_state"
CONF_MOVING_DISTANCE = "moving_distance"
CONF_MOVING_ENERGY = "moving_energy"
CONF_STATIONARY_DISTANCE = "stationary_distance"
CONF_STATIONARY_ENERGY = "stationary_energy"
CONF_DETECTION_DISTANCE = "detection_distance"
CONF_MAX_DISTANCE = "max_distance"

# Engineering-mode extras the module appends after the gate energies
# (protocol table 15): the on-board photodiode and the OUT pin's own state.
CONF_LIGHT = "light"
CONF_OUT_PIN = "out_pin"

# Spatial projection entities
CONF_ROOM_X = "room_x"
CONF_ROOM_Y = "room_y"
CONF_ROOM_Z = "room_z"
CONF_IN_BOUNDARY = "in_boundary"

# Gate Energy Sensors
CONF_GATE_MOVE_ENERGY = "gate_move_energy"
CONF_GATE_STILL_ENERGY = "gate_still_energy"

# Configuration read-back. These publish what the radar answered to the
# queries the component issues, so a setting that did not take is visible
# rather than assumed.
CONF_FIRMWARE_VERSION = "firmware_version"
CONF_GATE_SENSITIVITY = "gate_sensitivity"
CONF_NOISE_FLOOR_STATUS = "noise_floor_status"
CONF_MAX_MOVING_GATE = "max_moving_gate"
CONF_MAX_STILL_GATE = "max_still_gate"
CONF_UNMANNED_DURATION = "unmanned_duration"
CONF_DISTANCE_RESOLUTION = "distance_resolution"

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

UNIT_METER_PER_GATE = "m"

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
            # 距离门外的目标默认不计入 presence，与其他型号一致
            cv.Optional(CONF_BOUNDARY_GATES_PRESENCE, default=True): cv.boolean,

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
            cv.Optional(CONF_MAX_DISTANCE): sensor.sensor_schema(
                unit_of_measurement=UNIT_CENTIMETER,
                device_class=DEVICE_CLASS_DISTANCE,
                accuracy_decimals=0,
            ),
            # 0–255 from the module's own photodiode. Not lux: the datasheet
            # gives no conversion, so it is published as the raw count.
            cv.Optional(CONF_LIGHT): sensor.sensor_schema(
                accuracy_decimals=0,
                icon="mdi:brightness-5",
            ),
            # What the module is driving on its OUT pin. Differs from
            # `presence` once the light-assisted control mode is enabled.
            cv.Optional(CONF_OUT_PIN): binary_sensor.binary_sensor_schema(
                icon="mdi:electric-switch",
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

            # Configuration read-back
            cv.Optional(CONF_FIRMWARE_VERSION): text_sensor.text_sensor_schema(
                icon="mdi:chip",
            ),
            cv.Optional(CONF_GATE_SENSITIVITY): text_sensor.text_sensor_schema(
                icon="mdi:tune-variant",
            ),
            cv.Optional(CONF_NOISE_FLOOR_STATUS): text_sensor.text_sensor_schema(
                icon="mdi:waveform",
            ),
            cv.Optional(CONF_MAX_MOVING_GATE): sensor.sensor_schema(
                accuracy_decimals=0,
            ),
            cv.Optional(CONF_MAX_STILL_GATE): sensor.sensor_schema(
                accuracy_decimals=0,
            ),
            cv.Optional(CONF_UNMANNED_DURATION): sensor.sensor_schema(
                unit_of_measurement=UNIT_SECOND,
                accuracy_decimals=0,
            ),
            cv.Optional(CONF_DISTANCE_RESOLUTION): sensor.sensor_schema(
                unit_of_measurement=UNIT_METER_PER_GATE,
                accuracy_decimals=2,
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
            for x in range(9)
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
    cg.add(var.set_boundary_gates_presence(config[CONF_BOUNDARY_GATES_PRESENCE]))

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
    if CONF_MAX_DISTANCE in config:
        sens = await sensor.new_sensor(config[CONF_MAX_DISTANCE])
        cg.add(var.set_max_distance_sensor(sens))
    if CONF_LIGHT in config:
        sens = await sensor.new_sensor(config[CONF_LIGHT])
        cg.add(var.set_light_sensor(sens))
    if CONF_OUT_PIN in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_OUT_PIN])
        cg.add(var.set_out_pin_sensor(sens))

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

    if CONF_FIRMWARE_VERSION in config:
        sens = await text_sensor.new_text_sensor(config[CONF_FIRMWARE_VERSION])
        cg.add(var.set_firmware_version_sensor(sens))
    if CONF_GATE_SENSITIVITY in config:
        sens = await text_sensor.new_text_sensor(config[CONF_GATE_SENSITIVITY])
        cg.add(var.set_gate_sensitivity_sensor(sens))
    if CONF_NOISE_FLOOR_STATUS in config:
        sens = await text_sensor.new_text_sensor(config[CONF_NOISE_FLOOR_STATUS])
        cg.add(var.set_noise_floor_status_sensor(sens))
    if CONF_MAX_MOVING_GATE in config:
        sens = await sensor.new_sensor(config[CONF_MAX_MOVING_GATE])
        cg.add(var.set_max_moving_gate_sensor(sens))
    if CONF_MAX_STILL_GATE in config:
        sens = await sensor.new_sensor(config[CONF_MAX_STILL_GATE])
        cg.add(var.set_max_still_gate_sensor(sens))
    if CONF_UNMANNED_DURATION in config:
        sens = await sensor.new_sensor(config[CONF_UNMANNED_DURATION])
        cg.add(var.set_unmanned_duration_sensor(sens))
    if CONF_DISTANCE_RESOLUTION in config:
        sens = await sensor.new_sensor(config[CONF_DISTANCE_RESOLUTION])
        cg.add(var.set_distance_resolution_sensor(sens))

    for x in range(9):
        if gate_conf := config.get(f"g{x}"):
            if move_config := gate_conf.get(CONF_GATE_MOVE_ENERGY):
                sens = await sensor.new_sensor(move_config)
                cg.add(var.set_gate_move_sensor(x, sens))
            if still_config := gate_conf.get(CONF_GATE_STILL_ENERGY):
                sens = await sensor.new_sensor(still_config)
                cg.add(var.set_gate_still_sensor(x, sens))
