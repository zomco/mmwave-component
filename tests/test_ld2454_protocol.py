"""Host regression tests for the actual LD2454 C++ UART parser (requires g++)."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class LD2454ProtocolTest(unittest.TestCase):
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
#include <vector>
namespace esphome::uart { class UARTDevice { public:
int available() { return 0; } uint8_t read() { return 0; }
std::vector<uint8_t> tx; void write_byte(uint8_t b) { tx.push_back(b); } void write_array(const uint8_t *p, size_t n) { tx.insert(tx.end(),p,p+n); } }; }
""",
                "components/sensor/sensor.h": """
#pragma once
namespace esphome::sensor { class Sensor { public: float state = -1;
void publish_state(float v) { state = v; } }; }
""",
                "components/binary_sensor/binary_sensor.h": """
#pragma once
namespace esphome::binary_sensor { class BinarySensor { public: bool state = false;
bool has_state() const { return true; } void publish_state(bool v) { state = v; } }; }
""",
            }
            stubs["components/button/button.h"] = "namespace esphome::button { class Button { public: virtual void press_action() {} }; }"
            stubs["components/switch/switch.h"] = "namespace esphome::switch_ { class Switch { public: bool state=false; virtual void write_state(bool) {} void publish_state(bool v) { state=v; } }; }"
            stubs["components/text_sensor/text_sensor.h"] = "namespace esphome::text_sensor { class TextSensor { public: void publish_state(const char*) {} }; }"
            for name, content in stubs.items():
                path = root / "esphome" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            source = root / "test.cpp"
            source.write_text(r'''
#include "ld2454.h"
#include <cassert>
using namespace esphome;
class Radar : public ld2454::LD2454Component {
 public:
 void ack(uint16_t word, uint16_t status=0, bool truncated=false) {
   std::vector<uint8_t> bytes{0xfd,0xfc,0xfb,0xfa,static_cast<uint8_t>(truncated?2:4),0,
       static_cast<uint8_t>(word),static_cast<uint8_t>(word>>8)};
   if(!truncated) bytes.insert(bytes.end(),{static_cast<uint8_t>(status),static_cast<uint8_t>(status>>8)});
   bytes.insert(bytes.end(),{4,3,2,1});
   for(auto b:bytes) process_byte_(b);
 }
 void timeout() { check_config_timeout_(now); }
 uint16_t sent() { assert(tx.size()>=12); auto cmd=tx[6]|(tx[7]<<8); tx.clear(); return cmd; }
};
int main() {
 Radar r; switch_::Switch sw; r.set_multi_target_switch(&sw);
 r.set_multi_target_mode(true); assert(r.sent()==0xff); assert(!sw.state);
 // A slow enable ACK must gate the command, without a blocking delay.
 now+=500; r.timeout(); assert(r.tx.empty());
 r.ack(0x1fe); assert(r.tx.empty());
 r.ack(0x1ff,0,true); assert(r.tx.empty());
 r.ack(0x1ff); assert(r.sent()==0x90); assert(!sw.state);
 r.ack(0x1ff); assert(r.tx.empty());
 r.ack(0x190); assert(sw.state); assert(r.sent()==0xfe);
 r.ack(0x1fe); assert(sw.state);
 r.set_multi_target_mode(false); assert(r.sent()==0xff);
 r.ack(0x1ff); assert(r.sent()==0x80);
 r.ack(0x180); assert(!sw.state); assert(r.sent()==0xfe); r.ack(0x1fe);
 // Failed mode ACK cannot claim that the requested mode was enabled.
 r.set_multi_target_mode(true); r.sent(); r.ack(0x1ff); r.sent();
 r.ack(0x190,1); assert(!sw.state); assert(r.sent()==0xfe); r.ack(0x1fe);
 // Failed enable does not send the target command.
 r.set_multi_target_mode(true); r.sent(); r.ack(0x1ff,1);
 assert(r.sent()==0xfe); r.ack(0x1fe);
 // Missing ACK triggers one cleanup command, then returns to idle.
 r.set_multi_target_mode(true); r.sent(); now+=1500; r.timeout();
 assert(r.sent()==0xfe); now+=1500; r.timeout(); assert(r.tx.empty());
 r.set_multi_target_mode(true); assert(r.sent()==0xff);
 // A second request cannot corrupt the transaction already in flight.
 r.set_multi_target_mode(false); assert(r.tx.empty());
 r.ack(0x1ff); assert(r.sent()==0x90); r.ack(0x190); assert(sw.state); r.sent();r.ack(0x1fe);
 // Buffer caller-owned payload until enable ACK, then send the original bytes.
 uint8_t payload[]{7,0}; r.send_config_cmd(0xa1,payload,2);r.sent();payload[0]=1;
 r.ack(0x1ff);assert(r.tx[8]==7);assert(r.sent()==0xa1);
}
''')
            binary = root / "test"
            component = ROOT / "components" / "ld2454"
            subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-I", str(root),
                            "-I", str(component), str(source), str(component / "ld2454.cpp"),
                            "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
