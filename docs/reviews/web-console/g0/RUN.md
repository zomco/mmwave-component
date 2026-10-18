# G0 probe run notes

This is preparation only. It is not a hardware pass. Do not flash until the board, port, and erase permission are named.

## Software already checked

From `submodules/mmwave-component/static`:

```text
node --test --test-timeout=60000 test/g0-diag.test.js
```

The diagnostic controller is exercised against the in-memory simulator. That is not a serial-port test.

The firmware contract test compiles the real formatters and is required, not skipped. It needs a C++ compiler and is cross-platform:

```text
MWCP_GPP=/usr/bin/g++ node --test test/g0-hello.test.js
```

On Windows: `$env:MWCP_GPP="D:\Build\mingw64\bin\g++.exe"`. Without `MWCP_GPP` it searches PATH (`where.exe g++` / `which g++`). A missing compiler raises an error. CI installs `g++` and sets `MWCP_GPP`.

## Compile

On 2026-10-18 an isolated `esphome==2026.9.1` / ESP-IDF 5.5.5 compiled both YAML files, exit 0. After the G0-T stack-unit fix the same toolchain recompiled both, exit 0. Current artifacts and SHA256 are in phase-report section 20; section 18/19 hashes are obsolete. `esphome` is still not on PATH. To reproduce:

```text
cd submodules/mmwave-component/docs/reviews/web-console/g0
esphome config baseline.yaml
esphome config host.yaml
esphome compile baseline.yaml
esphome compile host.yaml
```

Record the printed ESPHome and ESP-IDF versions. Do not treat `esp32-c3-devkitm-1` as the physical board.

## Differences

| Item | baseline.yaml | host.yaml |
| --- | --- | --- |
| MWCP component | absent | `mmwave_host` |
| Improv Serial | present | absent |
| Logger plaintext | USB Serial/JTAG default, plus one `g0_meter` line every 5s | UART0, `baud_rate: 0`, console `CONFIG_ESP_CONSOLE_NONE` |
| Radar UART | GPIO21 TX, GPIO20 RX, 115200 | same |
| Offline reboot policy | Wi-Fi/API `reboot_timeout: 0s` | same |
| Absent SSID placeholder | `mwcp-g0-absent-ssid` / `unused-offline-probe` | same |

The password is a placeholder for a network that does not exist. It is not a user secret.

The diagnostic page opens Web Serial at 115200 because locked esp-web-tools 10.4.0 uses that `port.open` value. That number is not the radar UART setting. Radar UART remains GPIO21/GPIO20 at 115200 on a different controller.

## Hardware stop

Do not open a port or flash. The next step is the authorization checklist in the phase report.
