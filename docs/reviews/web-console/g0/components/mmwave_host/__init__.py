from pathlib import Path

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components.esp32 import add_idf_sdkconfig_option
from esphome.const import CONF_ID
from esphome.core import CoroPriority, coroutine_with_priority

CODEOWNERS = ["@zomco"]
DEPENDENCIES = ["logger"]

mmwave_host_ns = cg.esphome_ns.namespace("mmwave_host")
MwcpHost = mmwave_host_ns.class_("MwcpHost", cg.Component)
r60abd1_ns = cg.esphome_ns.namespace("r60abd1")
R60ABD1Component = r60abd1_ns.class_("R60ABD1Component")

CONF_RADAR_ID = "radar_id"
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(MwcpHost),
    cv.Optional(CONF_RADAR_ID): cv.use_id(R60ABD1Component),
}).extend(cv.COMPONENT_SCHEMA)


@coroutine_with_priority(CoroPriority.FINAL)
async def _own_usb_serial_jtag() -> None:
    add_idf_sdkconfig_option("CONFIG_ESP_CONSOLE_NONE", True)
    add_idf_sdkconfig_option("CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG", False)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    repo = Path(__file__).resolve().parents[6]
    cg.add_cxx_build_flag("-I" + (repo / "protocol" / "cpp").as_posix())
    cg.add_cxx_build_flag("-I" + (repo / "components" / "r60abd1").as_posix())
    if CONF_RADAR_ID in config:
        cg.add(var.set_radar(await cg.get_variable(config[CONF_RADAR_ID])))
    await _own_usb_serial_jtag()
