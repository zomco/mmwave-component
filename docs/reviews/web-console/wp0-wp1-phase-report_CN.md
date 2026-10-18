# WP-0 / WP-1 阶段报告

日期：2026-10-18。工作包：WP-0、WP-1。是否提交/发布：否。协议是否冻结：否。是否具备提交 G1 冻结评审的条件：**不具备。**

[English](wp0-wp1-phase-report.md)

## 1. 基线

| 项 | 值 |
| --- | --- |
| 工作区 | `468b4144a0653c5adde66351a2d8f7e94a0763c8`，分支 `main`，与设计提交相同 |
| mmwave-component | `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b` |
| mmwave-card | `5799d5729dd8bf6ee6114038bc989c2be1a35cf0`，只读 |
| Node | v22.13.1，npm 11.17.0 |
| esp-web-tools | lockfile 解析为 10.4.0；`package.json` 仍是 `^10.1.1`。本阶段没有改 lockfile |
| improv-wifi-serial-sdk | 2.8.0，esp-web-tools 的依赖 |
| esptool-js | 0.6.0，esp-web-tools 的依赖，应用未直接依赖 |
| ESPHome / ESP-IDF | 未锁定。CI 使用 `esphome/build-action@v7`，默认 `latest`。本机没有 `esphome`。见 DD-02 |
| C++ 主机测试 | `D:\Build\mingw64\bin\g++.exe` 13.3.0，`-std=c++14 -fno-exceptions -fno-rtti -static` |

工作区已有大量外壳相关未提交修改。本阶段没有重置、checkout 或改动 `cases/`、外壳技能、mmwave-fusion、mmwave-engine、mmwave-desktop、mmwave-card。组件仓库里原有的 `docs/rd03/*.step` 与 `docs/rd03d/*.step` 也未动。

## 2. 修改文件

新增，未接入烧录页，也未注册为 ESPHome 组件：

| 路径 | 用途 |
| --- | --- |
| `static/src/protocol/` | 无 DOM 的 JS codec、严格 JSON、客户端、内存模拟器、坐标函数、安装交接状态机 |
| `static/test/protocol-*.test.js`、`flash-handoff.test.js` | 主机测试 |
| `protocol/cpp/` | 独立 C++14 codec 与主机测试 |
| `protocol/fixtures/json-cases.json` | JS 与 C++ 共用的 JSON 期望结果 |
| `static/protocol-browser.html`、`protocol-browser-entry.js`、`vite.protocol.config.js` | 浏览器 `ProtocolClient` 入口，不是烧录页 |
| `docs/protocol/` | 草案 schema、R60 fixture、坐标向量、待评审差异 |
| `docs/reviews/web-console/` | 本报告与未编译的 G0 探针 YAML |

没有修改 `static/src/App.jsx`。模拟器不会被现有页面加载。

## 3. G0

用户没有指定测试板、串口、允许烧写或网络范围。没有打开、复位或烧写任何设备。

| ID | 状态 | 证据 |
| --- | --- | --- |
| G0-01 | not_run | 源码确认电脑路径是 ESP32-C3 原生 USB Serial/JTAG，雷达 UART 是 GPIO21 TX → 雷达 RX、GPIO20 RX ← 雷达 TX。R60 波特率 115200，这是雷达 UART，不是电脑 `port.open` 参数。目录板卡图片标记为 `reference-concept`，不能代替实物。`r60abd1.cpp` 只有一个 `loop()` UART reader。没有枚举设备或示波器/照片证据。 |
| G0-02 | not_run | 生产 logger 钉在 `USB_SERIAL_JTAG`，共享 `_device.yaml` 同时启用 `improv_serial`。这是两个 USB 消费者。探针 YAML 只写在评审目录，没有编译。logger 回调是否在 `baud_rate: 0` 后仍可用，未测。 |
| G0-03 | not_run | 现有 YAML 没有把 Wi-Fi/API `reboot_timeout` 设为 `0s`。源码预示无网络时可能周期重启。没有 2 小时运行。 |
| G0-04 | not_run | 已用 10.4.0 源码确认 `closed` 不等于 `port.close()` 完成，安装结束还会重开并尝试 Improv。浏览器成功/失败/取消/关闭/拔出路径未跑。交接方案见 DD-01，假端口测试只证明状态机，不证明操作系统已释放端口。 |
| G0-05 | not_run | 没有 host 与基线固件的堆、栈、loop 和丢帧对比。静态缓冲上限见第 6 节，不是设备测量。 |

G0 未通过。按交接要求，可以继续与硬件无关的 WP-1 草案，但不能宣布 G0 通过或冻结协议。

## 4. WP-1 已实现

- JSON Schema 草案覆盖已注册的 request、result 和 event，以及统一错误码。没有加入 `AUTH_REQUIRED`。
- JS 与 C++ codec 分开实现。两边都读取同一份 `protocol-vectors.json`，逐字节比对，不是同一实现自编自解。
- 严格 JSON：无 BOM、无重复键、深度、安全整数、非法 UTF-8。
- 客户端与内存模拟器：握手、request id、缓存、旧会话、分页冲突、丢响应后查询、不自动重放写入、限流、控制优先、1D/2D/空目标/未知/零坐标。模拟数据带 `origin: "simulation"`。
- 坐标向量含非零 pitch/roll、负坐标、1D 沿局部 +Y，以及现有射线法的边缘点。C++ 测试调用真实 `r60abd1_transform.h`，JS 测试对照卡片源码。

## 5. 命令与结果

```text
cd submodules/mmwave-component/static
node --test test/protocol-codec.test.js test/protocol-session.test.js test/protocol-schema.test.js test/protocol-coordinates.test.js test/flash-handoff.test.js
```

退出码 0。随后 `node --test test/*.test.js` 也是退出码 0，含原有安装页测试，29 项通过。

```text
D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-exceptions -fno-rtti -static -Wall -Wextra -Werror ^
  -I protocol\cpp -I components\r60abd1 ^
  -o %TEMP%\opencode\mwcp_host_test.exe ^
  protocol\cpp\mwcp_host_test.cpp protocol\cpp\mwcp_codec.cpp protocol\cpp\mwcp_json.cpp
%TEMP%\opencode\mwcp_host_test.exe docs\plans\mmwave-web-console\protocol-vectors.json
```

输出：`mwcp c++ host test passed`，退出码 0。

可复现故障样例：把黄金帧 `ping-request` 的 decoded 首字节翻转后再 COBS，解析器计为损坏且不执行；随后原黄金帧仍可交付。半帧在注入时钟上等待 2000 ms 后进入丢弃，下一个 `00` 之后的合法帧恢复。这些断言在 JS 与 C++ 测试中。

## 6. 内存与时延

未在 ESP32 上测量。静态上限：

| 缓冲 | 字节 |
| --- | --- |
| COBS 累积 | 4141 |
| decoded 帧 | 4124 |
| 含分隔符的最大线长 | 4143 |
| JSON 深度 / 键 / 数组 | 8 / 64 / 256 |
| `Parser::object()` 主机栈，`-fno-inline -fstack-usage` | 64 |
| `parse_object()` 主机栈 | 96 |
| `json_check()` 主机栈，含 512 个键区间 | 2144 |
| `classify_number()` 主机栈，`-fno-inline` | 192 |
| `finite_fraction()` 主机栈，H2 之后 | 80 |
| `exceeds_double_max()` 主机栈 | 96 |

修复前 `object()` 内有 `bytes[64][192]`。主机 g++ `-O2 -fstack-usage` 测得该帧 12976 静态字节，记录在 `C:\Users\zomco\AppData\Local\Temp\opencode\mwcp_json_before.su`。这不是 64 个指针。检查路径现在把键偏移放在同一个 `Parser` 里，并比较解码后的 Unicode，包括 `\u` 转义。嵌套 `object()` 会恢复 span 计数，不再每次调用保留 12 KiB 表。252 字节的唯一键可以通过。长数字改为就地扫描，已去掉 `digits[128]` 和 `tmp[96]`。溢出判断不是“大于 `DBL_MAX` 即非有限”。binary64 向偶数舍入的溢出点是 `2^1024 - 2^970`。数字串在 `protocol/fixtures/double-overflow-threshold.txt`，并对照该公式校验。不再调用 `strtod`。深度 8 的数字路径把已测帧相加为 4368 字节；若 `span_digit`（48）也在栈上则为 4416。这个和数不含未测量的 libc 帧，该路径不调用 `strtod`。`-O2` 下 `json_check` 为 2144，`value` 为 272。这些数字来自主机 g++ 13.3.0，不是 ESP32 测量。仍然没有设备 RPC 样本，架构时延预算未验证。

## 7. 通过、仅模拟、仍需真机

已通过：黄金向量互验、COBS/CRC/粘包/噪声恢复、schema 与 R60 fixture 的机器检查、会话和配置冲突的内存模拟、坐标源码对照。

仅模拟通过：握手、分页、丢响应查询、限流、优先级、1D/2D 语义。模拟器明确标记 `simulation`，不能当真机。

仍需真机：G0-01 至 G0-05 全部，R60 真实时序，安装器五条浏览器路径，堆/栈/loop，无 Wi-Fi 长运行。

## 8. 差异、失败、未执行

设计差异 DD-01 至 DD-13 在 `docs/protocol/design-differences_CN.md`，全部待评审。没有为了让测试通过而删除失败用例。

F1–F5 复跑没有失败断言，但浏览器清理可能挂起。第 12 节修正这一点。仍未执行：G0-01 至 G0-05、固件编译、ESP32 栈/堆、Ubuntu 浏览器、实际 GitHub Actions 运行，以及安装器五条浏览器烧录路径。协议浏览器检查是本地回环，不是串口设备。

需要用户提供：具体 ESP32-C3 板、确认原生 USB 而不是 UART 桥、雷达接线、允许烧写的串口、可丢弃的测试网络。未获授权前不会打开或烧写设备。

秘密检查：探针和报告没有写入 Wi-Fi 密码、API key 或 OTA 密码。模拟配网测试没有加入本阶段，因为没有实现会保存密码的固件路径。

## 9. 验收整改 R1–R9

这是软件回归修复，不是 G0 通过，也不是协议冻结。

| 项 | 根因 | 修复位置 | 回归测试 | 结果 |
| --- | --- | --- | --- | --- |
| R1 | `object()` 在 `skip()` 之后未检查 `i_ < len_` 就调用 `string()` | `protocol/cpp/mwcp_json.cpp` 的 `string`/`object`/`array`/`number`/`hex4` | `test_json_bounds_and_duplicates`，含 Windows `VirtualProtect` 保护页 | C++ 主机测试退出码 0，未再出现 `0xC0000005` |
| R2 | 测试读取父仓库黄金向量和兄弟仓库卡片源码 | 组件内 `protocol/fixtures/protocol-vectors.json`；卡片对照移到工作区 `tests/unit/test_mwcp_sources.py` | 隔离目录 `C:\Users\zomco\AppData\Local\Temp\opencode\mwcp-independent\static` 的 `node --test test/*.test.js` | 退出码 0，37 项通过 |
| R3 | 默认 `createClock()` 不会自己推进 | `client.js` 默认 `createRealClock()`；假时钟必须显式注入 | `real clock times out`、`fake clock is explicit` | 通过。超时后 `pending` 为空，下一次 RPC 可继续 |
| R4 | 模拟器先改状态再校验；客户端把 request 帧当 response | `contract.js` `validateRequest`/`validateResponse`；`simulator.js` 在 `dispatch` 前校验 | `invalid commit and ping`、`late response and request frame` | 缺 `op_id` 不增加 `writeCount`；request 帧不完成 RPC |
| R5 | C++ 按原始字节比键，指数整数走了浮点路径 | 两端按解码后的键比较；整数值含 `e`/` .0` 也检查安全整数 | `duplicate escaped keys` 与 C++ 同一组 `json-cases` 字符串 | `{"a":1,"\u0061":2}` 和 `9007199254740993e0` 两端拒绝 |
| R6 | `stale()` 用客户端时间减设备 `sample_ms` | `qualityOf()` 使用 `sent_ms - sample_ms` 加本地接收后单调时间 | `freshness uses device sent_ms` | 设备已运行一小时、网页刚收到近帧时仍为 valid |
| R7 | 订阅只回显预算；`events` 无限增长 | 第一次只合并了遥测。第 10 节改为所有已订阅事件共用协商的线字节预算。RPC 响应不计入。客户端最多保留 32 条 | `telemetry budget`，以及 `mixed events stay inside 1000 and 8000 byte windows` | 遥测回归仍是 100 个观测只发 1 帧。混合事件在 1000 B/s 下发出 966 字节并暂留 10 条 |
| R8 | `SESSION_CLOSE` 不失效；过期只在下一请求检查 | `expire()`；`clock.advance` 调用 `poll()` | 同一测试中的关闭与 15 秒无请求后的 `emitTelemetry` | 关闭后旧会话不能 PING；到期后不再推遥测；已保存 revision 不撤销 |
| R9 | schema 不约束 presence；`properties[key]` 会命中继承属性；断言含 `ok \|\| true` | `presenceSample`、`if/then`、`hasOwn`；响应对象 `x-open-object` | `schema rejects bad presence`；每个命令的非法样例 | 字符串 presence、unknown+true、`__proto__` 均失败。恒真断言已删除 |
| revision | `Number(revision)+1` 在 2^53 处停住 | `nextRevision()` 使用 `BigInt` | 同一测试，`9007199254740992` | 结果为 `9007199254740993` |

先前报告说 C++ 覆盖噪声和半帧恢复。当时只有 JS 测试。现已由 `test_parser_noise_and_half_frame` 实际执行，不能再写成未执行。

资源上限（主机模拟，不是 ESP32）：所有已订阅事件共用协商的编码后线字节预算；RPC 响应不计入且保持优先级 0；遥测、配置和状态只保留最新暂存；日志队列 8；暂存事件上限 16；客户端事件 32；解析器固定缓冲仍是 4141/4124。没有设备堆测量。

命令：

```text
cd submodules/mmwave-component/static
node --test test/*.test.js
npm run build
```

那次较早的 `node --test` 退出码 0，37 项通过，当时还没有 F1–F5 测试。安装页 `npm run build` 成功，但不能证明 `ProtocolClient` 可在浏览器运行。当前次数见第 10 节。隔离检出在那个较早时点同样 37 项通过；F1–F5 没有重建隔离树。

```text
D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-exceptions -fno-rtti -static -Wall -Wextra -Werror ^
  -I protocol\cpp -I components\r60abd1 ^
  -o %TEMP%\opencode\mwcp_host_test.exe ^
  protocol\cpp\mwcp_host_test.cpp protocol\cpp\mwcp_codec.cpp protocol\cpp\mwcp_json.cpp
%TEMP%\opencode\mwcp_host_test.exe protocol\fixtures\protocol-vectors.json
```

退出码 0。保护页测试在同一可执行文件内。

## 10. 验收 F1–F5

只做软件回归。不是 G0 通过，也不是协议冻结。

| 项 | 根因 | 修复位置 | 回归测试 | 结果 |
| --- | --- | --- | --- | --- |
| F1 | `contract.js` 用 `node:fs` 读 schema；安装页构建没有加载 `ProtocolClient` | 以 JSON import 读取 `docs/protocol/schema/mwcp-v1.schema.json`。浏览器入口不导入仍使用 `node:crypto` 的 `simulator.js` | `protocol-browser.test.js` | 有一次 Windows 运行完成了 HELLO/PING，但清理时 `server.close()` 等待 Chrome 仍持有的连接。这是 G1，不能当作浏览器路径可靠的证据 |
| F2 | `object()` 预留 `bytes[64][192]`，静态 12976 字节 | 键偏移放在同一个 `Parser`；按解码后的键比较 | C++ 主机测试，含保护页，以及 252 字节键和 `\u00e9` | `object()` 64，`parse_object()` 96，`json_check()` 2144。仅主机 |
| F3 | 指数下溢和超大整数可能不一致，且 `1e999` 被标成 `number` | 共用 `protocol/fixtures/json-cases.json`，26 例，JS 与 C++ 都读取 | `shared JSON fixture` 与 `test_shared_json_cases` | `1e-2`、`1.2e-3`、`0.01`、`1e-1` 接受。`9007199254740993e0`、`9007199254740993.0` 和 `1e999` 为 `unsafe_integer` |
| F4 | 预算和速率只覆盖遥测。显式 `expire()` 后 `bumpExternal` 可能抛错 | 所有已订阅事件共用线字节。RPC 为优先级 0 且不计入 | 混合窗口测试和显式 `expire()` | 那些测试没有在不调用 `poll()` 的情况下推进时钟。自然到期仍会发出 `CONFIG_CHANGED`。第 12 节修正 |
| F5 | `write()` 成功会刷新存活；过期依赖 `link()` 调用 `client.poll()` | 客户端只在 HELLO/RPC 响应后武装自己的 15 秒计时器。心跳仍是 5 秒。不重放副作用 | `client liveness does not treat a successful write`、`successful pings keep the session` | 丢弃响应后离线。20 秒内成功 PING 保持在线。只有遥测不会续期。之后的 PING 拒绝为 `session_expired` |

```text
cd submodules/mmwave-component/static
node --test test/*.test.js
```

退出码 0。43 项通过，含无头 Chrome 测试。

```text
D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-exceptions -fno-rtti -static -Wall -Wextra -Werror ^
  -I protocol\cpp -I components\r60abd1 ^
  -o %TEMP%\opencode\mwcp_host_test.exe ^
  protocol\cpp\mwcp_host_test.cpp protocol\cpp\mwcp_codec.cpp protocol\cpp\mwcp_json.cpp
%TEMP%\opencode\mwcp_host_test.exe protocol\fixtures\protocol-vectors.json
```

输出：`mwcp c++ host test passed`，退出码 0。

```text
D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-inline -fstack-usage -fno-exceptions -fno-rtti -Wall -Wextra -Werror -c ^
  -I protocol\cpp -o %TEMP%\opencode\mwcp_json_noinline.o protocol\cpp\mwcp_json.cpp
```

`object()` 64，`parse_object()` 96，`json_check()` 2144。不是 ESP32 测量。

## 12. 验收 G1–G4

不是 G0 通过，也不是协议冻结。主机测试和一次 Windows 浏览器运行通过。这里没有执行 Ubuntu 和 GitHub Actions。

| 项 | 根因 | 修复位置 | 回归测试 | 结果 |
| --- | --- | --- | --- | --- |
| G1 | 浏览器测试写死 `C:\Program Files\Google\Chrome\Application\chrome.exe`，`taskkill` 未等待。`finally` 在 Chrome 仍持有 HTTP 连接时等待 `server.close()`，整套测试可能挂起。管道没有超时 | `static/test/browser-harness.js` 查找 `MWCP_CHROME`、常见 Windows/Linux 路径或 `which`。启动使用 `stdio: ignore`。构建、启动、CDP 和页面结果都有超时。清理只结束本次进程树，先销毁套接字再关服务。`web.yml` 与 `publish-pages.yml` 用 `browser-actions/setup-chrome@v2` 安装 Chrome，并分别运行 `npm run test:unit` 和 `npm run test:browser` | Windows `node --test --test-timeout=20000 test/protocol-browser.test.js`；无效可执行文件测试 | Windows 浏览器测试 8.5 秒退出码 0。正文含 `"ok":true`。无效路径约 20ms 失败，没有残留进程。`npm test` 退出码 0，50 项通过，进程退出。Ubuntu：not_run。WSL 未能启动（`networkingMode Mirrored`，`0x8007054f`），`docker version` 没有返回。GitHub Actions 实际运行：not_run |
| G2 | 新的 `hello()` 留下旧的 15 秒计时器。`expireLocal()` 拒绝了新握手。`hello()` 在发现 `rpc_inflight` 之前就清了 `sessionLive` | 只有确认没有 pending 后，`endSession()` 才增加 `generation` 并清除心跳和存活计时器。计时器和超时回调在 generation 或 pending 槽位变化后不再动作。有副作用的请求仍然不重试 | `protocol-g-fixes.test.js` | 14.9 秒重握手、延迟的旧回调、进行中的 `hello()`、失败后重试、旧心跳重叠均通过 |
| G3 | `classify_number()` 复制到 `digits[128]` 和 `tmp[96]`，拒绝了低于 4096 字节载荷上限的合法数字 | 就地扫描。整数宽度不使用大缓冲。非整数只用 40 字节科学计数探针判断有限性 | JS 与 C++ 共用 `json-cases.json` | `0.` 加 100 个零加 `1`（109 字节）和 `1.` 加 150 个零（158 字节）接受。4090 字节的 `1.` 加零接受。带长 `.0` 尾的 `9007199254740993` 为 `unsafe_integer`。`1.` 加 400 个零加 `1e400` 为 `number`。C++ 主机测试退出码 0，含保护页、Unicode 重复键、噪声和半帧恢复 |
| G4 | 事件发送只检查会话对象存在，不检查 `now` 是否仍在 15 秒截止时间内。测试调用了 `poll()` 或 `expire()` | `offerEvent` 和 `releaseEvents` 使用 `sessionAlive()`。会话计时器不依赖 `poll()`。预算窗口恢复时释放计时器发送暂存事件，到期后丢弃剩余事件。断开、关闭、取消订阅和新 nonce 清除旧事件。配置状态仍会更新 | 直接创建客户端和设备，时钟推进 16000ms，不调用 `poll()` 或 `expire()` | 会话、订阅和暂存事件被清除。`bumpExternal` 更新了 `install.x_cm`，之后没有再发事件字节。status、jobs、logs 未发送。速率暂存的遥测在下一窗口发出，到期后不再补发 |

```text
cd submodules/mmwave-component/static
node --test --test-timeout=20000 test/protocol-browser.test.js
npm test
npm run build
```

浏览器命令退出码 0。`npm test` 退出码 0，50 项通过。`npm run build` 退出码 0。

```text
D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-exceptions -fno-rtti -static -Wall -Wextra -Werror ^
  -I protocol\cpp -I components\r60abd1 ^
  -o %TEMP%\opencode\mwcp_host_test.exe ^
  protocol\cpp\mwcp_host_test.cpp protocol\cpp\mwcp_codec.cpp protocol\cpp\mwcp_json.cpp
%TEMP%\opencode\mwcp_host_test.exe protocol\fixtures\protocol-vectors.json
```

输出：`mwcp c++ host test passed`，退出码 0。

```text
python -m unittest tests.unit.test_mwcp_sources -v
```

退出码 0，2 项，在工作区运行。该测试读取兄弟卡片仓库；独立组件运行不读取它。

独立目录 `C:\Users\zomco\AppData\Local\Temp\opencode\mwcp-g4-isolated` 含本次组件协议、schema、变换头文件和 static 测试。在该目录执行了 `npm ci`。`node --test --test-timeout=120000 test/*.test.js` 退出码 0，50 项通过。同一 g++ 主机命令退出码 0。不使用父工作区设计文件或兄弟仓库。

没有新增 npm 依赖。锁文件未改。

## 13. G 轮结论

本段只记录 G1–G4 那一轮，不是当前覆盖结论。那一轮有主机回归和一次 Windows Chrome 回环。Ubuntu 与 GitHub Actions 为 not_run。第 14 节是之后的 H1–H3。

## 14. 验收 H1–H3

不是 G0 通过，也不是协议冻结。先前的 50/50 没有覆盖这些边界用例。

| 项 | 根因 | 修复位置 | 回归测试 | 结果 |
| --- | --- | --- | --- | --- |
| H1 | `handleFrame()` 在超时回调还没跑时仍接受响应。挂起的时钟可以完成迟到的 PING 并刷新存活。旧回调还会在检查 generation 之前清空 `livenessTimer` / `heartbeat` | 请求和会话保存绝对截止时间。接收、poll 和新 RPC 即使没有回调也会检查 `now >= deadline`。回调先核对 generation 和计时器身份，再清当前句柄 | `protocol-h-fixes.test.js`，使用 `clock.jump()` | t=0 HELLO、t=14000 PING、跳到 30000 后迟到 PING 被拒绝，`sessionLive` 为 false，`lastResponseAt` 仍是 0。仅请求超时、会话截止边界、迟到 HELLO、回调先于响应、旧回调与新句柄、只有遥测、心跳均通过 |
| H2 | `finite_fraction()` 截取 17 位后调用 `strtod`。330 字节输入在 JS 中是 Infinity，C++ 却接受 | 第一次对照了精确 `DBL_MAX`。那不是 JS 的舍入阈值。第 16 节改为 `2^1024 - 2^970` | 共用 `json-cases.json` | 330 字节输入仍为 `number`。会舍入成有限最大值的 329 字节输入被接受。见第 16 节 |
| H3 | CDP `send()` 没有命令超时，close/error 也不拒绝 pending。`--test-skip-pattern protocol-browser` 匹配不到测试名，`test:unit` 仍会启动 Chrome | `connectCdp()` 为每条命令计时，并在 close/error 时拒绝 pending。浏览器测试移到 `test/browser/`。`test:unit` 只跑 `test/*.test.js`。`npm test` 各跑一次 unit 和 browser。CI 仍分别运行两个脚本 | `protocol-cdp.test.js` 以及 `test:unit` / `test:browser` | 不回复、关闭、报错、迟到响应和空页面都在截止时间内失败。`MWCP_CHROME=mwcp-missing-browser npm run test:unit` 退出码 0，59 项通过，没有启动浏览器。同一环境的 `npm run test:browser` 退出码 1，`ENOENT`，不是假通过。正常 Windows `npm run test:browser` 退出码 0 |

```text
cd submodules/mmwave-component/static
$env:MWCP_CHROME='mwcp-missing-browser'; npm run test:unit
$env:MWCP_CHROME='mwcp-missing-browser'; npm run test:browser
Remove-Item Env:MWCP_CHROME
npm run test:browser
npm test
npm run build
```

无效浏览器下 unit 退出码 0，59 项通过。无效浏览器下 browser 命令退出码 1。正常浏览器命令退出码 0。`npm test` 退出码 0，61 项通过。`npm run build` 退出码 0。

C++ 主机测试：`mwcp c++ host test passed`，退出码 0。`python -m unittest tests.unit.test_mwcp_sources -v` 退出码 0，2 项。

独立目录 `C:\Users\zomco\AppData\Local\Temp\opencode\mwcp-h3-isolated`：`npm ci` 后 Node 61 项通过，g++ 主机测试通过。不读取父工作区设计文件或兄弟仓库。

没有新增 npm 依赖。锁文件未改。

## 15. 结论

H1 与 H3 已通过后续复查。上面的 H2 行由第 16 节修正。H3 另有一次 Windows 无头 Chrome 的 HELLO/PING 结果。Ubuntu 浏览器和实际 GitHub Actions 运行仍是 not_run。G0-01 至 G0-05 仍是 not_run。协议未冻结。不能进入 WP-2/WP-3。没有提交、推送、烧写或发布。请原设计者独立复验。

## 16. H2 舍入边界

H1 与 H3 已通过原设计者本轮复查。上一轮 H2 的表述不是当前规则：对照 `DBL_MAX` 的精确十进制，会拒绝一些 `Number()` 仍舍入为有限最大值的输入。

根因：向偶数舍入时，精确值达到中点 `(DBL_MAX + 2^1024) / 2 = 2^1024 - 2^970` 才溢出，不是一超过 `DBL_MAX` 就溢出。

必须接受的失败样例：`1.7976931348623158` 加 300 个零加 `1e308`，载荷 329 字节。JS `Number()` 为 `1.7976931348623157e+308`，有限。上一轮多一个 `9` 的 330 字节输入仍是 `Infinity`，拒绝为 `number`。

阈值数字由该公式生成，写入 `double-overflow-threshold.txt`，JS 测试对照公式校验。C++ 主机测试核对 `json_overflow_threshold()` 与该文件一致。超出 `±(2^53-1)` 的整数仍是 `unsafe_integer`。

新增共用案例包括 329 字节接受、负数、`e+308`、`E308`、小数点移位、中点下方的非整数和中点上方的非整数。接受案例同时断言 JS 转换有限。拒绝的溢出案例断言 `number`，不是只看两端相同。

栈帧没有变大：`overflows_binary64` 96，`finite_fraction` 80，`json_check` 2144。`-O2` 的 `value` 仍是 272。仅主机。

`npm run test:unit` 退出码 0，59 项通过。`npm run test:browser` 退出码 0，2 项通过。`npm test` 退出码 0，61 项通过。`npm run build` 退出码 0。C++ 主机测试退出码 0。工作区 `test_mwcp_sources` 退出码 0，2 项。

Ubuntu、GitHub Actions 和 G0 仍是 not_run。协议未冻结。没有提交或烧写。

## 17. G0 准备阶段

G0 **未完成**。没有硬件授权，没有打开串口，没有烧写。软件测试通过不是 G0 通过。不具备进入 G1 审查的条件。

| 项 | 状态 | 证据 |
| --- | --- | --- |
| G0-01 | not_run | 没有板卡照片、原理图或实测 USB 路径 |
| G0-02 | not_run | host YAML 已在锁定 ESPHome 上编译，见第 18 节。没有在设备上运行，不能证明 USB 独占 |
| G0-03 | not_run | 没有两小时离线运行 |
| G0-04 | not_run | 没有烧录成功/失败/取消/关闭/拔插 |
| G0-05 | not_run | 没有对照固件的堆、栈和时延 |

基线：工作区 `468b4144a0653c5adde66351a2d8f7e94a0763c8`，组件 `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b`，另有未提交协议/G0 文件。Node v22.13.1，npm 11.17.0，Python 3.14.7，esp-web-tools lockfile 10.4.0。系统 PATH 没有 `esphome`；隔离环境见第 18 节。`esp32-c3-devkitm-1` 只是编译占位。

准备产物在 `docs/reviews/web-console/g0/`：`baseline.yaml`、`host.yaml`、`components/mmwave_host/`、`RUN_CN.md`。诊断页 `static/g0-diag.html`。`node --test test/g0-diag.test.js` 退出码 0，这是模拟器自测。

暂停点：需要用户确认板卡型号、USB 路径、R60 接线、指定串口 VID/PID、是否专用测试机、允许烧写的固件、是否保留现有固件、默认禁止整片擦除。未确认前不会枚举后打开设备。

## 18. G0-R 软件补救

G0 仍未完成。本节只记录软件编译和主机回归。没有打开串口，没有烧写。静态体积不是 G0-05。

隔离环境：`esphome==2026.9.1`，ESP-IDF 5.5.5，riscv32-esp-elf GCC 14.2.0（`esp-14.2.0_20260121`），构建用的 esptool.py 4.12.0。构建目录在临时目录，不在仓库内。两次 `esphome compile` 均退出码 0。

| 固件 | OTA SHA256 | factory SHA256 | 链接期 RAM | 链接期 Flash |
| --- | --- | --- | --- | --- |
| host | `8D5E8A9CFB3C11B1676CE79AD234EF78305F24224050DA2CC1CC6F36144A92D7` | `1F4EFB06EA0A206886926F1FF39B6D52517ED68EA678A9F96D63C4F9F8393300` | 120072 / 321296 | 766826 / 1835008 |
| baseline | `E4E20DD0D8F70E546500251144AA0401A21D1A4A5CAC0C6C3CE1001FDE2B948E` | `E01669731DAB02044B2BF2E25E9F1830C8D9B83ABB98B4BECA213703A733D485` | 102556 / 321296 | 764188 / 1835008 |

host 相对 baseline 多 17516 字节 RAM、2638 字节 Flash。这是链接期占用，不是运行时堆、栈或 loop。

| 项 | 结果 |
| --- | --- |
| G0-R1 | C++ 命名空间是 `esphome::mmwave_host::MwcpHost`。IDF 工具链不接收普通 `-I`，协议头通过 `add_cxx_build_flag` 进入 C++ 选项。两份协议源必须分开编译，合进同一翻译单元会让 `Parser` 重名。host 的 logger 使用 UART0 且 `baud_rate: 0`；`hardware_uart: USB_SERIAL_JTAG` 会编进 USB 初始化并与 `CONFIG_ESP_CONSOLE_NONE` 链接失败。sdkconfig 已是 `CONFIG_ESP_CONSOLE_NONE=y`。 |
| G0-R2 | `node --test test/g0-diag.test.js` 3 项退出码 0。`npm test` 退出码 0，64 项通过。仍是模拟器，不是串口。 |
| G0-R3 | 雷达计数走 `R60ProbeStats`，不依赖 `frame_id_`。`r60_probe_stats_test.cpp` 主机测试通过，并编进 host 固件。设备上未测。 |
| G0-R4 | 发送使用成员缓冲和 64 字节、超时 0 的泵。主机测试通过，并编进 host 固件。设备上未测。 |
| G0-R5 | `boot_id` 使用 MAC 加两次 `esp_random()`。会话号递增。诊断日志上限 200，证据上限 8000。已编译，设备上未测。 |

G0-01 至 G0-05 仍是 not_run。协议未冻结。不能进入 WP-2/WP-3。没有提交、推送或烧写。

## 19. G0-S 软件准备

软件准备 **通过**。这不是 G0 硬件通过。第 18 节的固件哈希已被本节取代，不能代表当前代码。

| 项 | 状态 | 根因与变更 | 回归 |
| --- | --- | --- | --- |
| G0-S1 | 通过 | `%02x` 四字节 MAC 加两个 `%08lx` 只有 24 个十六进制字符，schema `hex32` 拒绝 HELLO。`g0_format_boot_id()` 使用 6 字节 MAC 和 10 字节随机数，`%02x` 保留前导零。同一函数生成 HELLO JSON。 | `g0_hello_emit` 的输出交给现有 `ProtocolClient`/`validateResponse` 完成握手。截成 24 位仍被 schema 拒绝。会话隔离和重启身份有覆盖。 |
| G0-S2 | 通过 | 断开时递增 generation，迟到的选择不再打开，迟到的 open 会关闭。`cancel()` 后 `releaseLock()`，关闭失败保留端口。读写锁独立。页面订阅状态。 | `test/g0-diag.test.js` 使用真实 `ReadableStream`/`WritableStream` 和控制器 transport 上的 `ProtocolClient`。按钮点击会触发连接。 |
| G0-S3 | 通过 | 采集有开始记录、本地单调 RTT、`rpc_inflight` 间隙计数和有界截断。未测量项来自设备 status，不用 healthy 或零代替。基线用 `g0_meter` 每 5 秒打一行，不开 MWCP。 | 采集测试通过。基线行由固件格式函数生成后再解析。设备上的两小时样本仍是 not_run。 |
| G0-S4 | 通过 | 连续零写 250ms 后放弃；已发出的半帧标记重同步，下一帧前补 `0x00`。会话结束丢弃旧队列。HELLO 先清队列，入队失败不切换会话。 | `g0_session_test.cpp` 覆盖零写超时、半帧失败、过期、占用队列时的新 HELLO 和解析器重同步。 |
| G0-S5 | 通过，先前失败未复现 | 没有把失败改成跳过。本环境 Chrome `155.0.8059.84` 上 `npm run test:browser` 连续三次 2/2 通过。独立复核报告的 `cdp closed` 没有复现，原因未定位，断言未放宽。 | `npm run test:unit` 65/65 退出码 0。C++ `g0_session_test` 与 `r60_probe_stats_test` 退出码 0。 |

编译命令：隔离环境 `esphome==2026.9.1`，ESP-IDF 5.5.5，`esphome compile docs/reviews/web-console/g0/host.yaml` 与 `baseline.yaml`，退出码都是 0。产物在 `C:\Users\zomco\AppData\Local\Temp\opencode\esphome-data\build\`。链接期体积不是运行时堆或栈。

| 固件 | OTA SHA256 | factory SHA256 | 链接期 RAM | 链接期 Flash |
| --- | --- | --- | --- | --- |
| host | `9971612CC6749B7A74EC069E4376A5657F41C48AE4C93DE007167EA584E83C08` | `470F7FEB96B2E8F7F0CB0D3E7A4FAA1B35F208D86BD39A97F76FC63E4A931694` | 120112 / 321296 | 767510 / 1835008 |
| baseline | `D5C7DE3C8986EA531407D936D7023820D4C23591A934166272EAE063B3ACB82C` | `2101FBEFF36C69F59EA9B0B20A22F03C073A6771DD4F03290ECB03AD347C979E` | 102588 / 321296 | 765218 / 1835008 |

工作区 `468b4144a0653c5adde66351a2d8f7e94a0763c8`，组件 `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b`，另有未提交差异。G0 源文件快照哈希 `89776E4C23A3951825DA9CD4B89628D5A9846B6009BF93B4F0C8EE0B04A4A49A`。栈水位单位按 ESP-IDF 5.5.5 `task.h` 记为 FreeRTOS word，32 位目标上 1 word = 4 字节；这不是设备测量。

| 硬件项 | 状态 |
| --- | --- |
| G0-01 | not_run |
| G0-02 | not_run |
| G0-03 | not_run |
| G0-04 | not_run |
| G0-05 | not_run |

仍需用户确认：板卡与原生 USB 路径、R60ABD1 接线与供电、串口 VID/PID、是否专用测试机、允许烧写的固件、是否保留现有固件、禁止整片擦除。未确认前不打开串口、不烧写。协议未冻结。没有提交或进入 WP-2/WP-3。

## 20. G0-T 软件整改

G0-T1–T4 之后软件准备 **通过**。这不是 G0 硬件通过。第 19 节的固件哈希和“1 word = 4 字节”的栈水位标注已作废，由本节取代。

| 项 | 状态 | 原因与改动 | 回归 |
| --- | --- | --- | --- |
| G0-T1 | 通过 | `static/test/g0-hello.test.js` 写死了 `D:\Build\mingw64\bin\g++.exe` 和 Windows 临时路径，Linux 运行器无编译器。现在从 `MWCP_GPP` 或 PATH（`where.exe` / `which`）解析编译器，在 `mkdtempSync(join(tmpdir(), 'mwcp-g0-hello-'))` 中构建，用 `platform()` / `join` / `.exe` 后缀，`spawnSync` 对编译（20 秒）和运行（5 秒）设超时，并在 `finally` 中 `rmSync` 清理。找不到编译器会抛错而不是跳过。CI 安装 `g++` 并设置 `MWCP_GPP`。 | 固件 emitter 输出仍完成 `ProtocolClient` 握手。 |
| G0-T2 | 通过 | 永久挂起的写会让 `phase=online`、端口保持打开、`capture.stopped=false`。`disconnect()` 现在先置 `closing`，调用 `endCapture('disconnect')`，所有等待都以 `ioWaitMs` 为界。写/取消/关闭卡住时进入 `error`，提示 `resources held; retry disconnect before connecting again`，保留端口，并向调用方 reject（页面已捕获）。 | `test/g0-diag.test.js` 的 “a hung write...” 与 “cancel and open...”。反向验证：去掉 `endCapture('disconnect')` 该测试失败。 |
| G0-T3 | 通过 | `sampleOnce` 在 `await` 之后读取全局 capture，迟到的结果会污染下一次运行；错误和事件无界。现在每个样本绑定到自己的 run 对象和 generation，`stopCapture()` 脱离当前 run，样本按有界分段滚动（`maxSamples` 64、`maxSegments` 120，约 1 Hz 下 2 小时）并带间隙计数，错误/事件有上限（`maxErrors` / `maxEvents` 32）并记录丢弃计数，`exportEvidence()` 输出 segments、coverage、`missing`、`gaps`、`healthy`。 | “capture runs do not accept late results and stay bounded”：迟到结果进入 run A 而非 run B；强制 5 个错误保留 2 个、丢弃 3 个，`healthy:false`。 |
| G0-T4 | 通过 | ESP-IDF 5.5.5 RISC-V 的 `portSTACK_TYPE` 是 `uint8_t`，`uxTaskGetStackHighWaterMark` 返回**字节**；`stack_high_water_words` 配 `stack_word_bytes=4` 是 4 倍高估。字段改为 `stack_high_water_bytes`、`stack_high_water_unit:"bytes"`、`stack_type_bytes:1`；两份固件加 `static_assert(sizeof(StackType_t)==1)`；证据在 `docs/reviews/web-console/g0/stack-unit.json`。 | C++ 与 JS 断言 `600`、拒绝 `2400`、拒绝任何 `stack_word_bytes`。反向验证：改回 words×4 的头文件使 `g0_session_test` 报 “raw mark is already bytes” 失败。 |

命令与结果：
- `npm run test:unit` 68/68，退出码 0（原 65，新增 3 个 g0-diag 用例）。
- `node --test test/g0-diag.test.js test/g0-hello.test.js` 9/9，退出码 0（已设 `MWCP_GPP`）。
- C++ `g0_session_test` 与 `r60_probe_stats_test` 退出码 0（g++ 13.3.0，`-Wall -Wextra -Werror -static-libgcc -static-libstdc++`）。
- `npm run test:browser` 2/2，退出码 0，Chrome 155.0.8059.84。
- `npm run build` 退出码 0。
- `esphome==2026.9.1` / ESP-IDF 5.5.5 编译 `host.yaml` 与 `baseline.yaml`，退出码都是 0。

| 固件 | OTA SHA256 | factory SHA256 | 链接期 RAM | 链接期 flash |
| --- | --- | --- | --- | --- |
| host | `DF0DA7283D78E899B478F6092C125528964FABCED6FB4EF49F7B5ACDD8674026` | `72C87C3DB3AAEF9A9C1968F2994365230D63FF33B3D0F50BE7B52A725CE56DD6` | 120112 / 321296 | 767502 / 1835008 |
| baseline | `7E0B7077A8D8A0594184C7F46924BC0A05969BC583F2777E96E0ADDA6CB4D1B8` | `EDD243713F65C6B86DDA7642AF140898A24EABAD804A23E54B17AF14186BB21D` | 102588 / 321296 | 765210 / 1835008 |

工作区 `468b4144a0653c5adde66351a2d8f7e94a0763c8`，组件 `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b`，另有未提交差异。G0 源文件快照哈希 `E673FFB3717040CACEB19835F245A1ED03C76C62336F4FCD79BC33A5D0D4E114` —— 对该 76 个文件的 `sha256<空格>相对路径` 排序列表再做 SHA256，文件位于 `docs/reviews/web-console/g0`、`protocol/cpp`、`static/src/g0`、`static/src/protocol`、`static/test`、`components/r60abd1` 和 `docs/protocol/schema/mwcp-v1.schema.json`。第 18/19 节没有记录算法，故在此写明。

Linux/WSL 与 GitHub Actions 的跨平台执行尚未在此运行；测试与 CI 已支持，但在实际执行前该运行保持 **blocked**。链接期大小不是运行时堆或栈，以上都不是设备测量。

| 硬件项 | 状态 |
| --- | --- |
| G0-01 | not_run |
| G0-02 | not_run |
| G0-03 | not_run |
| G0-04 | not_run |
| G0-05 | not_run |

硬件前置条件同第 19 节，仍未确认。没有打开串口、没有烧写。协议未冻结。没有提交、推送或发布，也未进入 WP-2/WP-3。

## 21. G0-U 软件整改（第 2 轮修正与第 3 轮端口重开生命周期修复）

### 结论更正说明
上一轮整改报告曾得出“软件准备通过”的结论，经独立复核指出存在遗留缺陷，该结论属于**过早判定**，在此正式撤回更正：
1. **U2 遗留（关闭超时迟到）**：`port.close()` 超时后若在底层延迟成功，后续再次调用 `disconnect()` 会对已处于 `closed` 状态的端口重复调用 `close()`，触发 Web Serial 规范的 `InvalidStateError`，控制器永远保留 `port`，导致重连被永久阻断。先前回归采用简化的无状态端口替身（可反复调用 `close()`），构成了假阴性测试。
2. **U2 遗留（端口对象重用生命周期）**：关闭状态原采用 `closedPorts = new WeakSet()` 永久绑定到端口对象。当同一端口对象被再次 `connect()` 重新打开后，其旧关闭标记未失效；后续 `disconnect()` 命中 `closedPorts` 直接跳过实际 `port.close()`，控制器声称 `closed` 但底层端口实际仍处于 `opened`，导致第三次连接报 `streams before open`。
3. **U3 遗留（导出破坏性分段）**：`exportEvidence()` 内部调用 `flushSegment(capture)`，将尚未填满当前段的样本直接提交到有限的分段存储中。在 `maxSamples=2, maxSegments=1` 条件下，采样 1 次→导出→采样 1 次→导出，会导致第二次采样被强行降级为摘要分段并丢弃原始样本（`raw=1, summary=1, healthy=false`），与连续采样后导出（`raw=2, summary=0, healthy=true`）产生严重分歧，导出频率破坏了数据保留容量与健康结论。

本轮针对上述遗留缺陷实施了彻底整改，并在严格 Web Serial 状态模型、生命周期代际模型（epoch）与幂等快照模型下全面通过回归验证。

| 项 | 状态 | 根因与实际修复 | 回归验证 |
| --- | --- | --- | --- |
| G0-U1 | 通过 | `findCompiler()` 执行 `existsSync(process.env.MWCP_GPP)`，将 `g++` 等命令名误当成当前工作目录下的文件路径，导致 CI 工作流设置 `MWCP_GPP=g++` 失败。`resolveCompiler()` 现同时支持已存在的绝对/相对路径以及通过 PATH（`which` / `where.exe`）解析的命令名。显式配置无效或在 PATH/文件系统中缺失时立即抛出明确异常，绝不静默切换编译器或跳过测试。`.github/workflows/web.yml` 与 `publish-pages.yml` 明确补充了该双重支持注释。 | `static/test/g0-hello.test.js` 中的 7 项回归矩阵覆盖：未设置变量 PATH 自动发现、`MWCP_GPP=g++` PATH 发现、含空格有效绝对路径、无效路径、无效命令名、显式空配置、编译器不可用。已使用 CI 实际配置 `MWCP_GPP=g++` 验证执行。 |
| G0-U2 | 通过 | **根因**：<br>1. 原控制器未按端口实例跟踪关闭生命周期。底层 `port.close()` 超时仍在后台运行，超时后重试 `disconnect()` 会对同一个已处于 `closing`/`closed` 的端口重复调用 `close()` 引发 `InvalidStateError`；<br>2. `closedPorts` 为全局 `WeakSet`，使端口对象的关闭状态变为永久性。同一端口重新 open 后，旧 closed 状态未失效，导致后续 disconnect 跳过实际 close，底层端口保持 opened。<br>**修复**：<br>1. 引入打开生命周期代际模型：`portEpochs = new WeakMap()` 记录端口当前打开代际，`closedPortEpochs = new WeakMap()` 记录已完成关闭的代际，`portCloseStates = new Map()` 记录 `{ epoch, promise, status, error }`；<br>2. 每次 `connect()` 在调用 `selected.open()` 前递增代际（`nextEpoch`），确保新生命周期彻底使旧关闭标记失效；<br>3. `requestClosePort(p)` 仅当 `closedPortEpochs.get(p) === currentEpoch` 时才认为当前生命周期已关闭；对当前代际正在进行的关闭复用原 Promise，避免并发或重复调用 `p.close()`；失败后允许安全重试；<br>4. 超时等待不终止底层关闭操作；迟到成功后由 `handlePortClosed(p, epoch)` 校验代际，仅在当前端口仍属于该代际时清空控制器引用，清理 `unreleasedPorts` 并清除 `guidance`，允许同页面重新连接；<br>5. 严格隔离端口与代际上下文，旧连接清理闭包绝不影响或关闭后来连接的新端口或新代际；<br>6. 普通 `disconnect()`、迟到 `open` 清理、`unreleasedPorts` 重试与 `failRead` 统一接入代际感知 `requestClosePort`。 | 在 `static/test/g0-diag.test.js` 中引入符合 Web Serial 规范的严格端口模型 `createStrictPort`（区分 `closed`、`opening`、`opened`、`closing`，关闭中或已关闭时直接调用 `close()` 抛出 `InvalidStateError`）。新增 11 组严格回归全部通过：<br>1. 正常连接后 close 超时，随后成功，可恢复连接；<br>2. open 迟到成功后，清理 close 又超时，随后成功，可恢复连接；<br>3. close 迟到失败后可安全重试；<br>4. close 永久挂起时持续拒绝重连，API 等待有界；<br>5. 重复 disconnect 不重复启动同一关闭任务；<br>6. 旧清理任务不影响新端口；<br>7. **同一端口对象连续 3 轮 connect→握手→disconnect**，每轮断开后底层端口真实 closed、流锁释放，最终 `openCount=3, closeCount=3`；<br>8. 同一端口 close 超时迟到成功后，重新打开并正常关闭；<br>9. 曾关闭过的同一端口，下一轮 open 超时且迟到成功后，仍真正执行清理关闭；<br>10. 同一端口重复 disconnect 不增加当前生命周期 close 次数；<br>11. 旧任务不影响后续生命周期，失败与永久挂起持续保持安全阻断。 |
| G0-U3 | 通过 | **根因**：`exportEvidence()` 包含破坏性副作用（调用 `flushSegment(capture)` 强制提交未满段），导致导出频率改变分段边界、提前消耗原始分段配额并触发摘要降级与历史丢弃。<br>**修复**：<br>1. 彻底移除 `exportEvidence()` 内的 `flushSegment` 调用，将导出重构为非破坏性快照；<br>2. 正在累积的未满段作为临时尾段 `pendingSegment` 包含在快照的 `segments` 和 `samples` 中，带有明确的 `is_pending_tail: true` 与 `uncommitted_snapshot: true` 语义标识；<br>3. `recordSample` 改在样本填满 `maxSamples` 时自然 flush，确保无论中间导出 0 次、1 次或频繁导出，分段结构与样本保留完全一致；<br>4. 保持所有存储数组严格有界，保留原始样本、摘要样本、丢弃计数和错误计数的严格区分；多次快照仅递增 `export_index`，不产生重复或遗漏，不污染后续采样。 | 在 `static/test/g0-diag.test.js` 中新增 5 组快照与容量回归全部通过：<br>1. `maxSamples=2, maxSegments=1` 下，Path A（sample→sample→export）与 Path B（sample→export→sample→export）结果完全一致（均保留 2 个原始样本，0 摘要，0 丢弃，`healthy: true`）；<br>2. 采样与导出交替进行，多次跨越段边界和覆盖边界，容量守恒不变；<br>3. 相同采样序列在 0 次导出与高频导出策略下，最终证据内容、样本列表与统计数据 100% 一致；<br>4. 无新样本时连续导出不改变控制器存储状态；<br>5. 停止后导出、错误响应后导出与容量耗尽后导出均符合定义。 |

### 命令与实际结果
- `npm run test:unit`（配置 `MWCP_GPP=g++`，MinGW g++ 13.3.0 在 PATH）：**94/94 passed**，退出码 0（原 78，Round 2 增 11，Round 3 增 5，合计 94 个单元测试全部通过）。
- `node --test test/g0-diag.test.js`：**33/33 passed**，退出码 0。
- `node --test test/g0-hello.test.js`：**2/2 passed**，退出码 0。
- `npm run test:browser`：**2/2 passed**，退出码 0（Chrome 155.0.8059.84，无 Node API 污染，快速失败保护有效）。
- `npm run build`：**passed**，退出码 0（Vite 8.3.1 生产构建成功，客户端各平台资源哈希打包完整）。
- C++ 宿主测试：
  - `mwcp_host_test`（`-std=c++14 -fno-exceptions -fno-rtti -static`）：**passed**，退出码 0，黄金向量 100% 匹配。
  - `g0_session_test`（`-std=c++14 -static-libgcc -static-libstdc++`）：**passed**，退出码 0。
  - `r60_probe_stats_test`（`-std=c++14 -static`）：**passed**，退出码 0。
- Python 验证：`python -m unittest discover -s tests -p test_releases.py -v`：**20/20 passed**，退出码 0。

### 未执行项目与受阻说明
- **Linux WSL / 远端 CI 状态**：
  - 本机 WSL 环境目前出现网络初始化错误（`CreateInstance/CreateVm/ConfigureNetworking/0x8007054f`），且本地 WSL 发行版缺少 Node.js 二进制，故本轮 Linux 环境下的 Node.js 单元测试明确标记为 **blocked / not_run**。
  - 严格遵循指令规则：未擅自推送代码或触发 GitHub Actions 远端工作流，绝不使用 Windows 本机测试结果冒充 Linux 通过。
- **物理硬件 G0-01～G0-05 状态**：
  - 维持 **not_run**。未经用户提供具体板卡型号、原生 USB 路径、接线引脚、端口 VID/PID 并给予明确操作授权，**严禁打开物理串口、严禁烧写、严禁擦除、严禁重启硬件**。软件模拟仿真绝不等于硬件 G0 验收。

### 固件哈希与源码快照
本轮仅修改前端诊断逻辑与测试用例，未改动固件 C++ 源码与 YAML 配置。第 20 节固件二进制哈希保持有效：
- Host OTA：`DF0DA7283D78E899B478F6092C125528964FABCED6FB4EF49F7B5ACDD8674026`
- Host factory：`72C87C3DB3AAEF9A9C1968F2994365230D63FF33B3D0F50BE7B52A725CE56DD6`
- Baseline OTA：`7E0B7077A8D8A0594184C7F46924BC0A05969BC583F2777E96E0ADDA6CB4D1B8`
- Baseline factory：`EDD243713F65C6B86DDA7642AF140898A24EABAD804A23E54B17AF14186BB21D`

工作区 `468b4144a0653c5adde66351a2d8f7e94a0763c8`，组件 `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b`，另有未提交修改。
按既定算法（对 76 个 G0 审查范围文件的 `sha256<空格>相对路径` 排序清单计算 SHA-256），最新源码快照哈希为：
**`242D8366DFA15E0A45AC0F4467AD24FFE7ED3649201CCB3758C353DB0675BAA2`**。

| 硬件项 | 状态 |
| --- | --- |
| G0-01 | not_run |
| G0-02 | not_run |
| G0-03 | not_run |
| G0-04 | not_run |
| G0-05 | not_run |

硬件前置条件同前，仍需用户确认具体板卡、原生 USB 路径、接线与串口授权。未获授权前不打开串口、不烧写、不擦除。协议未冻结，未提交、推送或发布，未推进 WP-2/WP-3。


