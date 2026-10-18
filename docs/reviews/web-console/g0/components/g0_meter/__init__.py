from pathlib import Path

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID

CODEOWNERS = ["@zomco"]
DEPENDENCIES = ["logger"]

g0_meter_ns = cg.esphome_ns.namespace("g0_meter")
G0MeterComponent = g0_meter_ns.class_("G0MeterComponent", cg.Component)
r60abd1_ns = cg.esphome_ns.namespace("r60abd1")
R60ABD1Component = r60abd1_ns.class_("R60ABD1Component")

CONF_RADAR_ID = "radar_id"
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(G0MeterComponent),
    cv.Optional(CONF_RADAR_ID): cv.use_id(R60ABD1Component),
}).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    repo = Path(__file__).resolve().parents[6]
    host = Path(__file__).resolve().parents[1] / "mmwave_host"
    cg.add_cxx_build_flag("-I" + host.as_posix())
    cg.add_cxx_build_flag("-I" + (repo / "components" / "r60abd1").as_posix())
    if CONF_RADAR_ID in config:
        cg.add(var.set_radar(await cg.get_variable(config[CONF_RADAR_ID])))
