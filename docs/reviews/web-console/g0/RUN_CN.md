# G0 探针运行说明

这是准备阶段，不是硬件通过。未点名板卡、串口和擦除授权前不要烧写。

## 已做的软件自测

在 `submodules/mmwave-component/static`：

```text
node --test --test-timeout=60000 test/g0-diag.test.js
```

诊断状态机对的是内存模拟器，不是真实串口。

固件契约测试会编译真实格式化函数，是必须项，不能跳过。它需要 C++ 编译器且跨平台：

```text
MWCP_GPP=/usr/bin/g++ node --test test/g0-hello.test.js
```

Windows：`$env:MWCP_GPP="D:\Build\mingw64\bin\g++.exe"`。未设置 `MWCP_GPP` 时从 PATH 查找（`where.exe g++` / `which g++`）。找不到编译器会抛错。CI 安装 `g++` 并设置 `MWCP_GPP`。

## 编译

2026-10-18 已在隔离环境用 `esphome==2026.9.1` / ESP-IDF 5.5.5 编译两份 YAML，退出码都是 0。G0-T 栈单位修复后用同一工具链再次编译两份，退出码都是 0。当前产物和 SHA256 见阶段报告第 20 节；第 18/19 节哈希已作废。系统 PATH 仍没有 `esphome`。复现：

```text
cd submodules/mmwave-component/docs/reviews/web-console/g0
esphome config baseline.yaml
esphome config host.yaml
esphome compile baseline.yaml
esphome compile host.yaml
```

记录打印出的 ESPHome 与 ESP-IDF 版本。`esp32-c3-devkitm-1` 只是编译占位，不是已确认实物。

## 差异

| 项 | baseline.yaml | host.yaml |
| --- | --- | --- |
| MWCP 组件 | 无 | `mmwave_host` |
| Improv Serial | 有 | 无 |
| 纯文本日志 | USB Serial/JTAG 默认，另有 `g0_meter` 每 5 秒一行 | UART0，`baud_rate: 0`，控制台 `CONFIG_ESP_CONSOLE_NONE` |
| 雷达 UART | GPIO21 TX、GPIO20 RX、115200 | 相同 |
| 离线重启策略 | Wi-Fi/API `reboot_timeout: 0s` | 相同 |
| 不存在的 SSID 占位 | `mwcp-g0-absent-ssid` / `unused-offline-probe` | 相同 |

该密码是不存在网络的占位符，不是用户秘密。

诊断页按锁定的 esp-web-tools 10.4.0，以 115200 调用 `port.open`。这不是雷达 UART 设置。雷达 UART 仍是 GPIO21/GPIO20、115200，走另一条控制器路径。

## 硬件暂停点

不要打开串口或烧写。下一步是阶段报告里的授权清单。
