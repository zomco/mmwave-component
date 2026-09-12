"""Host regression tests for the actual RD03E C++ UART parser (requires g++)."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RD03EProtocolTest(unittest.TestCase):
    def test_wire_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            stubs = {
                "core/component.h": """
#pragma once
#include <cstdint>
#include <string>
namespace esphome {
inline uint32_t now = 1000;
inline uint32_t millis() { return now; }
namespace setup_priority { constexpr float DATA = 600; }
class Component { public: virtual void setup() {} virtual void loop() {}
virtual void dump_config() {} virtual float get_setup_priority() const { return 0; } };
}
""",
                "core/log.h": """
#pragma once
#include <cstdio>
#include <string>
inline std::string logs;
#define ESP_LOGD(tag, fmt, ...) do { char b[1024]; snprintf(b, sizeof(b), fmt, ##__VA_ARGS__); logs += std::string(b) + "\\n"; } while (0)
#define ESP_LOGI ESP_LOGD
#define ESP_LOGW ESP_LOGD
#define ESP_LOGE ESP_LOGD
#define ESP_LOGV ESP_LOGD
#define ESP_LOGCONFIG ESP_LOGD
#define LOG_SENSOR(...)
#define LOG_BINARY_SENSOR(...)
""",
                "core/helpers.h": """
#pragma once
#include <string>
#include <cstdint>
namespace esphome { inline std::string format_hex_pretty(const uint8_t *, size_t) { return "hex"; } }
""",
                "components/uart/uart.h": """
#pragma once
#include <cstdint>
#include <cstddef>
namespace esphome::uart { class UARTDevice { public:
int available() { return 0; } uint8_t read() { return 0; }
void write_byte(uint8_t) {} void write_array(const uint8_t *, size_t) {} }; }
""",
                "components/sensor/sensor.h": """
#pragma once
namespace esphome::sensor { class Sensor { public: float state = -1;
void publish_state(float v) { state = v; } }; }
""",
                "components/binary_sensor/binary_sensor.h": """
#pragma once
namespace esphome::binary_sensor { class BinarySensor { public: bool state = false;
void publish_state(bool v) { state = v; } }; }
""",
            }
            for name, content in stubs.items():
                path = root / "esphome" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            source = root / "test.cpp"
            source.write_text(r'''
#include "rd03e.h"
#include <cassert>
#include <vector>
using namespace esphome;
class Radar : public rd03e::RD03EComponent {
 public:
 void feed(const std::vector<uint8_t> &bytes) { for (auto b : bytes) process_byte_(b); }
 void ack(std::vector<uint8_t> payload) {
   std::vector<uint8_t> bytes{0xfd,0xfc,0xfb,0xfa,static_cast<uint8_t>(payload.size()),0};
   bytes.insert(bytes.end(),payload.begin(),payload.end());
   bytes.insert(bytes.end(),{4,3,2,1}); feed(bytes);
 }
};
int main() {
 Radar r; sensor::Sensor distance, motion; binary_sensor::BinarySensor presence;
 r.set_target_timeout(0);
 r.set_distance_sensor(&distance); r.set_motion_state_sensor(&motion); r.set_presence_sensor(&presence);
 r.feed({0xaa,0xaa,1,0x2c,1,0x55,0x55});
 assert(distance.state == 300 && motion.state == 1 && presence.state);
 now += 1000; r.feed({0xaa,0xaa,2,90,0,0x55,0x55});
 assert(distance.state == 90 && motion.state == 2 && presence.state);
 now += 1000; r.feed({0xaa,0xaa,0,0,0,0x55,0x55});
 assert(distance.state == 0 && motion.state == 0 && !presence.state);

 // Refresh detection on frames hidden by the publication throttle.
 r.set_target_timeout(3000); now = 10000;
 r.feed({0xaa,0xaa,1,150,0,0x55,0x55});
 now = 10950; r.feed({0xaa,0xaa,1,151,0,0x55,0x55});
 now = 11000; r.feed({0xaa,0xaa,0,0,0,0x55,0x55});
 assert(presence.state && distance.state == 151 && motion.state == 1);
 now = 13000; r.feed({0xaa,0xaa,0,0,0,0x55,0x55});
 assert(presence.state && distance.state == 151);
 now = 14000; r.feed({0xaa,0xaa,0,0,0,0x55,0x55});
 assert(!presence.state && distance.state == 0 && motion.state == 0);
 // Presence without a fresh range must not reuse a position indefinitely.
 now = 15000; r.feed({0xaa,0xaa,2,0,0,0x55,0x55});
 assert(presence.state && distance.state == 0 && motion.state == 2);
 // UART loss clears held state; the next empty frame cannot resurrect it.
 now = 16000; r.loop();
 assert(!presence.state && distance.state == 0 && motion.state == 0);
 now = 17000; r.feed({0xaa,0xaa,0,0,0,0x55,0x55});
 assert(!presence.state);
 logs.clear(); r.ack({0xff,1,0,0,1,0,0,0});
 assert(logs.find("Enable config ACK") != std::string::npos);
 logs.clear(); r.ack({0,1,4,0,2,0,3,0});
 assert(logs.find("Firmware version: 4.2.3") != std::string::npos);
 for (bool separate_status : {false,true}) {
   std::vector<uint8_t> p{0x73,1};
   if (separate_status) p.insert(p.end(),{0,0});
   p.insert(p.end(),{0xcd,2,30,0,0xa9,1,30,0,20,0});
   p.resize(separate_status ? 54 : 52);
   logs.clear(); r.ack(p);
   assert(logs.find("motion=[30-717] micro=[30-425] vacancy=20") != std::string::npos);
 }
 logs.clear(); std::vector<uint8_t> failed(54); failed[0]=0x73; failed[1]=1; failed[2]=1;
 r.ack(failed); assert(logs.find("Read parameters failed") != std::string::npos);
 assert(logs.find("Params:") == std::string::npos);
 // A truncated ACK must not read beyond the received fields.
 logs.clear(); r.ack({0x73,1,0,0}); assert(logs.find("Params:") == std::string::npos);
}
''')
            binary = root / "test"
            component = ROOT / "components" / "rd03e"
            subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-I", str(root),
                            "-I", str(component), str(source), str(component / "rd03e.cpp"),
                            "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
