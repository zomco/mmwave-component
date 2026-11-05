import subprocess
from pathlib import Path

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import wifi
from esphome.components.esp32 import add_idf_sdkconfig_option
from esphome.const import CONF_ID
from esphome.core import CoroPriority, coroutine_with_priority

CODEOWNERS = ["@zomco"]
DEPENDENCIES = ["logger", "wifi"]

mmwave_host_ns = cg.esphome_ns.namespace("mmwave_host")
MwcpHost = mmwave_host_ns.class_("MwcpHost", cg.Component)
r60abd1_ns = cg.esphome_ns.namespace("r60abd1")
R60ABD1Component = r60abd1_ns.class_("R60ABD1Component")

CONF_RADAR_ID = "radar_id"
# Diagnostic-only: a synthetic LOG stream for stress soaks (r2 review R2-A).
# 0 (the default) compiles to nothing; production profiles never set it.
CONF_LOG_PRESSURE_HZ = "log_pressure_hz"
CONF_FIRMWARE_VERSION = "firmware_version"
CONF_RELEASE_CHANNEL = "release_channel"
CONF_BUILD_PROFILE = "build_profile"
CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(MwcpHost),
        cv.Required(CONF_RADAR_ID): cv.use_id(R60ABD1Component),
        cv.Optional(CONF_LOG_PRESSURE_HZ, default=0): cv.int_range(min=0, max=20),
        # Host tests keep the historical identity. A factory build reports
        # ESPHOME_PROJECT_VERSION instead, so a stamped version: line wins.
        cv.Optional(CONF_FIRMWARE_VERSION, default="mwcp-host"): cv.All(cv.string, cv.Length(min=1, max=64)),
        cv.Optional(CONF_RELEASE_CHANNEL, default="development"): cv.one_of(
            "alpha", "beta", "development", lower=True
        ),
        cv.Optional(CONF_BUILD_PROFILE, default="host-enabled"): cv.All(cv.string, cv.Length(min=1, max=32)),
    }
).extend(cv.COMPONENT_SCHEMA)


def _cxx_string(name, value):
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    cg.add_cxx_build_flag(f'-D{name}=\\"{escaped}\\"')


@coroutine_with_priority(CoroPriority.FINAL)
async def _own_usb_serial_jtag() -> None:
    add_idf_sdkconfig_option("CONFIG_ESP_CONSOLE_NONE", True)
    add_idf_sdkconfig_option("CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG", False)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    # A scan is started only when ESPHome can prove which scan a completion
    # belongs to: the pinned patch adds start_scan_for_component() and a
    # completion listener that echoes the request's generation. On stock ESPHome
    # none of that exists, and wifi.scan fails with UNSUPPORTED rather than
    # guessing which scan finished.
    if hasattr(wifi, "request_wifi_scan_completion_listener"):
        wifi.request_wifi_scan_completion_listener()
        cg.add_define("MWCP_WIFI_SCAN_OWNERSHIP")
    # Keeping the results disables ESPHome's configured-network filter, so the
    # UI sees every AP.
    wifi.request_wifi_scan_results()
    # Pauses ESPHome's post-connect roaming scans while an owned scan is active,
    # so the radio is never handed a second scan mid-request.
    wifi.enable_runtime_roaming_suppression()
    repo = Path(__file__).resolve().parents[2]
    cg.add_cxx_build_flag("-I" + (repo / "protocol" / "cpp").as_posix())
    cg.add_cxx_build_flag("-I" + (repo / "components" / "mmwave_host").as_posix())
    cg.add_cxx_build_flag("-I" + (repo / "components" / "r60abd1").as_posix())
    cg.add(var.set_radar(await cg.get_variable(config[CONF_RADAR_ID])))
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(repo), text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        sha = ""
    if sha:
        # HEAD only. A dirty worktree can share this SHA, so the candidate
        # report records the diff separately.
        _cxx_string("MWCP_GIT_SHA", sha)
    _cxx_string("MWCP_FIRMWARE_VERSION", config[CONF_FIRMWARE_VERSION])
    _cxx_string("MWCP_RELEASE_CHANNEL", config[CONF_RELEASE_CHANNEL])
    _cxx_string("MWCP_BUILD_PROFILE", config[CONF_BUILD_PROFILE])
    pressure_hz = config[CONF_LOG_PRESSURE_HZ]
    if pressure_hz:
        # Diagnostic stress profile only; see CONF_LOG_PRESSURE_HZ above.
        cg.add_cxx_build_flag(f"-DMWCP_LOG_PRESSURE_HZ={int(pressure_hz)}")
    await _own_usb_serial_jtag()
