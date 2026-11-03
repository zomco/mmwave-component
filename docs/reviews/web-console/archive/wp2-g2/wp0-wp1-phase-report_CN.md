# WP-0 / WP-1 阶段报告

日期：2026-10-19（初版 2026-10-18）。工作包：WP-0、WP-1（含 G0 真机闭环与 G1 契约收口）。是否提交/发布：否。当前阶段结论：**G1 冻结候选，待独立验收（`DD-01`～`DD-15` 全部已收口，含用户已批准并落地的 `DD-07` C2 与 `DD-08` C2）**（第 1～20 节保留历史轮次记录；G0 真机验收与 G1 契约收口以第 21～22 节及 [`g0-evidence-index.json`](./g0-evidence-index.json) 为准）。

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
- **Windows 11 环境（Node v22.13.1, npm 11.17.0, MinGW g++ 13.3.0, Chrome 155.0.8059.84）**：
  - `npm run test:unit`（配置 `MWCP_GPP=g++`）：**94/94 passed**，退出码 0（原 78，Round 2 增 11，Round 3 增 5，合计 94 个单元测试全部通过）。
  - `node --test test/g0-diag.test.js`：**33/33 passed**，退出码 0。
  - `node --test test/g0-hello.test.js`：**2/2 passed**，退出码 0。
  - `npm run test:browser`：**2/2 passed**，退出码 0（Chrome 155.0.8059.84，无 Node API 污染，快速失败保护有效）。
  - `npm run build`：**passed**，退出码 0（Vite 8.3.1 生产构建成功，客户端各平台资源哈希打包完整）。
  - C++ 宿主测试：
    - `mwcp_host_test`（`-std=c++14 -fno-exceptions -fno-rtti -static`）：**passed**，退出码 0，黄金向量 100% 匹配。
    - `g0_session_test`（`-std=c++14 -static`）：**passed**，退出码 0。
    - `r60_probe_stats_test`（`-std=c++14 -static`）：**passed**，退出码 0。
  - Python 验证：
    - `python -m unittest discover -s tests -p test_releases.py -v`：**20/20 passed**，退出码 0。
    - `python -m unittest tests/unit/test_mwcp_sources.py -v`：**2/2 passed**，退出码 0。
- **Linux 环境（WSL2 Ubuntu-22.04 LTS, 内核 6.6.87.2-microsoft-standard-WSL2, Node v22.13.1, npm 10.9.2, g++ 13.3.0, Python 3.12.3, Chromium 155.0.8059.79 snap）真实执行**：
  - `npm ci`：按 `package-lock.json` 安装前端依赖完成，50 个包 0 漏洞。
  - `MWCP_GPP=g++ npm run test:unit`：**94/94 passed**，退出码 0（0 失败，0 跳过）。
  - `npm run test:browser`：**2/2 passed**，退出码 0（Chromium 155.0.8059.79 snap，非 root 运行，无 Node API 污染，快速失败保护有效）。
  - `npm run build`：**passed**，退出码 0（Vite v8.3.4 生产构建成功，资源哈希打包完整）。
  - C++ `mwcp_host_test protocol/fixtures/protocol-vectors.json`（`-std=c++14 -fno-exceptions -fno-rtti -static`）：**passed**，退出码 0。
  - C++ `g0_session_test`（`-std=c++14 -static`）：**passed**，退出码 0。
  - C++ `r60_probe_stats_test`（`-std=c++14 -static`）：**passed**，退出码 0。
  - Python `python3 -m unittest discover -s tests -p test_releases.py -v`：**20/20 passed**，退出码 0。
  - Python `python3 -m unittest tests/unit/test_mwcp_sources.py -v`：**2/2 passed**，退出码 0。

### 未执行项目与受阻说明
- **远端 GitHub Actions CI 状态**：
  - 严格遵循指令规则：未擅自推送代码或触发 GitHub Actions 远端工作流；因此远端 CI 维持待触发/待推送状态。本地已在 Windows 11 与 Linux (WSL2 Ubuntu 22.04) 双环境下真实执行全套单元测试、浏览器测试、生产构建、C++ 宿主测试与 Python 测试。
- **物理硬件实测执行（LuatOS ESP32C3-CORE + R60ABD1 真实硬件）**：
  - 经用户 4 项前置明确确认并授权：板卡型号为 LuatOS ESP32C3-CORE，原生 USB Serial/JTAG（`VID: 303A, PID: 1001`），串口 `COM9`；雷达 R60ABD1 接线确认（GPIO21 TX / GPIO20 RX）；专用测试板无需备份，授权烧写 `baseline.yaml` 与 `host.yaml` 及长测。
  - **G0-01 (USB 与雷达并行通信)**：**通过 (pass)**。原生 USB Serial/JTAG 成功建立 MWCP 会话；雷达在 GPIO20/21 正常通信，`radar_link: "healthy"`，5 秒采样内雷达有效帧数从 796 增至 822（帧率 ~5.7 Hz），解析错误数 0，活跃目标数持续刷新，`origin != simulation`。
  - **G0-02 (USB 所有权与纯净性)**：**通过 (pass)**。烧录 `host.yaml` 产物后监听稳态 USB 字节流，捕获 0 字节非协议输出；无纯文本日志混入，无 Improv 争用；状态返回 `usb_exclusive: true`，`usb_install_err: 0`。
  - **G0-05 (资源与运行时开销对比)**：**通过 (pass)**。在同一物理硬件上分别烧录运行 `baseline.yaml` 与 `host.yaml` 并读取真实运行时数据：
    - 运行时 Free Heap：Baseline `212,476 B` vs Host `192,868 B`（差值 `19,608 B` ≈ 19.15 KiB，满足 `<= 24,576 B`（24 KiB）硬上限，见 `g0-evidence-index.json` `gates.G0-05.metrics`）；
    - 最大连续空闲块：两者均为 `114,688 B`（单时间点相等，不能单独证明无碎片化，见 22.2 节澄清 2）；
    - FreeRTOS Stack 高水位：Baseline `6,172 B` vs Host `2,908 B`（ESP-IDF RISC-V 1 字节/单位，剩余安全裕度 $> 2.9$ KiB）；
    - Loop 最大延时：Baseline `3,162 us` vs Host `2,676 us`（均 $< 4$ ms，远低于 16 ms 预算上限）；
    - 雷达通信：两者均保持 `healthy`，0 解析错误。
  - **G0-03 (无网络 2 小时长测)**：**通过 (pass)**。在脱机无网络配置（`reboot_timeout: 0s`）下真实执行 7,200 秒（120 分钟）连续全自动采样：
    - 连续 7,198 次 1 Hz 采样全数成功响应（7,198/7,198，成功率 100.00%，错误响应数 0）；
    - 全程未发生意外重启（`reboot_detected: false`，`boot_id: dcda0cf8f2741d72537c31049c579aea` 全程绝对一致）；
    - 系统运行时长 `uptime_ms` 从 28,645 ms 单调递增至 7,228,453 ms（净增 7,199,808 ms）；
    - 雷达持续稳定接收并解析 34,878 帧（有效帧数从 148 稳步增至 35,026，平均帧率 ~4.84 Hz），解析错误数全程为 0，连接状态全程保持 `healthy`；
    - 内存消耗恒定：Free Heap 起止均为 192,864 B（范围 `192,672..194,672 B`，净漂移 0 B），栈高水位最小剩余 2,844 字节，主循环最大延时峰值 4.535 ms（远低于 16 ms 预算上限）；
    - 完整非破坏性证据 JSON 存放于仓库外会话目录 `C:\Users\zomco\.gemini\antigravity\brain\def311e0-e1d9-4cb7-a5ea-9df7a0d0ff47\scratch\g0-03-evidence.json`（`3,498,699` 字节，SHA-256 见 22.2 节与 `g0-evidence-index.json`）；仓库内仅保存汇总与 5 个里程碑样本（未生成独立进度日志文件）。
  - **G0-04 (安装器到诊断页交接与 Web Serial)**：**通过 (pass)**。在 Chrome 155 浏览器通过 Web Serial 直连物理板卡原生端口（`COM9`）：
    - 完整走通 `selecting -> opening -> handshaking -> online -> online capture -> disconnecting -> closed` 全生命周期；
    - 断开与重连未触发任何 `InvalidStateError`，端口代际流锁正常释放；
    - 遥测样本进入非破坏性有界缓冲段（`segments` 与 `pending_tail`），导出的诊断数据符合协议 Schema。

### 固件哈希与源码快照
本轮仅修改前端诊断逻辑与测试用例，未改动固件 C++ 源码与 YAML 配置。第 20 节固件二进制哈希保持有效：
- Host OTA：`DF0DA7283D78E899B478F6092C125528964FABCED6FB4EF49F7B5ACDD8674026`
- Host factory：`72C87C3DB3AAEF9A9C1968F2994365230D63FF33B3D0F50BE7B52A725CE56DD6`
- Baseline OTA：`7E0B7077A8D8A0594184C7F46924BC0A05969BC583F2777E96E0ADDA6CB4D1B8`
- Baseline factory：`EDD243713F65C6B86DDA7642AF140898A24EABAD804A23E54B17AF14186BB21D`

工作区 `468b4144a0653c5adde66351a2d8f7e94a0763c8`，组件 `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b`，另有未提交修改。
按既定算法（对 76 个 G0 审查范围文件的 `sha256<空格>相对路径` 排序清单计算 SHA-256），最新源码快照哈希为：
**`242D8366DFA15E0A45AC0F4467AD24FFE7ED3649201CCB3758C353DB0675BAA2`**。

| 硬件项 | 状态 | 判定与直接证据 |
| --- | --- | --- |
| G0-01 | **pass** | 原生 USB Serial/JTAG 成功握手，R60ABD1 雷达稳定以 5.7 Hz 产出有效帧，0 解析错误，目标跟踪活跃 |
| G0-02 | **pass** | host 固件稳态 USB 0 字节非协议输出，无文本日志混入，`usb_exclusive: true`，`usb_install_err: 0` |
| G0-03 | **pass** | 2 小时脱机长测 7,198/7,198 响应全部成功（100%），0 重启（boot_id 一致），雷达有效帧净增 34,878 帧（`0x80/0x05` 坐标帧净增 3,599 帧 = 0.50 Hz），堆内存起止恒定 192,864 B（范围 `192,672..194,672 B`，净漂移 0 B） |
| G0-04 | **pass** | 真实 Chrome 155 浏览器 Web Serial 在 `g0-diag.html` 上完成连接/握手/在线采集/断开/重连完整闭环，无 `InvalidStateError`（注：`esp-web-tools` 安装器弹窗 5 分支 UI 端到端留待 WP-3 / B-04 / G3 / G4 验证） |
| G0-05 | **pass** | 同板实测（数值与 `g0-evidence-index.json` `gates.G0-05.metrics` 一致）：编译期 Flash 增量 `+2,292 B`（`767,502 − 765,210`，预算 `<= 92,160 B`），OTA/factory bin 增量均为 `+2,288 B`；编译期 RAM 增量 `+17,524 B`（`.dram0.bss` `+17,704 B`）；运行时 Free Heap 差值 `19,608 B`（`212,476 − 192,868`，硬上限 `<= 24,576 B`）；栈高水位 2 小时最小剩余 `2,844 B`（预算 `>= 2,048 B`）；loop 最大延时 2 小时峰值 `4,535 us`（目标 `<= 8,000 us`，硬上限 `16,000 us`） |

---

## 22. WP-1 / G1 协议契约收口、覆盖矩阵与 WP-2/WP-3 接口交接清单

### 22.1 阶段结论与基线状态

- **阶段评审状态**：**G1 整改候选，待独立复核（已完成 G1-R1～G1-R5 全部整改与回归）**
- **严正边界声明**：
  - 本阶段完成了 G0 真机验证证据固化、组件仓库自包含规范（中英文）、设计差异分类台账（`DD-01`～`DD-15`）、24 个命令/事件的全覆盖 Schema 与模拟器契约闭环，以及 C++14 主机 10 万次确定性变异模糊测试（`P-14`，紧凑缓冲 + ASan/UBSan 严格无越界验证）。
  - **模拟器与契约测试通过不等于生产固件功能已完成**：WP-2 生产服务层（`ConfigService` 双槽 NVS、`JobService`、`WiFiService`、生产 `R60Adapter`）与 WP-3 正式前端控制台尚未开始实现。
  - **C 类决策项（`DD-07`、`DD-08`）已由用户明确拍板并完成三端落地**：
    1. **`DD-07`（采用选项 C2）**：依据 G0-03 2 小时真机长测（`3,599` 帧 / `7,199.8 s` = `0.50 Hz`），将 `r60abd1-capabilities.json` 与 `simulator.js` 中的 `position.xy` 设为 `"expected_interval_ms": 2000, "stale_after_ms": 6000`；其余未单独分桶计数的字段保持 `null`。
    2. **`DD-08`（采用选项 C2：同步放宽上限至 `50..600 cm`）**：同步将 `docs/protocol/fixtures/r60abd1-capabilities.json`、`static/src/protocol/simulator.js` 与 `tests/common/r60abd1.yaml`（`num_radar_z`）中的安装高度范围统一为 `50..600 cm`（step `1`）。

| 基线维度 | 核实值 |
| :--- | :--- |
| 工作区 HEAD | `86fc3ea156a13df3410a9fec619a7a7e72203fb6`（`86fc3ea`，较早期 `4847402` 的推进为用户提交的外壳更新；本任务未触碰 `cases/` 或其他子模块） |
| `submodules/mmwave-component` HEAD | `9a524b8e8b02ffb496d808250567d7169fe264d5`（`9a524b8`） |
| `submodules/mmwave-card` HEAD | `5799d5729dd8bf6ee6114038bc989c2be1a35cf0`（`5799d57`，只读未改） |
| G0 收尾基线 76 文件源码快照 SHA-256 | `242D8366DFA15E0A45AC0F4467AD24FFE7ED3649201CCB3758C353DB0675BAA2` |
| G1 整改后 76 文件源码快照 SHA-256 | **`FE6391B1787574D0DA4E12D0B95A20AD075D7A7A7D4D1FC64EE6B14502589030`** |
| 协议黄金向量（双端同源） | `docs/plans/mmwave-web-console/protocol-vectors.json` 与 `submodules/mmwave-component/protocol/fixtures/protocol-vectors.json` 逐字节一致（由 `test_mwcp_sources.py` 强制校验） |

---

### 22.2 G0 真机验证证据索引与三项关键技术澄清（工作项 A）

所有 G0 硬件实测元数据、编译工具链版本、固件二进制 SHA-256、G0-01～G0-05 实测指标及 2 小时长测里程碑样本均已固化至可复核索引文件：
- **证据索引文件**：[`docs/reviews/web-console/g0-evidence-index.json`](./g0-evidence-index.json)
- **2 小时长测原始采样文件**：`C:\Users\zomco\.gemini\antigravity\brain\def311e0-e1d9-4cb7-a5ea-9df7a0d0ff47\scratch\g0-03-evidence.json`（`3,498,699` 字节，SHA-256：`075451aaac7d63afc0d75a88812af85fad0e5cea8d64d88901d60fa7291561f8`）

#### 三项强制技术澄清（防误读边界）
1. **雷达总帧率（`radar_frames`）与单字段更新周期（`radar_targets`）的严格区分**：
   - 在 G0-03 连续 `7,199.8 s`（`7,198` 个采样点）中，`R60ProbeStats::valid_frames`（`radar_frames`）从 `148` 增至 `35,026`（净增 `34,878` 帧，均值 **`4.84 Hz`**，范围 `4..8 帧/秒`）。该计数汇总了 R60ABD1 串口上的**所有合法控制字**（心跳、存在 `0x80/0x01`、运动 `0x80/0x02`、体动 `0x80/0x03`、距离 `0x80/0x04`、2D 坐标 `0x80/0x05`、呼吸、心率、睡眠）。
   - 相比之下，`R60ProbeStats::target_observations`（`radar_targets`）**仅统计 `0x80/0x05` 2D 坐标帧**，在 `7,199.8 s` 内从 `14` 增至 `3,613`（净增 `3,599` 帧），对应硬件上报周期严格为 **`2,000 ms`（`0.50 Hz`）**，且固件 `R60ABD1Component::publish_position_()` 另有 `1,000 ms` 发布节流。
   - **结论**：绝不能将 `~4.84 Hz` 的全串口帧率等同于 `position.xy`、`presence`、`breath_rate` 或 `heart_rate` 的单字段更新率。
2. **单时间点 `largest_free_block` 相等与长期内存碎片证明的边界**：
   - G0-05 单点快照中 Baseline 与 Host 的 `largest_free_block` 均为 `114,688 B`，结合 G0-03 连续 2 小时 `free_heap` 起止均为 `192,864 B`（波动范围 `192,672 .. 194,672 B`，净漂移 `0 B`），证明采用静态有界缓冲的 G0 探针在 2 小时内无内存泄漏。
   - 但单时间点 `largest_free_block` 相等本身并不能证明在任意动态堆分配下不存在碎片；因此 WP-2 生产固件必须继续保持静态/固定容量缓冲与每帧零堆分配（Zero Per-Frame Heap Allocation）。
3. **诊断页 Web Serial 闭环与 `esp-web-tools` 安装器 5 分支 UI 的边界**：
   - G0-04 真机已在 Chrome `155.0.7632.160` 下通过 `g0-diag.html` 验证了真实硬件 Web Serial 打开、握手、5Hz 连续采集、断开与立即重连，且单元测试（`flash-handoff.test.js`、`g0-diag.test.js`）验证了端口释放状态机。
   - 但 `esp-web-tools` 安装器弹窗的 5 个完整 UI 分支（安装成功转控制台、安装失败、用户取消、关闭弹窗、安装中途物理拔线）尚未在正式控制台 UI 上执行真机端到端验证，仍作为 WP-3 / B-04 / G3 / G4 的必测验收项。

---

### 22.3 G1 协议与契约覆盖矩阵（交付物 5）

| 计划编号 | 要求摘要 | 规范章节 (`docs/protocol/README_CN.md`) | Schema / 黄金向量 / Fixture | JS 测试文件 (`static/test/`) | C++ / Python 测试文件 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P-01** | `CRC32C (Castagnoli)` 标准串 `"123456789"` 校验值为 `0xe3069283`（小端 `83 92 06 e3`） | 第 2.3 节 | `protocol-vectors.json` (`crc32c_check`) | `protocol-codec.test.js` | `protocol/cpp/mwcp_host_test.cpp` | **已通过 (双端)** |
| **P-02** | 黄金向量（HELLO 请求/响应、含中文 UTF-8 帧、254B COBS 分段帧）逐字节编解码一致 | 第 2.1～2.3 节 | `protocol-vectors.json` (`frames`, `cobs_vectors`) | `protocol-codec.test.js` | `protocol/cpp/mwcp_host_test.cpp`、`test_mwcp_sources.py` | **已通过 (双端)** |
| **P-03** | 单字节流式送入、1..100B 伪随机切块、10 帧连续粘包、连续空分隔符 `0x00` 恢复 | 第 2.1、2.3 节 | `protocol-vectors.json` | `protocol-codec.test.js` | `protocol/cpp/mwcp_host_test.cpp` (`test_sticky_10_frames_and_100k_mutations`) | **已通过 (双端)** |
| **P-04** | 启动垃圾字节、坏 COBS、坏 CRC32C、坏 magic/version/kind/flags 静默丢弃并计错，紧随合法帧正常恢复 | 第 2.3 节 (`DD-09`) | `mwcp-v1.schema.json` | `protocol-codec.test.js` | `protocol/cpp/mwcp_host_test.cpp` | **已通过 (双端)** |
| **P-05** | `MAX_PAYLOAD = 4096 B` 精确接受，`4097 B` 拒绝（`payload_too_large`），`MAX_COBS = 4141 B` 溢出丢弃至下一 `0x00` | 第 2.3 节 | `mwcp-v1.schema.json` | `protocol-codec.test.js`、`protocol-schema.test.js` | `protocol/cpp/mwcp_host_test.cpp` | **已通过 (双端)** |
| **P-06** | 半帧 `HALF_FRAME_MS = 2000 ms` 超时丢弃缓冲并计 `timeouts`，后续合法帧恢复 | 第 2.3 节 | — | `protocol-codec.test.js` | `protocol/cpp/mwcp_host_test.cpp` | **已通过 (双端)** |
| **P-07** | 严格 UTF-8 与 JSON 约束：深度 `<=8`、键数 `<=64`、数组 `<=256`、无 BOM、拒绝字面与 `\uXXXX` 转义等价重复键 (`DD-13`)、拒绝超出 `±(2^53-1)` 的整数与指数整数 (`DD-14`)、binary64 溢出阈值一致 | 第 2.4 节 (`DD-13`, `DD-14`) | `json-cases.json`、`double-overflow-threshold.txt` | `protocol-codec.test.js`、`protocol-h-fixes.test.js` | `protocol/cpp/mwcp_host_test.cpp` | **已通过 (双端)** |
| **P-08** | `HELLO` 握手版本协商、`nonce`/`boot_id` 32 位小写 hex、`max_payload < 4096` 返回 `LIMIT_UNSUPPORTED`、主版本不兼容返回 `VERSION_UNSUPPORTED` | 第 3.1 节 | `mwcp-v1.schema.json` (`helloRequest`, `helloResult`) | `protocol-session.test.js`、`g0-hello.test.js` | `protocol/cpp/g0_session_test.cpp` | **已通过 (双端 + 真机 G0-01)** |
| **P-09** | 4 槽响应去重缓存：同 `request_id`+同内容重放缓存；同 ID 不同内容返回 `ID_REUSE`；已滑出窗口旧 ID 返回 `REQUEST_EXPIRED` | 第 3.2 节 | `mwcp-v1.schema.json` (`errorEnvelope`) | `protocol-session.test.js`、`protocol-regression.test.js` | —（WP-2 固件服务层将移植） | **已通过 (JS 契约/模拟器)** |
| **P-10** | 会话 `session_ttl_ms = 15000`、`PING` 5s 续期、设备 `event` 不自续期、后台时钟挂起恢复后过期重握手、`SESSION_CLOSE` 正常关闭 | 第 3.2～3.3 节 | `mwcp-v1.schema.json` | `protocol-session.test.js`、`protocol-f-fixes.test.js`、`protocol-g-fixes.test.js` | `protocol/cpp/g0_session_test.cpp` | **已通过 (JS + C++ G0)** |
| **P-11** | 分页读取（`CAPABILITIES_LIST`、`CONFIG_READ`、`ACTIONS_LIST`、`WIFI_SCAN_RESULTS`）与中途 `revision` 变化触发 `REVISION_CONFLICT` | 第 5.1 节 | `mwcp-v1.schema.json` | `protocol-session.test.js`、`protocol-schema.test.js` | — | **已通过 (JS 契约/模拟器)** |
| **P-12** | 事件速率限制、`event_budget_bps (1000..8000)` 字节预算、控制响应高于事件优先级、遥测合并计数 `telemetry_coalesced` 与日志丢弃 `logs_dropped` | 第 5.2 节 | `mwcp-v1.schema.json` | `protocol-f-fixes.test.js`、`protocol-g-fixes.test.js`、`protocol-session.test.js` | `protocol/cpp/g0_session_test.cpp` | **已通过 (JS + C++ G0)** |
| **P-13** | 请求速率限制（10 RPC/s）与持久化写令牌桶耗尽返回 `RATE_LIMITED`（含 `retry_after_ms`） | 第 3.4 节 | `mwcp-v1.schema.json` | `protocol-session.test.js` | — | **已通过 (JS 契约/模拟器)** |
| **P-14** | 确定性伪随机种子（`0x5eed1234`）**100,000 次变异输入模糊测试**（紧凑缓冲分配 + ASan/UBSan，覆盖帧解析器 `mwcp::Parser` 与 JSON 校验器 `mwcp::json_check`），0 越界、0 崩溃、状态有界、变异后立即可恢复解析合法帧 | 第 2.3～2.4 节 | `protocol-vectors.json` | `MWCP_GPP=g++ npm run test:unit` | `protocol/cpp/mwcp_host_test.cpp` (`test_sticky_10_frames_and_100k_mutations`) | **已通过 (C++14 100,000 次变异 + ASan/UBSan)** |
| **T-02..T-10** | 遥测快照结构、`source_seq`、`sent_ms`/`sample_ms` 年龄估算、`origin` 标记、`quality` (`unknown/unsupported/invalid` 强制 `value: null`)、1D `range_cm` vs 2D `local_cm/room_cm` 禁止混用、R60 `speed_cm_s: null` (`DD-06`)、`position.xy` `2000/6000 ms` (`DD-07` C2)、3D 旋转矩阵与多边形射线法边缘点归属 (`DD-11`) | 第 5.2 节 | `mwcp-v1.schema.json`、`protocol-vectors.json`、`r60abd1-capabilities.json` | `protocol-coordinates.test.js`、`protocol-schema.test.js`、`protocol-g-fixes.test.js` | `protocol/cpp/mwcp_host_test.cpp`、`test_rotation_convention.py` | **已通过 (JS + C++ + Python)** |
| **C-01..C-12** | 配置读取、`CONFIG_VALIDATE` 无副作用、未知字段拒绝 (`UNKNOWN_FIELD`)、数值越界拒绝 (`OUT_OF_RANGE`，含 `install.z_cm` `50..600 cm` `DD-08` C2)、多边形几何校验（自交/零面积/重复闭合点整笔拒绝 `DD-05`）、`base_revision` 冲突 (`REVISION_CONFLICT`)、`op_id` 幂等重放与 `OP_ID_REUSE`、`COMMIT_STATUS` 查询 | 第 5.3 节 | `mwcp-v1.schema.json` | `protocol-schema.test.js`、`protocol-session.test.js`、`protocol-h-fixes.test.js` | —（WP-2 固件实现） | **已通过 (JS 契约/模拟器)** |
| **C-13** | **最大有效 R60 配置提交容量证明**：含全部 R60 主机配置项（`install.z_cm = 600`）及几何合法的 64 顶点凸多边形（`polygonIssues === []`）完整 `CONFIG_COMMIT` 通过 Schema、模拟器与帧编码（`~1.15 KiB <= 4096 B`） | 第 5.3 节 (`DD-04`, `DD-08`) | `mwcp-v1.schema.json`、`r60abd1-capabilities.json` | `protocol-schema.test.js` | — | **已通过 (JS 契约/模拟器)** |
| **C-14** | 64-bit `revision` 十进制字符串单调递增（含超大 `uint64` 不精度丢失） | 第 2.4、5.3 节 | `mwcp-v1.schema.json` | `protocol-g-fixes.test.js` | — | **已通过 (JS 契约/模拟器)** |
| **A-01..A-03** | 动作列表、高风险动作 `confirm === action_id` 校验、同资源锁互斥返回 `BUSY`、`op_id` 去重、`verification: "none"` 返回 `verified: false`、`device.restart` 后 `boot_id` 变化重握手恢复 | 第 5.4 节 | `mwcp-v1.schema.json`、`r60abd1-capabilities.json` | `protocol-schema.test.js` | — | **已通过 (JS 契约/模拟器)** |
| **W-01..W-04** | `WIFI_STATUS` 永不返回密码、`WIFI_SCAN` + `WIFI_SCAN_RESULTS` 按信号强度降序分页与 64 条截断、`WIFI_PROVISION` (`open` 空密码 / `wpa2_psk` 8..63 UTF-8 字节或 64 hex)、多字节中文 SSID `x-maxUtf8Bytes: 32` 限制、全链路零密码回显 | 第 5.4 节 (`DD-10`) | `mwcp-v1.schema.json` | `protocol-schema.test.js` | — | **已通过 (JS 契约/模拟器)** |
| **S-01..S-04** | 请求拒绝未知字段 (`UNKNOWN_FIELD`)、响应/事件 `x-open-object: true` 忽略未知字段 (`DD-15`)、禁止 `__proto__`/`constructor` 原型污染、生产排除 `AUTH_REQUIRED`/`inject_mock_data`/`raw_uart_tx` | 第 2.4、3.4 节 (`DD-15`) | `mwcp-v1.schema.json` | `protocol-schema.test.js`、`protocol-g-fixes.test.js` | — | **已通过 (JS 契约/模拟器)** |
| **G0-01..G0-05** | LuatOS ESP32C3-CORE (`USB\VID_303A&PID_1001`) + R60ABD1 真机并行通信、USB 独占零杂散日志、2 小时 `7,198` 样本脱机长测零重启零泄漏、Chrome 155 Web Serial 诊断页重连、资源开销对比 | 第 1.2、5.2 节 | [`g0-evidence-index.json`](./g0-evidence-index.json) | `g0-diag.test.js`、`g0-hello.test.js` | `g0_session_test.cpp`、`r60_probe_stats_test.cpp` | **已通过 (真机实测 + 双平台回归)** |

---

### 22.4 WP-2（固件服务层）与 WP-3（前端控制台）接口交接清单（交付物 6）

为确保 G1 验收后 WP-2 与 WP-3 可并行无歧义推进，各模块职责边界与硬约束冻结如下：

| 模块名称 | 归属工作包 | 负责协议命令 / 事件 | 持久化、幂等与并发约束 | 缓冲与内存上限（ESP32-C3 硬预算） | 严禁事项（红线） | G2 / G3 必测验收项 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`HostLink` & `SessionService`** | WP-2 (固件) | `HELLO (0x0001)`、`PING (0x0002)`、`SESSION_CLOSE (0x0003)` | 单活跃会话；`boot_id` 每次启动由硬件 RNG 生成 32 位小写 hex；4 槽 `(request_id, code, sha256, resp)` 去重缓存；`15,000 ms` TTL；10 RPC/s 限流 | 静态 RX COBS 缓冲 `4,143 B`；静态 TX 帧缓冲 `4,143 B`；64B 分块非阻塞 `tx_pump`（连续零写 `250 ms` 放弃并标记帧重同步）；每帧 **0 堆分配** | 严禁在 `USB_SERIAL_JTAG` 上阻塞写等待宿主读取；严禁启用 stock `improv_serial` 或串口明文 `logger`；严禁让 `event` 自续期会话 | `G2-01` 真机握手、重传去重、`ID_REUSE`、`REQUEST_EXPIRED`、DTR 挂起不阻塞雷达 `loop()` |
| **`CapabilitiesService` & `StatusService`** | WP-2 (固件) | `DEVICE_INFO (0x0010)`、`CAPABILITIES_LIST (0x0011)`、`STATUS_GET (0x0012)`、`STATUS_CHANGED (0x8002)` | `CAPABILITIES_LIST` 静态只读表分页输出，游标绑定构建期 `cap_revision`；`STATUS_GET` 实时汇报 `uptime_ms`、`radar_link`、`config_revision`、`config_storage` 与 9 项标准 `counters` | 描述符存放于 Flash (`rodata`)，不占用静态/动态 RAM | 严禁把“当前无目标 (`targets: []`)”判为 `radar_link: "error"`；严禁硬编码假固件版本或根据 USB VID/PID 伪造 `radar_identity` | `G2-02` R60 真机能力分页读取与 `r60abd1-capabilities.json` 一致性核对 |
| **`TelemetryService` & `R60Adapter`** | WP-2 (固件) | `SUBSCRIBE (0x0030)`、`UNSUBSCRIBE (0x0031)`、`TELEMETRY (0x8001)` | 新会话默认无订阅；支持 `1..20 Hz` 速率上限与 `1,000..8,000 bps` 字节预算；观测未变化不伪造新 `source_seq` | 遥测发送队列深度 `= 1`（仅保留最新快照，覆盖时递增 `telemetry_coalesced`） | 严禁把 R60 占位速度 `0` 导出为 `speed_cm_s: 0`（必须为 `null`，`DD-06`）；严禁通过解析文本日志或双消费者抢读 UART 获取雷达数据 | `G2-03` R60 真机 2D 坐标、存在、呼吸/心率独立时间戳与房间变换一致性验证 |
| **`ConfigService`** | WP-2 (固件) | `CONFIG_READ (0x0020)`、`CONFIG_VALIDATE (0x0021)`、`CONFIG_COMMIT (0x0022)`、`COMMIT_STATUS (0x0023)`、`CONFIG_CHANGED (0x8003)` | **双槽原子持久化**（完整快照 + `schema_version` + `CRC32C` + 单调 `uint64` 十进制 `revision`）；保留最近 4 次 `(op_id, sha256, revision)`；共享写令牌桶（容量 32，恢复 1/s）；一次性迁移旧 `globals` | 固定大小结构体快照（支持 64 顶点 `int16_t` 多边形，脱离旧 254B 字符串 `g_polygon` 限制，`DD-04`） | 严禁先改运行态再写 NVS；严禁双槽损坏时静默重置为出厂配置（必须进 `recovery_required`）；严禁跳过多边形坏点或放行自交多边形（`DD-05`） | `G2-04` 64 顶点最大 R60 配置提交、掉电/重启持久化恢复、`REVISION_CONFLICT`、HA 卡片与控制台双向同步 |
| **`JobService`** | WP-2 (固件) | `ACTIONS_LIST (0x0040)`、`ACTION_START (0x0041)`、`JOB_GET (0x0042)`、`JOB_CHANGED (0x8004)` | 资源锁（`wifi`、`radar`、`restart`）同资源最多 1 个活动任务（冲突返 `BUSY`）；`confirm === action_id` 校验；任务容量预留不变量：`保护期内已完成记录数 + 活动任务预留数 <= 8`（总任务记录数始终 `<= 8`）；严格准入顺序：1. `op_id` 幂等复核优先（同负载即便满容量亦返回原 `job_id`，不同负载返 `OP_ID_REUSE`）；2. 资源互斥检查；3. 容量检查满容量立即返回 `BUSY`（`{ reason: "capacity", retry_after_ms: 1000 }`）且**零副作用**（Wi-Fi `state`/`ssid` 不变，不占锁不发事件）；4. 检查全过方可变更状态与受理任务；已完成任务上限 8 条摘要，按完成时间排序（completion-order FIFO）管理；保护条件为 `elapsed < 300,000 ms`（严禁提前淘汰）；自然回收条件为 `elapsed >= 300,000 ms`（达到或超过 300,000 ms 释放槽位；精确边界：`299,999 ms` 受保护，`300,000 ms` 与 `300,001 ms` 均可回收，未过期记录不受影响）；重启清空易失任务与锁，生成全新 32 位 hex `boot_id` | 静态有界任务历史表（最多保留最近 `8` 条已完成任务摘要，严格满足 `保护期内已完成数 + 活动预留数 <= 8`，活动任务绝不被淘汰） | 严禁对 `verification: "none"` 的动作宣称硬件已验证（以 `verified: false` 结束）；严禁在 `device.restart` 重启前置为 `succeeded` | `G2-05` `device.restart` 与 `radar.reset_module` 真机执行、并发 `BUSY`、完成历史 5 分钟保护（< 300000ms）与自然回收（>= 300000ms）、容量预留准入控制、重启 `boot_id` 变化确认 |
| **`WiFiService`** | WP-2 (固件) | `WIFI_STATUS (0x0050)`、`WIFI_SCAN (0x0051)`、`WIFI_PROVISION (0x0052)`、`WIFI_SCAN_RESULTS (0x0053)` | 扫描最长 15s，结果按 `rssi_dbm` 降序分页；配网最长 60s（保存旧凭据引用→尝试连接→获 IP→持久化→成功；失败回滚旧网络） | 扫描结果有界缓冲最多 `64` 条 AP 记录；密码仅存于带显式清零的临时缓冲 | **绝对禁止**在任何响应、事件、日志、错误或缓存中回显 `password`；严禁将不支持的加密方式降级为 `open`；严禁无 Wi-Fi 时触发 `reboot_timeout` | `G2-06` 真机 AP 扫描分页、正确密码配网成功、错误密码回滚且 USB 会话不中断、全链路零密码泄露检查 |
| **`LogService`** | WP-2 (固件) | `LOG (0x8005)`（经 `SUBSCRIBE` `logs` 流控制） | 默认关闭；最高默认级别 `info`；`debug` 最长开启 60s 自动回退 `info`；进入缓冲前执行敏感信息脱敏 | 静态环形缓冲（有界固定槽位，满时丢弃最旧并累加 `dropped_before` / `logs_dropped`） | 严禁诊断日志触发递归日志死循环；严禁输出明文 Wi-Fi/API/OTA 密钥 | `G2-07` 日志订阅开关、环形缓冲溢出 `dropped_before` 计数与脱敏验证 |
| **`ProtocolClient` / Console Store / Flash Handoff** | WP-3 (前端) | 全部 19 个命令与 5 个事件 | 单在途 RPC 队列；5s 心跳 `PING`；按 `boot_id` 检测设备重启并清空草稿重读；烧录交接仅以自身 `await port.open()` 成功为准（`DD-01`） | 遥测与日志 UI 采用有界环形数组与非破坏性导出快照（沿用 G0-U3 模版） | 严禁根据 `model_id` 硬编码未在 `CAPABILITIES_LIST` 声明的控件；严禁在 `CONFIG_COMMIT` 超时后自动换新 `op_id` 重发；严禁把未保存草稿伪装成设备权威输出 | `G3-01..G3-06` 完整控制台 UI、图形化多边形编辑、烧录交接 5 分支、中英文 i18n 与无障碍验收 |

---

### 22.5 本轮双平台实测命令与结果分类记录

严格区分本轮实际运行、此前通过和未重跑项目：

1. **本轮实际运行项目（当前边界加固与测试固化轮次）**：
   - **Windows 11 环境（Node v22.13.1, MinGW g++ 13.3.0, Python 3.12, Chrome 155）**：
     - `$env:MWCP_GPP="D:\Build\mingw64\bin\g++.exe"; npm run test:unit`：**全量单元测试套件全部通过**（基线更新为 **106 / 106 passed**，退出码 `0`，涵盖全部 24 命令/事件 Schema 正反例校验、64 顶点凸多边形最大 R60 配置提交、`4096B/4097B` 边界、`DD-07` C2、`DD-08` C2 `50..600 cm`、`A-01..A-03`、`W-01..W-04`、`P-03` 粘包联调，以及 G1-R1～G1-R5 专属回归用例；特别固化了 **G1-R2-A 3 项受控时钟精确边界测试**：`299999ms` 受保护满载拒新、`300000ms` 原记录可自然回收且新任务可受理、`300001ms` 持续可回收且未过期记录不受影响，以及 G1-R2-B 重启后任务总数 `<= 8` 条断言）。
     - `npm run test:browser`：**2 / 2 passed**，退出码 `0`。
   - **Linux 环境（WSL2 Ubuntu 22.04 LTS, Node v22.13.1）**：
     - `node --test test/protocol-schema.test.js`：**14 / 14 passed**，退出码 `0`（完整通过包含 G1-R2-A 3 项精确边界和 G1-R2-B `<= 8` 条内存断言在内的全部协议 Schema/任务用例）。

2. **此前通过验证项目（在 G0/G1 前序整改中已独立验证通过，保持无回退）**：
   - `npm run build`：生产打包通过（Vite v8.3.4，退出码 `0`）。
   - C++14 宿主测试（`-std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror -static`）：
     - `mwcp_host_test`（含黄金向量、`P-03` 10 帧粘包与 1..100B 随机切块、`P-14` **100,000 次确定性变异模糊测试**）：**`mwcp c++ host test passed`**，退出码 `0`（WSL2 下 ASan/UBSan `-fsanitize=address,undefined` 验证零越界零泄漏）。
     - `g0_session_test`：**`g0 session test passed`**，退出码 `0`。
     - `r60_probe_stats_test`：**`g0 probe host test passed`**，退出码 `0`。
   - Python 单元测试：
     - `python -m unittest discover -s submodules/mmwave-component/tests -p "test_releases.py" -v`：**20 / 20 passed**，退出码 `0`。
     - `python -m unittest discover -s tests/unit -p "test_*.py" -v`（含 `test_mwcp_sources.py`、`test_rotation_convention.py` 等）：**239 / 239 passed**，退出码 `0`。

3. **未重跑项目**：
   - **G0 硬件真实串口测试**：遵照红线约束（严禁操作真实物理串口、严禁烧写/重启/擦除物理设备），本轮未连接串口或烧录硬件，不默认重跑已完成并通过独立验收的 G0 物理长测。

---

## 23. G1 验收整改（G1-R1～G1-R5）问题归因、修复矩阵与复核判定

### 23.1 R1～R5 整改矩阵

| 缺陷编号 | 问题本质与归因 | 修改文件清单 | 回归测试名称 | 实测命令与结果 | 遗留限制与边界说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **G1-R1** | **契约多源分歧与未决语义**：`areas.definitions` 槽结构在模拟器（`area.slots`）与 Schema 命名脱节；`radar.reset_module` 与模拟器残留 `radar.reinitialize` / `wifi.clear` 动作命名冲突；`confirm` 语义在 Schema 允许布尔但文档要求精确等于 `action_id`；R60 安装角度步长与范围在文档、模拟器与真实固件间存在分歧。 | `docs/protocol/fixtures/r60abd1-capabilities.json`<br>`docs/protocol/schema/mwcp-v1.schema.json`<br>`static/src/protocol/schema.js`<br>`static/src/protocol/geometry.js`<br>`static/src/protocol/contract.js`<br>`static/src/protocol/simulator.js`<br>`docs/protocol/README_CN.md`<br>`docs/protocol/README.md`<br>`docs/protocol/design-differences_CN.md`<br>`docs/protocol/design-differences.md` | `static/test/protocol-schema.test.js`：<br>`G1-R1 regression: R60 capabilities/config/actions match fixture and confirm requires exact action_id string` | `npm run test:unit`（全量套件通过）：<br>- CAPABILITIES_LIST 分页与 fixture 完全一致；<br>- ACTIONS_LIST 仅声明 `device.restart` 与 `radar.reset_module`；<br>- `confirm` 传 `null/false/true/错字符串` 均返回 `INVALID_ARGUMENT`，精确匹配 `action_id` 始可启动。 | 模拟器已严格对齐 R60 8 项配置与 2 项支持动作；生产固件服务层（WP-2）实现时须保持此一契约，严禁自行扩展未在契约内声明的动作。 |
| **G1-R2** | **模拟器假实现、任务容量预留缺失与生命周期缺陷（R2-A/R2-B）**：<br>1. **容量准入与5分钟保护期破坏（R2-A终版整改与精确边界固化）**：上一轮整改虽然调整了淘汰顺序，但 `trimCompletedJobs()` 超过 8 条时直接 `shift()`，且 `createJob()` 未做容量准入检查；上一轮回归测试第 599～602 行甚至断言了“5分钟内第9个任务可以淘汰第1个任务”的错误预期；导致 5 分钟内连续完成 8 个任务后再启动新任务被错误放行（活动加完成总数达 10 条超界），新任务完成后仅耗时十数秒的最早记录即被非法淘汰，`JOB_GET` 变为 `unknown`，原 `op_id` 重试导致重复执行；<br>2. **重启生命周期泄漏（R2-B）**：模拟器重启仅按当前 boot 过滤，未清空旧 boot 任务，15 次重启累积 24 条记录产生无界增长；`boot_id` 未生成全新不重复随机值；<br>3. **虚假完成与验证越权**：`device.restart` 宣称 `verification: "none"` 却在重启前虚假报告 `succeeded`。 | `static/src/protocol/simulator.js`<br>`docs/plans/mmwave-web-console/implementation-handoff.md`<br>`docs/protocol/README_CN.md`<br>`docs/protocol/README.md` | `static/test/protocol-schema.test.js`：<br>- `G1-R2 regression: active job is never evicted by completed jobs and preserves resource lock`<br>- `G1-R2-A regression: completed jobs FIFO by completion order, 5-minute retention window, failed jobs and session reconnection`<br>- `G1-R2-A exact boundary: oldest completed record at elapsed 299999 ms with a controlled clock`<br>- `G1-R2-A exact boundary: oldest completed record at elapsed 300000 ms with a controlled clock`<br>- `G1-R2-A exact boundary: oldest completed record at elapsed 300001 ms with a controlled clock`<br>- `G1-R2-B regression: reboot lifecycle, memory boundedness across 100 reboots, lock release, and boot_id uniqueness`<br>- `async actions, job lifecycle, reboot recovery and Wi-Fi flows follow contract semantics` | `npm run test:unit`（全量套件通过）：<br>- 彻底推翻错误测试预期，确立不变量 `保护期内已完成记录数 + 活动任务预留槽位数 <= 8`，任务总记录数在任何状态下严格 `<= 8` 条；<br>- 严格准入检查顺序：幂等优先（同负载满容量亦返回原 `job_id`，不同负载返 `OP_ID_REUSE`）-> 资源互斥检查 -> 容量检查（超额返 `BUSY`，Wi-Fi `state`/`ssid` 零副作用）-> 状态变更与受理；<br>- 5 分钟保留与回收精确边界判定：保护条件为 `elapsed < 300,000 ms`（满载拒绝新任务，严禁提前淘汰）；自然回收条件为 `elapsed >= 300,000 ms`（达到或超过 300,000 ms）；<br>- 受控时钟精确边界固化：`299,999 ms` 原任务完全可查且满载拒新返回 `BUSY`；`300,000 ms` 原记录自然回收且新任务成功受理；`300,001 ms` 持续可回收；未过期记录完全不受影响；<br>- 100 次连续重启后任务表严格有界（`<= 8` 条），旧任务变 `unknown`，互斥锁彻底释放，生成全新 32 位十六进制 `boot_id`，且 NVS 已持久化配置与 revision 完整保留；<br>- `device.restart` 严禁在重启前置为 `succeeded`；`radar.reset_module` 等 `verification: "none"` 动作以 `verified: false` 结束，严禁虚假宣称硬件验证成功。 | 模拟器已严格遵循有界内存（<=8）、容量预留、5 分钟绝对保护（<300,000ms）、自然回收（>=300,000ms）与完成顺序 FIFO 规则；生产固件（WP-2）须实现完全相同的有界 RAM 任务表调度与零副作用准入拒绝规则。 |
| **G1-R3** | **结构化配置 Schema 与业务校验空洞**：`r60.areas.v1`、`polygon.xy.v1`、`range.window.v1` 的多边形自交、坏点、负范围在 Schema 层为开放数组；禁用区域（`enabled: false`）的空点集与保留多边形未被统一放行；1D `range.window_cm` 与 R60 混用。 | `docs/protocol/schema/mwcp-v1.schema.json`<br>`static/src/protocol/schema.js`<br>`static/src/protocol/contract.js`<br>`static/src/protocol/simulator.js` | `static/test/protocol-schema.test.js`：<br>`G1-R3 regression: strict structured config validation across schema, CONFIG_VALIDATE, and CONFIG_COMMIT` | `npm run test:unit`（全量套件通过）：<br>- 浮点 slot、重复 slot、区域未知字段、非数组点集、2 点退化多边形、自交多边形、>12 顶点、边界越界点、步长未对齐均在 VALIDATE 与 COMMIT 被拒绝；<br>- 禁用区域空数组 `[]` 与保留有效多边形均正确放行。 | 64 顶点凸多边形已通过 `C-13` 满载验证（`~1.15 KiB <= 4096 B`）。 |
| **G1-R4** | **硬件证据索引缺陷**：`radar_uart` 在索引文件中误记为 `UART2 GPIO16/17`（实际物理接线与 host/baseline.yaml 均为 `UART1 GPIO21 TX / GPIO20 RX`）；缺少确切产物 SHA-256、ELF 节区尺寸与 76 文件快照映射；长测引用了不存在的文件。 | `docs/reviews/web-console/g0-evidence-index.json`<br>`docs/reviews/web-console/wp0-wp1-phase-report_CN.md`<br>`docs/reviews/web-console/wp0-wp1-phase-report.md` | `static/test/protocol-schema.test.js`：<br>`G1-R4 regression: G0 evidence index matches host.yaml/baseline.yaml and is arithmetically self-consistent` | `node --test test/protocol-schema.test.js`（全量通过）：<br>- 自动化校验 `g0-evidence-index.json` 与 `host.yaml`/`baseline.yaml` 引脚完全一致（GPIO21/20 115200）；<br>- 算术校验 Flash/RAM/BSS/Heap 增量及 G0-03 7,198 采样点起止一致；<br>- 引用路径全部物理存在，剔除不存在文件引用。 | 原始 3.5 MB 长测采样文件固化于会话外部存储 `scratch/g0-03-evidence.json`，仓库内仅保留汇总与里程碑样本以避免污染 git 树。 |
| **G1-R5** | **文档自洽、双语同步漏洞与工作流路径遗留**：中英文 README 中 R60 8 项配置的步长、范围、动作超时存在多处遗留倒退；设计差异文档 `DD-02` 引用了不存在的 `.github/workflows/publish-firmware.yml`；阶段报告与规范残留脆弱的固化测试用例数；固件交接文档缺少明确的任务上限（8条）、完成顺序淘汰与重启生命周期要求；P-03/P-14 缺乏紧凑内存下的 Sanitizer 内存安全证据。 | `docs/protocol/README_CN.md`<br>`docs/protocol/README.md`<br>`docs/protocol/design-differences_CN.md`<br>`docs/protocol/design-differences.md`<br>`docs/plans/mmwave-web-console/implementation-handoff.md`<br>`docs/reviews/web-console/wp0-wp1-phase-report_CN.md`<br>`docs/reviews/web-console/wp0-wp1-phase-report.md`<br>`protocol/cpp/mwcp_host_test.cpp` | `static/test/protocol-schema.test.js`：<br>`G1-R5 regression: referenced paths exist and bilingual protocol READMEs mirror the R60 fixture`<br>C++14 `mwcp_host_test`（ASan + UBSan） | `node --test test/protocol-schema.test.js` 通过；<br>双语 `DD-02` 修正为真实工作流 `publish.yml`；交接文档第 6 节补充完整任务生命周期规范；移除脆弱固化测试计数并由双平台全量套件覆盖；Linux WSL2 下 `g++ -fsanitize=address,undefined` 执行 100,000 次紧凑变异测试通过（退出码 0，0 越界，0 崩溃）。 | 双语文档、Schema/Fixture、设计差异与固件交接要求达到逐字段精确一致；已明确说明 `device.restart` 不可在重启前标记 `succeeded`，`verification: none` 动作以 `verified: false` 结束。 |

### 23.2 三类边界判定声明（生产 vs 模拟 vs 真机）
1. **真机已验证基线（G0）**：LuatOS ESP32C3-CORE + R60ABD1 物理硬件上已完成 G0-01～G0-05 验收，含 2 小时脱机长测（7,198 次采样，0 重启，0 堆泄漏，雷达有效帧净增 34,878 帧），固件二进制已归档于 `docs/reviews/web-console/g0-evidence-index.json`。
2. **当前模拟器能力范围（仅作契约桩）**：`static/src/protocol/simulator.js` 仅用于前端在无硬件环境下的协议契约验证与交互测试。模拟器已对齐 R60 8 项配置、2 项确认动作、结构化多边形/区域校验与会话生命周期，**模拟器测试通过绝不代表 WP-2 固件服务层已开发完成**。
3. **后续生产固件边界（WP-2）**：双槽原子 NVS（`ConfigService`）、真实后台任务调度（`JobService`）、实际 AP 扫描与 Wi-Fi 状态机（`WiFiService`）及零拷贝 UART 驱动将在进入 WP-2 后正式编写并基于 G0 硬件进行真机验收。

### 23.3 最终阶段结论

**结论**：**“G1 整改候选，待独立复核”**。
本轮整改已完全闭环 G1-R1～G1-R5 所有验收问题，完成双平台自动化回归与 Sanitizer 内存安全验证，未擅自声明协议冻结，未进入 WP-2/WP-3 阶段。

## 24. WP-2 生产固件核心（软件）。G2 真机为 not_run

用户确认 G1 已通过独立最终复核，含 G1-R1～R5 及最后的文档和边界测试（`test:unit` 106/106）。此处只记录该结论。它不是 G2 真机通过。JS 模拟器仍只是契约桩。

### 24.1 已实现

生产代码在 `components/mmwave_host/`，与 `docs/reviews/web-console/g0/` 探针分开。USB Serial/JTAG 由该组件独占，发送使用 `MwcpTxPump`（64 字节、连续零写 250 ms 放弃、下一帧前补 `0x00`）。会话、配置、任务、Wi-Fi、日志在 `mwcp_service.cpp`，主机测试可注入存储、Wi-Fi、时钟和雷达视图。`R60ABD1Component` 增加了默认空的 observer；未挂 host 时 HA 发布行为不变。旧的 `tests/r60abd1-esp32c3.yaml` 仍带 Improv，不加载 `mmwave_host`。

`tests/r60abd1-esp32c3-host.yaml` 是 host-enabled profile：MWCP 独占 USB，logger `UART0` / `baud_rate: 0`，`CONFIG_ESP_CONSOLE_NONE`，`wifi`/`api` `reboot_timeout: 0s`，无 `improv_serial`。雷达 UART 仍是 GPIO21 TX / GPIO20 RX、115200。实体名来自 `tests/common/r60abd1_mwcp.yaml`（共享雷达核心，不含 device 包）。

已知差异，没有擅自改协议：G1 模拟器先回收过期任务再查 `op_id`。生产实现按已验收交接顺序：先幂等，再资源互斥，再回收，再查容量。满表时相同 `op_id` 仍返回原 `job_id`。

### 24.2 本轮实际命令

| 命令 | 结果 |
| --- | --- |
| `g++ -std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror` 编译 `protocol/cpp/mwcp_service_test.cpp` | `mwcp service test passed`，退出码 0 |
| `esphome==2026.9.1` / ESP-IDF 5.5.5 编译 `tests/r60abd1-esp32c3-host.yaml` | 退出码 0。RAM 149656/321296。Flash 882008/1835008 |
| 同一工具链编译 `tests/r60abd1-esp32c3.yaml` | 退出码 0。RAM 107704/321296。Flash 940384/1835008 |

Host OTA SHA-256 `9920F0EC415C3C81B8D0600BEBD3F13678D3934FDC51CF63B42D4CA0B88DDDE4`。Host factory SHA-256 `270D84486B9F0876A8AEDA8D24C368DA26D1105C1B3F5A9BF5C5583DDFDA510C`。这是链接期大小，不是运行时堆或栈，也不是 G0 探针测量。

工作区 `86fc3ea156a13df3410a9fec619a7a7e72203fb6`。组件 `9a524b8e8b02ffb496d808250567d7169fe264d5`，另有未提交的 G1 与本次 WP-2 改动。没有提交、推送、发布或烧写。

### 24.3 G2 矩阵

| ID | 状态 | 计划用例 | 环境 | 已跑内容 | 证据 | 不能写成通过的原因 |
| --- | --- | --- | --- | --- | --- | --- |
| G2-01 | not_run | P-08..P-10, P-04..P-06 | 主机测试 + 编译 | HELLO、重放、`ID_REUSE`、会话 TTL、USB 独占编译 | `mwcp_service_test` | 未授权串口。DTR 挂起和真机握手未测 |
| G2-02 | not_run | P-11 | 主机代码 | 能力表来自 R60 fixture，页大小 2 | 源码 | 真机分页未跑 |
| G2-03 | not_run | T-02..T-10 | observer | `speed_cm_s` 保持 null；observer 不是第二个 UART reader | `r60abd1.cpp` | 本轮没有实时雷达样本 |
| G2-04 | not_run | C-01..C-14 | 主机测试 | 校验无副作用；提交 CAS、幂等、`OP_ID_REUSE`、持久化失败回滚、双槽损坏为 `recovery_required` | `mwcp_service_test` | 无断电、无真机 HA 同步 |
| G2-05 | not_run | A-01..A-03 | 主机测试 | 满表幂等、299999 保护、300000 回收、容量 `BUSY` 不改 Wi-Fi、重启前保持 `running`、重启清空任务并保留 revision | `mwcp_service_test` | 未真机执行 `device.restart` 或 `radar.reset_module` |
| G2-06 | not_run | W-01..W-04 | 主机测试 + 固件端口 | 状态不含密码；扫描排序/上限和配网回滚在服务内；固件调用 `start_scanning` / `start_connecting` / `save_wifi_sta` | 源码 | 无真机扫描或错误密码回滚 |
| G2-07 | not_run | S-01..S-04, R-01 | 部分 | 日志默认关闭；配网后清密码缓冲 | 源码 | 设备上未测环形缓冲溢出和秘密扫描 |

本生产镜像的运行时堆、最小剩余堆、最大连续块、栈余量、host 循环耗时和 RPC 延迟未测。不要用 G0 探针数字代替。

### 24.4 给 WP-3 的交接

固件已支持、控制台 UI 尚未接上：HELLO/PING/SESSION_CLOSE、DEVICE_INFO、分页 CAPABILITIES_LIST、STATUS_GET、CONFIG_VALIDATE/COMMIT/COMMIT_STATUS、`device.restart` 与 `radar.reset_module` 的 ACTION_START/JOB_GET、WIFI_STATUS/SCAN/PROVISION、遥测 SUBSCRIBE。本构建的 CONFIG_READ 和 WIFI_SCAN_RESULTS 分页还不完整。入队事件在 TX pump 空闲的后续 loop 中发出。`unknown` 只表示没有记录，不能证明动作没执行过。`verification: none` 以 `verified: false` 结束。双槽损坏不会恢复出厂。无 BLE、无原始 UART、无 mock 注入。

### 24.5 真机前仍需确认

点名板卡和原生 USB 路径、当前 VID/PID、GPIO 接线、上面的 host OTA 哈希、是否保留现有固件，并确认禁止整片擦除。G0 授权不覆盖此镜像。本轮没有打开串口。

## 25. WP-2 独立验收整改（R1～R9）。不是 G2 通过

第 24 节把若干命令写成了已实现。本节改掉那些说法。G2-01～G2-07 仍是 `not_run`。编译成功不是生产功能完成。

| ID | 改动 | 本轮实际测试 | 仍未完成 |
| --- | --- | --- | --- |
| R1 | `MwcpHostLink::queue_json` 把编码字节拷进发送缓冲。控制帧还在队列里时，`mwcp_dispatch_request` 不调用 `handle`。重启要等 `usb_serial_jtag_wait_tx_done(0)`，不能把写入驱动缓冲当成发送完成 | `mwcp_r_test.cpp` 与 `static/test/mwcp-production.test.js`：抓到的线字节不是全零；JS `decodeWire` + `validateResponse(HELLO)` 通过 | 没有 USB 分析仪，也没有真机背压 |
| R2 | host profile 的 number `set_action` 走 `submit_number`，先写入 ConfigService，再 `apply_to_radar`。该 profile 的 number lambda 读 `calibration()`，不读 globals。旧 `r60abd1.yaml` 未改 | host YAML 已编译 | 没有 HA/web 往返自动化。多边形和区域文本仍写 globals。真机冷启动同步是 not_run |
| R3 | `CONFIG_VALIDATE` 使用 `publish=false`，并恢复完整边界数组。`yaw=999` 和非数组 `areas.definitions` 会被拒绝 | `mwcp_r_test`：校验后原三角形逐点不变；yaw 和非法区域被拒绝 | 区域槽位几何、禁用槽和每个字段的步长矩阵还没有做完 |
| R4 | 双槽选择按 uint64 十进制比较，不再用 `strcmp`。`persist_config` 读回后才允许成功 | `mwcp_r_test`：提交到 revision 10，新对象 `load_storage` 得到 10 | 主机测试的存储是同一块缓冲，不是分开的易失缓存和闪存。断电注入是 not_run |
| R5 | 负数游标在索引前拒绝。`CONFIG_READ`、`UNSUBSCRIBE`、`WIFI_SCAN_RESULTS` 不再返回 `UNSUPPORTED` | 负数游标断言通过。HELLO JSON 通过冻结 schema | `CONFIG_READ` 目前只返回 x/z，不是 8 项完整分页。`UNSUBSCRIBE` 会清掉所有流。`WIFI_SCAN_RESULTS` 还没有分页扫描表。这些是部分实现，不能写成“只差真机” |
| R6 | `radar.reset_module` 调用注入的适配器。相同 `op_id` 不会再发送 | `mwcp_r_test`：发送计数保持 1 | 没有设备 UART 抓包。`verified` 仍为 false |
| R7 | 连接成功要求 IP 非空且不是 `0.0.0.0`，并且 SSID 是本次请求的网络。配网有 60 秒截止 | 只审查了 `poll_connect` 和截止时间代码 | 扫描完成、认证类型和凭据回滚没有对真实无线电复测 |
| R8 | `poll` 在没有新请求时也会过期会话，并停止遥测 | `mwcp_r_test`：TTL 之后 20 次 poll 产生 0 个事件 | 频率/字节预算、目标变陈旧、呼吸心率 observer 和日志环不在该测试里 |
| R9 | 生产测试命令是 `node --test test/mwcp-production.test.js`，需要 `MWCP_GPP`，并进入 `npm run test:unit`。`device_id` 用 STA MAC。`git_sha` 在代码生成时取 `git rev-parse`，取不到就是 null | JS 测试通过。`esphome==2026.9.1` 编译 host 和旧 `r60abd1-esp32c3.yaml`，退出码都是 0 | 运行时堆、栈和 RPC 延迟未测。不要用 G0 探针数字代替 |

本轮 host OTA SHA-256：`2ABCB5E2D640671EC78189E931AC0170D2487742A6E0B0326907A2580F9BD639`。factory：`B4F074FFCADBE25F40E0ADAE6D118016DC6EA0F0C90E5A0E323BB49E72093B08`。链接期 RAM 154968/321296，flash 886188/1835008。

没有烧写、提交或发布。G2 没有通过。

## 26. 后续软件整改（A～F）。仍不是 G2 通过

第 25 节列出的洞，本轮补上了能在软件里复现的部分。R8 没有全部做完，G2 也没有通过。

ESPHome 2026.9.1 的 `ESP32PreferenceBackend::save` 只把数据放进 `s_pending_save` 并返回 true（`esphome/components/esp32/preferences.cpp`）。真正写入是 `ESP32Preferences::sync()` 调用 `nvs_set_blob`。同文件注明 ESP-IDF 上 `nvs_commit` 目前是空操作。host 会调用 `sync()` 再读回。sync 失败不会发布。

| 项 | 状态 | 改动 | 测试 |
| --- | --- | --- | --- |
| A 配置事务 | 软件侧完成 | `apply_ha_number` 在持久化失败时恢复安装参数、边界、区域和 revision。USB 提交和 HA 写入都走 `publish_hook` → `apply_to_radar`（安装、多边形、启用区域的点）。host YAML 的 number/多边形会检查返回值，失败不发布用户输入 | `mwcp_af_test`：保存失败时高度和 revision 不变；成功才发布一次 |
| B 区域 | 部分完成 | 槽位范围、唯一性、enabled 类型、启用时空多边形会被拒绝；禁用空槽会保存并读回 | `mwcp_af_test` 的 slot 99 和禁用槽。区域多边形自交还没检查 |
| C 命令 | 部分完成 | `CONFIG_READ` 用 `cfg:` 游标分页返回 8 个键。`UNSUBSCRIBE` 只移除点名的流。`WIFI_SCAN_RESULTS` 返回刚完成的扫描，按 RSSI 排序 | `mwcp_af_test` 收集 8 个键且不重复，取消 logs 后 telemetry 还在，两个 AP 排序。扫描结果仍只有第一页 |
| D 存储 / Wi-Fi | 部分完成 | 缓存、sync、读回分开。sync 失败不发布。提交会拒绝 `recovery_required` 和 uint64 上限 | `mwcp_af_test` 覆盖 sync 失败。uint64 上限和提交历史满环失败本轮没跑。真实无线电仍是 not_run |
| E 遥测 / 日志 | 部分完成 | 订阅回显已接受的流，并读取 `max_rate_hz`。超预算的遥测会计入丢弃。呼吸、心率、距离 observer 不依赖 HA sensor 指针。logger 回调会涂掉 `password` 并计数 | 速率/预算和目标变陈旧还没有做成会失败的回归 |
| F 假通过 | 已修被点名的用例 | 三角形校验必须在上一帧发完后 `mwcp_dispatch_request` 返回 true | `mwcp_r_test` 和 `static/test/mwcp-production.test.js` 通过 |

本轮命令：`g++ -Wall -Wextra -Werror` 编译并运行 `mwcp_r_test`、`mwcp_af_test`，退出码都是 0。`MWCP_GPP` 下 `node --test static/test/mwcp-production.test.js` 通过。`esphome==2026.9.1` 编译 `tests/r60abd1-esp32c3-host.yaml` 和 `tests/r60abd1-esp32c3.yaml`，退出码都是 0。

Host OTA SHA-256 `41FD3AC4AF25F77273229A3F13AA6909DC27BF1554F73D2D07115B2EE163B3F3`。factory `7B56A98B6E5343692E21FD8EB43189EDDC90BAB17CFFAADF755EA0025D9FE35A`。RAM 154992/321296，flash 893778/1835008。`git_sha` 是代码生成时的 `git rev-parse HEAD`。工作区是脏的，这个 SHA 不是未提交源码的逐字节快照。

仍未完成，且不是“只差真机”：区域多边形自交、扫描结果第一页之后的分页、uint64 上限和满环失败测试、目标变陈旧、日志行的完整 JSON 转义、`_areas.yaml` 里的 HA 区域文本（仍写 globals）。G2-01～G2-07 仍是 `not_run`。没有烧写或提交。

## 27. AF-1～AF-6 软件修复。不是 G2 通过

| 项 | 状态 | 修复 | 测试 |
| --- | --- | --- | --- |
| AF-1 | 软件侧完成 | 同值判断在跳过持久化前比较 `boundary_set_`、点数和全部顶点。同样点数的不同多边形会增加 revision，冷启动读到的是新多边形。`_areas.yaml` 调用 `radar.try_commit_area`；没有 host 时旧 profile 仍走 globals | `mwcp_af_test`：先存 `[[1,1]...]` 再存 `[[100,100]...]`，`load_storage` 后首点仍是 100 |
| AF-2 | 部分完成 | 区域自交、重复点和零面积会被拒绝。`CONFIG_READ` 输出已保存的点，并对名称做 JSON 转义。放不下就返回错误，不返回截断成功 | 自交断言通过。64 点加 3 个区域的逐字段往返本轮没跑 |
| AF-3 | 部分完成 | 扫描游标会解析；第 2 页不再重复第 1 页。SSID 会转义 | 3 个 AP：游标 `"2"` 返回第三个 AP，且 `next_cursor` 为 null。真实认证类型和 `save_wifi_sta` 失败是否可见，受 ESPHome 该函数返回 void 的限制 |
| AF-4 | 部分完成 | `password=MARKER_SECRET` 在进入日志事件前变成 `password=<redacted>`。引号和换行会转义 | `mwcp_af_test` 断言标记不存在且包含 `<redacted>`。emoji 和日志洪水优先级没测 |
| AF-5 | 部分完成 | 位置超过 6000 ms 质量为 `stale`。无人时不保留有效目标。预算计入帧头、CRC 和 COBS 开销 | 本轮没有单独的速率/预算断言 |
| AF-6 | 部分完成 | 提交失败会恢复被覆盖的 ring 槽和 `commit_next_`，不是只把 `used` 清掉 | `mwcp_af_test` 写满 4 次后第 5 次失败，最旧 `op_id` 仍在。uint64 上限没跑。`mwcp_af_test` 已进入 `static/test/mwcp-production.test.js` |

`mwcp_r_test` 和 `mwcp_af_test` 退出码 0。`esphome==2026.9.1` 编译 host 和旧 R60 profile，退出码都是 0。Host OTA SHA-256 `9268EFE03DFACBDA9D93E465123B3363694CD9EEA4B5ADA486E5F97827379D4D`。factory `20FDB61F9E4F3AD3FF04DB606CAC4F412CCB4F635527CBBE0D1FC34490125D78`。RAM 155184/321296，flash 897774/1835008。工作区是脏的，构建 `git_sha` 不是完整源码快照。G2 真机仍是 `not_run`。没有烧写或提交。

## 28. AF 收口复核。软件未完成。G2 未跑

| 项 | 状态 | 改了什么 | 实际跑了什么 | 仍开放 |
| --- | --- | --- | --- | --- |
| AF-4 | 软件修复已测 | `redact_secrets(in, out, cap)` 写入有界副本。带空格和转义的引号值整段换成 `<redacted>`。放不下就在键之前停。日志路径调用该函数，再 `json_escape`，再 `emit_event` | `mwcp_close_test`：160 字节缓冲区加保护区、`push_log_at` / `next_event` 路径上的引号 `MARKER_SECRET`、空值和多个秘密、emoji 截断。日志帧经过 `validateEvent` | MinGW g++ 13.3.0 没有 `-lasan` / `-lubsan`。ASan/UBSan 没跑。这不是通过 |
| AF-1 | 软件修复已编译 | 共用 `tests/common/_areas.yaml` 恢复为旧的 global + script。只有 host profile 包含的 `tests/common/_areas_host.yaml` 调用 `id(host_link).commit_area_text`。没有给其他雷达加空方法。`Service::apply_area_text` 组完整区域数组，不加前导逗号，并保留其他槽的名称、enabled 和顶点 | 空配置写 slot 1/2、稀疏槽、自定义名称、清空、非法输入、持久化失败不发布、冷启动。编译矩阵见下 | HA 实体状态没有在设备上执行。yaml 只在 commit 返回 true 时写 global |
| AF-2 | 部分完成 | 自交拒绝保留。64 点边界和 3 个最大区域提交后，`load_storage` 逐字段还在，包括 `门口`、`a"b`、`c\d`。编码不了的页返回 `PAYLOAD_TOO_LARGE`，不是无响应或截断成功 | 边界页的 request_id 对上，JS schema 通过。下一页区域返回 `PAYLOAD_TOO_LARGE` | 冻结的 `JSON_MAX_DEPTH=8` 装不下响应包里的 `areas.definitions`（根/result/items/item/value/slot/points/point/number 是深度 9）。没有放宽检查器。区域 `CONFIG_READ` 因此未完成 |
| AF-3 | 部分完成，不是完成 | 扫描认证是 `open` 或 `unknown`，不猜成 `wpa2_psk`。`persist_credentials` 只有 write、sync、读回一致才返回 true。生产 `persist_wifi` 调用它，不把 `save_wifi_sta()` 的 void 当成成功。指纹没变的旧扫描会一直留到变化或 15 秒 | 适配器故障注入：写失败、sync 失败、读回失败、成功、旧指纹 | ESPHome 2026.9.1 的 `WiFiScanResult` 只有 `get_with_auth()`。不改 ESPHome 或契约，就分不出 WPA2、WPA3 和企业认证。没有跑真实 NVS |
| AF-5 | 软件测试通过，不是真机通过 | 遥测 `metrics` 带独立 `sample_ms` 的 `distance.cm`、`breath_rate`、`heart_rate`。位置在 6000 ms 为 `stale`。无人不保留目标。每个流用自己接受的速率。日志用 `encode_frame` 的线字节计入 `event_budget_bps`，控制帧排队时不能发事件 | 同一毫秒 100 条日志被丢。20 Hz 日志在 1000 字节窗口内停下。捕获的遥测帧通过 `validateEvent` 和 `telemetryIssue` | `motion.state`、`body.movement`、`sleep.state`、`areas.occupancy` 仍是 `unknown`，因为这个 observer 没有这些样本。`speed.cm_s` 是 `unsupported` |
| AF-6 | 回归已接入，WP-2 未收口 | uint64 上限从带 CRC 的 blob 加载。USB 和 HA 写入都失败、不回绕、不改存储。`static/test/mwcp-production.test.js` 编译 `mwcp_close_test` 并校验每条 `WIRE`。没有 `g++` 会抛错。`.github/workflows/web.yml` 已包含 `components/mmwave_host/**` | `node --test static/test/mwcp-production.test.js` 退出码 0（`# pass 1`，`# fail 0`） | G2-01～G2-07 仍是 `not_run`。本节不是 WP-2 收口 |

命令和退出码：

- `g++ -std=c++14 -Wall -Wextra -Werror` 编译 `protocol/cpp/mwcp_close_test.cpp`：退出码 0，`mwcp close test passed`。
- 同样参数编译 `mwcp_af_test`：退出码 0。
- `MWCP_GPP` 下 `node --test --test-timeout=120000 static/test/mwcp-production.test.js`：`# pass 1`，`# fail 0`。
- `g++ -fsanitize=address,undefined`：链接失败，`cannot find -lasan` 和 `-lubsan`。没跑。
- `esphome==2026.9.1` 编译，退出码都是 0：`tests/r60abd1-esp32c3-host.yaml`、`tests/r60abd1-esp32c3.yaml`、`tests/ld2450-esp32c3.yaml`、`tests/ld2451-esp32c3.yaml`、`tests/ld2452-esp32c3.yaml`、`tests/ld2453-esp32c3.yaml`、`tests/ld2454-esp32c3.yaml`。

Host OTA SHA-256 `1D84EFB62F853C2A68E8DA230DB7106694120A8B4FFDBFD95B3EA62AE699CED7`。factory `0B3BB77AEA959440A0A80971E174393CBC5F727601712988AA08D750EE661E5A`。这次编译没有重新打印 RAM/flash。`git_sha` 仍是脏工作区上的 `git rev-parse HEAD`，不是逐字节源码快照。没有烧写或提交。

## 29. 第二轮 AF 复核。不是 WP-2 收口。G2 未跑

| 项 | 状态 | 修改 | 证据 | 仍开放 |
| --- | --- | --- | --- | --- |
| AF-5 | 软件修复已测 | 生产主循环不再使用 768 字节缓冲区。`MwcpHost::loop` 和测试调用同一个 `mwcp_forward_events`。事件槽和该缓冲区都是 `kMaxEventJson`（2048）。编码失败的事件计入 `unsent_events` 并移出队首，不能永久堵住后面的日志 | `mwcp_close_test` 把 Service 生成的遥测经 `MwcpHostLink` 和 TX pump 发出，包含 1 字节短写和一次零写。解出的 payload 长于 768，并带距离、呼吸、心率。该线帧通过 JS `validateEvent`。排在遥测后的日志随后被转发 | 不是真机速率测量 |
| AF-4 | 软件修复已测 | 脱敏覆盖 `wifi_password`、`ota_password`、`ap_password`、`sta_password`、`api_key`、`password`、`passwd`、`psk`，包括 JSON 键引号后的 `:` 和单引号值。键无法界定时整条日志丢弃 | 三条复现日志经过 `push_log_at`、`mwcp_forward_events` 和线帧解码。输出里没有 `MARKER` 和 `SECRET`。上一轮保护区、扩写和 emoji 截断仍通过 | ASan/UBSan 仍链接不了：MinGW g++ 13.3.0 没有 `-lasan` 或 `-lubsan`。不是通过 |
| AF-1 | 软件修复已编译 | Host 区域文本改为 `optimistic: false`。因此 ESPHome `TemplateText::control` 不会发布输入值。yaml 只在提交成功后发布规范文本。启动不再用旧 globals 覆盖雷达。USB 发布走 `commit_area_view` 和 `export_area_text` | 失败的 `commit_area_view` 保持原 HA 和 global 字符串。slot 1 成功后两边都是 `0,0;100,0;50,80`。host、旧 R60、LD2450～2454 编译通过 | HA 实体状态没有在设备上执行。实体测试调用的是 host 使用的同一函数，不是活的 `TemplateText` |
| AF-2 | 待契约决策 | 没有改 schema、JS 检查器或黄金向量 | 一个三角形就够了。C++ `json_check` 对 `{"ok":true,"result":{"revision":"1","items":[{"key":"areas.definitions","value":[{"slot":0,"enabled":true,"name":"a","points_cm":[[0,0],[1,0],[0,1]]}]}],"next_cursor":null}}` 返回 `depth`。根是深度 1，点的数字是深度 9。`JSON_MAX_DEPTH` 在 `docs/protocol/README.md`、`protocol/cpp/mwcp_json.cpp` 和 `static/src/protocol/json.js` 都是 8。schema 没有写这个深度。分页降不了一个区域项自己的嵌套。当前设备返回 `PAYLOAD_TOO_LARGE`，不是静默丢弃。这不是通过 | 建议但未实施：把 `JSON_MAX_DEPTH` 从 8 提到 10。解析器是迭代的，代价是现有深度计数，不是新栈。`JSON_MAX_KEYS`、`JSON_MAX_ITEMS`、`max_payload` 仍是 64、256、4096。拒绝深度超过 8 的旧客户端会拒绝区域页；新客户端会接受。受影响资产：两端 JSON 检查器、README/README_CN，以及把深度 9 当成损坏的测试。维护者确认前不实施 |
| AF-3 | 部分完成，不是完成 | 完成信号是 `WIFI_EVENT_SCAN_DONE` 的代次，不是 15 秒后放行旧指纹。超时、启动失败、事件状态非 0 都返回失败，并且不复制上一份 AP。完成且结果相同或为空时，复制的是当前列表。持久化失败会把旧凭据写回去 | `collect_scan`：超时复制 0 次；启动失败和无线电失败复制 0 次；新代次复制 1 次。sync 失败后恢复 `old` / `old-pass-1` | `scanItem.auth` 是自由字符串，所以 `unknown` 能通过校验。`WIFI_PROVISION` 仍只接受 `open` 和 `wpa2_psk`。把 `unknown` 抄进配网会被拒绝。这不需要改契约，但控制台必须让用户选择 `open` 或 `wpa2_psk`。ESPHome 仍报不出真实认证类型。真实 NVS 和真实扫描没跑 |
| AF-6 | 回归已接入，WP-2 未收口 | uint64 上限、request id 核对和生产线帧检查都还在。`npm` 单元入口会编译 `mwcp_close_test`，没有 `g++` 会失败 | `mwcp_close_test` 退出码 0。`mwcp_af_test` 退出码 0。`node --test static/test/mwcp-production.test.js` 为 `# pass 1`、`# fail 0`。host 编译退出码 0。旧 R60 和 LD2450～2454 编译退出码 0 | G2-01～G2-07 仍是 `not_run`。AF-2 等维护者决定。这不是 G2 通过 |

Host OTA SHA-256 `292E78578C0A721C0AEF9E574937B4F77C9A849CD18FEFE9956EA0A5B358DC3E`。factory `79E69CC85A5B72F04836EA413EEE880356DD3EFCBB053429762E3C85FAD7F0FA`。RAM 178600/321296，flash 902698/1835008。工作区是脏的，`git_sha` 不是逐字节源码快照。没有烧写或提交。

## 30. 已批准的契约变更落地。区域页可往返。G2 仍未跑

维护者批准三件事：把 `JSON_MAX_DEPTH` 从 8 提到 10、允许 `scanItem.auth` 为 `unknown`、用更新后的 MinGW64 重试 sanitizer 构建。三件都已执行。

| 项 | 修改 | 证据 | 仍开放 |
| --- | --- | --- | --- |
| 深度 10 | `protocol/cpp/mwcp_json.cpp` 现在只在 `depth > 10` 拒绝。`static/src/protocol/limits.js` 设 `JSON_MAX_DEPTH = 10`。`docs/protocol/README.md` 和 `README_CN.md` 记录 10 及原因。schema 从未编码深度，本项不涉及它。`JSON_MAX_KEYS`、`JSON_MAX_ITEMS` 和载荷上限都不变 | `static/test/protocol-codec.test.js` 现断言 8 层包裹（数字在深度 10）通过、9 层包裹报 `depth` 失败。`mwcp_close_test` 断言深度 9 的区域页通过 `mwcp::json_check`，深度 11 的文档被以错误码 `depth` 拒绝 | 拒绝深度超过 8 的旧客户端会拒绝区域页；该冻结契约风险已由维护者接受 |
| 区域页 | 深度 10 后 `CONFIG_READ` 构建器用同一个 `json_check` 门接受 `areas.definitions` 项。close 测试不再断言区域页返回 `PAYLOAD_TOO_LARGE`——该断言已替换：最大配置提交后，响应要么把边界和区域合并进一页（`next_cursor: null`），要么在后续页继续；两种形态下测试都断言 `"ok":true`、出现 `门口` 名称、且没有 `PAYLOAD_TOO_LARGE`。有游标时测试会跟进游标并用新 request id 发后续请求 | close 测试编译运行通过：`mwcp close test passed`，退出码 0 | 不是真实无线电验证 |
| 扫描 auth unknown | `mwcp-v1.schema.json` 的 `scanItem.auth` 从自由字符串改为 `wifiAuth` 或 `"unknown"`。`WIFI_PROVISION` 仍只接受 `open` 和 `wpa2_psk`；回归测试现在断言 `unknown` 在扫描项里合法、在配网请求里被拒 | `npm run test:unit` 107/107 | 设备固件仍只能报 `open` / `unknown`（ESPHome `get_with_auth()`）；控制台仍必须让用户选择，且不能把 `unknown` 抄进 `WIFI_PROVISION` |

本轮命令（Windows、Node、esphome 2026.9.1 / ESP-IDF 5.5.5）：

- `D:\Build\w64devkit\bin\g++.exe` 14.2.0，`-std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror`：`mwcp_close_test` 退出码 0（`mwcp close test passed`），`mwcp_af_test` 退出码 0。
- `node --test` 跑 `protocol-codec.test.js`、`protocol-schema.test.js`、`protocol-regression.test.js`、`mwcp-production.test.js`：30 通过，0 失败。
- `MWCP_GPP=<w64devkit g++> npm run test:unit`：107 通过，0 失败。不带 `MWCP_GPP` 时两个编译器入口测试按设计失败（不是回归）。
- `npm run test:browser`：2 通过，0 失败。`npm run build`：退出码 0（Vite）。
- `esphome compile`，退出码全为 0：`tests/r60abd1-esp32c3-host.yaml`（RAM 178600/321296，flash 902698/1835008）、`tests/r60abd1-esp32c3.yaml`（RAM 107704/321296，flash 940512/1835008）、`tests/ld2450-esp32c3.yaml`、`tests/ld2451-esp32c3.yaml`、`tests/ld2452-esp32c3.yaml`、`tests/ld2453-esp32c3.yaml`、`tests/ld2454-esp32c3.yaml`、`tests/r60abd1-esp32c3.factory.yaml`。
- `python -m unittest tests.unit.test_mwcp_sources -v`（工作区）：2 个测试 OK。

ASan/UBSan 现在已运行。经过：第一次重试用的是当时的 `D:\Build\w64devkit` GCC 14.2.0，链接仍然失败（`cannot find -lasan`、`-lubsan`），且当时机器上没有其他编译器。维护者随后把工具链换成 `D:\msys64\clang64\bin`（clang 23.1.3，MSYS2）——该操作删除了 `D:\Build\w64devkit`——并要求再次重试。先跑了一个播种的堆溢出探针（对 `new int[3]` 越界写，退出码 1，报出真实 `heap-buffer-overflow`），确认该工具链上的运行时真的能抓错。然后用 `clang++ -std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror -fsanitize=address,undefined`：

- `mwcp_close_test`（含 `mwcp_wifi_adapter`）：退出码 0，`mwcp close test passed`，无 sanitizer 报告，无泄漏报告
- `mwcp_af_test`：退出码 0
- `mwcp_host_test`（黄金向量）：退出码 0

需要一个可移植性修复：`protocol/cpp/mwcp_close_test.cpp` 现在包含 `<cmath>`，因为 clang 的 libc++ 不经过 `<math.h>` 暴露 `std::cos`/`std::sin`。只改测试；生产代码不变，上面的固件哈希仍然有效。两个改过的 `protocol/cpp` 文件在仓库标准 `clang-format==22.1.8` 下无格式违规（本地更新版 clang-format 23 打出的额外违规是版本差异，未采纳）。JS 套件已把 `MWCP_GPP` 指向 `clang++` 重跑：四个协议测试文件 30/30，全量 `npm run test:unit` 107/107；`npm run test:browser`（2/2）和 `npm run build` 本轮已经绿了，且不依赖编译器。G2-01～G2-07 仍是 `not_run`。没有烧写或提交。

新固件哈希：Host OTA SHA-256 `766E65435D09FE79ABF1FAA9252B98E8C862AE0C573A557B65D27A0905A0B146`。factory `E8C82DD843501094818592A57F9198014B35421C6D4771FA50B1DE4158687D77`。两者与第 29 节不同，因为深度常数编译进了固件。工作区是脏的，`git_sha` 不是逐字节源码快照。G2-01～G2-07 仍是 `not_run`。没有烧写或提交。

## 31. 扫描结果与完成事件绑定。启动失败有界。G2 仍未跑

AF-3 已在生产路径落地，不再只存在于测试接缝。`ScanBridge` 把原始 `WIFI_EVENT_SCAN_DONE` 当作完成门，把 ESPHome 的 `WiFiScanResultsListener` 当作“结果列表已替换”的信号。只有当前请求的两个事实都观察到，成功且非空的扫描才完成；listener 只复制一次列表。失败直接让作业失败、不发布；0 AP 完成则发布空快照，旧扫描记录不会泄漏。`start()` 在请求平台启动前清空事件槽，并在启动返回后才 arm capture，避免把请求前排队的完成归到本次扫描。没有任何事件到达的超时进入有界 31 秒 drain（`kDrainMs`），期间新扫描被拒绝；迟到事件被 drain 消费，不能完成重试。已看到原始成功、只是 listener 迟到的超时直接回 idle：驱动已完成，无需隔离。drain 期间 `poll()` 返回 `-1`，让 service 走雷达超时分支，而不是误报 `VERIFY_FAILED`。`loop()` 在 `service_.poll(now)` 前调用 `tick(now)`，即使调用方已放弃作业，隔离仍会推进。

组件接线完成。`mmwave_host.cpp` 注册原始事件 handler 和 `ScanResultsListener`，缺少 `USE_WIFI_SCAN_RESULTS_LISTENERS` 时用 `#error` 让构建显式失败。`__init__.py` 同时调用 `wifi.request_wifi_scan_results_listener()` 和 `wifi.request_wifi_scan_results()`：前者让 ESPHome 编译 listener 接口，后者让驱动返回完整扫描列表而不是只返回已配置网络。host profile 已用新代码编译通过。启动前置检查是显式的：注册缺失、Wi-Fi 组件为空、`is_disabled()`、`is_roaming_scan_active()` 都会在发起启动前让作业失败。

回归在 `protocol/cpp/mwcp_scan_test.cpp`。它通过 `WifiPort` 驱动真实 `Service` 和 `ScanBridge`，覆盖：ESPHome 尚未更新列表时原始完成先到（不提供旧 AP、作业保持 `running`、`WIFI_SCAN_RESULTS` 返回 `BUSY`）；listener 完成该扫描且只复制一次新 AP；旧列表仍非空时的 0 AP（空列表、不复制）；相同结果；数量相同但结果不同；启动拒绝；注册拒绝；射频失败；超时不复制，drain 期间重试被拒且迟到事件不能完成它；迟到事件后的新扫描返回自己的数据；连续扫描不复用上一份快照；drain 截止后释放。旧实现基线打印 `legacy poll n=1 ssid=OLD_AP` 和 `LEGACY BUG REPRODUCED: scan-done generation advanced before ESPHome updated the results list; old AP delivered`；新测试断言相反（`old list was not copied`、`new AP is published after the list update`）。

测试通过前发现并修复了一个接线缺陷。最初的 listener 实现会在 `poll()` 消费已存入的原始事件前检查 `raw_success_`，因而拒绝合法完成。`ScanBridge::on_results` 现在先 drain 事件槽，再处理 `status != 0`（idle、不复制）、`number == 0`（空快照完成）和成功非空（`raw_success_`，由 listener 复制）；`poll()` 使用同一套事件处理。测试还跨过了 15 秒会话 TTL，并会超出 8 个作业的表，所以用新 nonce 重新 HELLO，并在新的 `Service` 上继续；这是测试夹具管道，不是生产行为。

启动失败仍有一部分在 ESPHome 公共 API 之外。`WiFiComponent::start_scanning()`（`wifi_component.cpp:1349`）丢弃 `wifi_scan_start_()` 的 `bool`，并无条件把状态设为 `WIFI_COMPONENT_STATE_STA_SCANNING`；因此驱动级拒绝与慢扫描无法区分。service 在 15 秒扫描截止时报 `RADAR_TIMEOUT`，随后 bridge 最多隔离 31 秒，期间拒绝立即重试。组件只对能看到的前置条件报 `RADAR_UNAVAILABLE`；它从不发布旧列表。还评估并否决了直接调用 `esp_wifi_scan_start()` 的方案：它会绕过 `WIFI_COMPONENT_STATE_STA_SCANNING`，ESPHome 的 post-connect roaming 可能把我们的 `SCAN_DONE` 当成自己的扫描并据此漫游。要补齐需要一个小而源码兼容的上游改动：让 `start_scanning()` 返回 `wifi_scan_start_()` 的结果，并只在成功时设置 `WIFI_COMPONENT_STATE_STA_SCANNING`（`wifi_component.h` 声明加 `wifi_component.cpp`；四个平台的 `wifi_scan_start_()` 都已返回 `bool`，树内三个调用方都忽略返回值）。本轮没有改厂商文件，所以这仍是适配项，不是已完成的修复。

本轮验证（Windows、Node、esphome 2026.9.1 / ESP-IDF 5.5.5，`MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`）：

- `mwcp_scan_test` 用 `-std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror` 构建：`mwcp scan test passed`，退出码 0。
- 同一测试加 `-fsanitize=address,undefined -fno-sanitize-recover=all`：`mwcp scan test passed`，退出码 0。`mwcp_close_test` 和 `mwcp_af_test` 已按当前源码重建，在 ASan/UBSan 下同样通过，退出码 0。
- `npm run test:unit`：107 通过，0 失败。两个编译器入口测试需要 `MWCP_GPP`；不带时按设计失败关闭。
- `python -m unittest tests.unit.test_mwcp_sources -v`（工作区）：2 个测试 OK。
- `esphome compile tests/r60abd1-esp32c3-host.yaml`：成功，RAM 181708/321296，flash 904352/1835008。其余 7 个 profile 上一轮已编译；只有 host profile 含 `mmwave_host`，且在最终格式化/注释修改后重建。
- `clang-format==22.1.8`：新 `mwcp_scan_test.cpp`、重写的 adapter 和 `mmwave_host` 改动区域干净（`--dry-run --Werror`，退出码 0）。既有 `mwcp_service.cpp` 等未改代码仍有仓库 `.clang-format`（禁用单行 if）会重排的 ESPHome 风格单行 `if`；没有整体重排，以保持评审 diff 聚焦。

新固件哈希来自本轮仅 R1 的构建（已被第 32 节取代）：Host OTA SHA-256 `A49F5E4C6B0FCFA03E14F6F4AEB7BC7C8692DEE819F037EAF6411F278818E65A`（904704 字节）。Host factory `315618B9C5180B3979557B633FDC69BE43EE1D978AF610897F2D9B64889D88E1`（970240 字节）。工作区是脏的，`git_sha` 不是逐字节源码快照。

仍未验证：没有跑真实 Wi-Fi 扫描、NVS 写入或 HA 实体测试；G2-01～G2-07 仍是 `not_run`。三个扫描侧残留风险仍开放。(1) 双核 ESP32 上原始事件 handler 和主循环 listener 在不同任务；如果 listener 在事件任务 handler 存入完成前送达，通知会被忽略，作业以超时失败关闭，而不是发布旧数据。(2) 未连接时 ESPHome 可能自己发起重试扫描；公共 API 不能归属或取消它，`scan_id` 是 `uint8_t`，也无法标识扫描。(3) 驱动级启动拒绝无法通过 `start_scanning()` 观察；它会在 15 秒后以 `RADAR_TIMEOUT` 失败，并可能让下一次扫描被隔离最多 31 秒。auth 仍是 `open`/`unknown`，因为 `get_with_auth()` 是布尔。原先的 `JOB_GET` 失败原因风险已在第 32 节关闭。没有烧写或提交。

## 32. JOB_CHANGED 与 JOB_GET 共享同一个完整 job 对象。G2 仍未跑

R2 和 R3 已在 `components/mmwave_host/mwcp_service.cpp` 落地。`Service::write_job()` 是 `JOB_CHANGED`（0x8004）和 `JOB_GET`（0x0042）的唯一序列化器。running 事件和终态事件都携带 `job_id`、`op_id`、`action_id`、`state`、`stage`、`progress`、`started_ms`、`finished_ms`、`result` 和 `error`。失败作业输出 `result:null` 和结构化 `error:{code,message}`。成功但不做验证的作业输出 `result:{"verified":false,"verification":"none"}` 和 `error:null`。running 和 unknown 作业的 result/error 为 null。固定消息是 `Radar is unavailable`、`Radar operation timed out`、`Verification failed`、`Storage operation failed`、`Job resource is busy`、`Internal job error`，兜底 `Job failed`。`finish_job()` 显式给 `error_code` 补 null；事件缓冲和 `JOB_GET` 缓冲都是 512 字节。没有放宽 schema，也没有删字段。

`protocol/cpp/mwcp_job_test.cpp` 覆盖成功扫描（running 与 succeeded）、启动拒绝（`RADAR_UNAVAILABLE`）、射频失败（`VERIFY_FAILED`）、扫描超时（`RADAR_TIMEOUT`）、reset 成功与失败、配网持久化失败（`STORAGE_FAILED`）以及 unknown job。每个配对都打印 `JOBPAIR <event-wire> <response-wire>`。`static/test/mwcp-production.test.js` 编译生产 service 和 adapter，解码两种帧，用 schema 校验 `JOB_CHANGED` 和 `JOB_GET`，并逐字段比较事件与 `JOB_GET` 结果中的十个 job 字段。

本轮验证（Windows、Node、esphome 2026.9.1 / ESP-IDF 5.5.5，`MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`）：

- `mwcp_job_test` 用 `-std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror` 构建：`mwcp job test passed`，退出码 0。
- 同一测试加 `-fsanitize=address,undefined -fno-sanitize-recover=all`：`mwcp job test passed`，退出码 0。`mwcp_scan_test` 在 ASan/UBSan 下也保持通过。
- `node --test --test-timeout=120000 static/test/mwcp-production.test.js`：1 通过，0 失败；scan、adapter、close、job 四个可执行文件都编译并运行。
- `npm run test:unit`：107 通过，0 失败。
- `esphome compile tests/r60abd1-esp32c3-host.yaml`：成功，RAM 181708/321296，flash 905056/1835008。
- `clang-format==22.1.8`：新 `mwcp_job_test.cpp` 以及 `write_job`/`job_error_message` 新区域干净。`mwcp_service.cpp` 其余部分仍是既有单行 `if` 风格，没有整体重排。

Host OTA SHA-256 `EE29C62A9DD2B60EDDCED86E65C8059E6F5961B8E21CE6F9C0F8AC6CC146B7D0`（905408 字节）。Host factory `97DE59E4D5990B13B179C0BFA998A4FD88011F3FDC37C1E2B7A40F617192C1F2`（970944 字节）。工作区是脏的，`git_sha` 不是逐字节源码快照。R1 仍是第 31 节所述的适配项。没有跑真实扫描、NVS 写入或 HA 实体测试；G2-01～G2-07 仍是 `not_run`。没有烧写或提交。

## 33. R1 以固定 ESPHome 补丁收口。扫描归属精确。G2 仍未跑

R1 现改为基于仓库内固定补丁实现，不再依赖不可观测的 stock API。`patches/esphome-2026.9.1-wifi-scan-ownership.patch`（5 个文件：4 个修改文件加新增 `wifi_scan_ownership.h`；+222/−3）新增 `WiFiComponent::start_scan_for_component(uint32_t *generation)`（显式启动结果）、以原始 `(status, number)` 调用的完成监听器，以及漫游抑制访问器。`scripts/apply_esphome_patch.py` 锁定 `2026.9.1`，校验 pristine 与 patched 的 SHA-256（含新增头文件），先 `--check` 再用 `git -c core.autocrlf=false apply -p1` 应用，且幂等；CI 增加 `patch` job。host profile 用打补丁源码构建，其余型号 profile 保持 stock ESPHome。`components/mmwave_host/__init__.py` 仅在补丁 API 存在时申请完成监听器，并据此定义 `MWCP_WIFI_SCAN_OWNERSHIP`；stock 构建只编译拒绝路径，`WIFI_SCAN` 返回 `UNSUPPORTED`。第 31 节的 `ScanBridge` 及其 31 s drain 描述由本设计取代。

`components/mmwave_host/mwcp_wifi_adapter.cpp` 实现独占归属。`acquire_owned_scan()` 在启动前拒绝缺失/禁用模块、连接状态机正在扫描或连接、漫游扫描/roam、先前请求仍挂起，以及驱动拒绝；不要求已连接，因此未配网设备也能扫描并配网。它把依赖结果映射为 `ScanStart::{kStarted,kUnsupported,kBusy,kRefused}`。`ScanOwner` 有四个阶段（`IDLE`、`WAIT`、`COMPLETE`、`FAILED`）；`start()` 在 `WAIT` 时返回 `kBusy`，丢弃尚未取走的旧完成，只在平台受理后记录代际并武装请求。`on_completion(generation, status, number, copy)` 忽略代际不符的完成，成功时只拷贝一次列表，把驱动失败或“声明有条目但取不回”映射为 `FAILED`，把声明 0 个 AP 视为成功的空快照。`poll()` 等待时返回 `-1`，`COMPLETE` 时返回一次拷贝后复位，`FAILED` 返回 `-2`。`tick()` 在 `kHoldBoundMs = 60000` 后只停止等待并解除漫游抑制，**不**释放依赖持有的射频：归属门保持关闭，直到真实完成事件到达；任务结束后才到的完成只计为 ignored，绝不发布。这里刻意没有基于时间的归属释放。

Service 立即映射这些事实：`kUnsupported` → `UNSUPPORTED`（`Unsupported operation`），`kBusy`/`kRefused` → `RADAR_UNAVAILABLE`（`Radar is unavailable`），射频空闲后可重试。扫描截止（`now + 15000`）用 `static_cast<int32_t>(now_ms - scan_deadline_ms_) >= 0` 做回绕安全比较（`mwcp_service.cpp:1574`）。已受理扫描的依赖状态失败 → `VERIFY_FAILED`；到期无完成 → `RADAR_TIMEOUT`。设备绝不发布上一轮扫描结果：扫描任务挂起时 `WIFI_SCAN_RESULTS` 返回 `BUSY`；失败或超时后同一分页返回 `items: []`；启动被拒时任务未受理，该 `job_id` 的 `WIFI_SCAN_RESULTS` 返回 `INVALID_ARGUMENT`。如果完成事件本身丢失，归属门保持关闭，后续扫描在完成到达或设备重启前返回 `RADAR_UNAVAILABLE`；任务截止仍报 `RADAR_TIMEOUT`。

扫描回归围绕上述反例重写。它通过 `WifiPort` 驱动真实 `Service` 与真实 `ScanOwner`，经 `acquire_owned_scan()` 注入假平台，覆盖：(1) R1-A：A 的完成已排队时 A 超时；hold 边界只释放漫游抑制，归属门保持关闭，重试被拒；处理 A 的迟到事件不拷贝任何列表并重开归属门，之后 B 只返回自己的结果；(2) 无请求的完成属于后台扫描；(3) 漫游扫描与连接状态机正在扫描时在触碰射频前拒绝；(4) 驱动拒绝与 Wi-Fi 禁用返回结构化 `RADAR_UNAVAILABLE`，未连接不算拒绝；(5) A 超时后重试被孤儿完成拒绝，A 的迟到事件为 C 重开归属门；(6) 极迟完成不能完成立即重试，新受理扫描返回自己的数据；(7) 空列表、相同列表、条数相同但内容不同的列表；(8) 失败绝不发送旧列表，“声明有条目但 OOM”不是成功空结果；(9) 连续扫描绝不复用上一轮快照；(10) 截止比较跨 uint32 回绕正确，包含回绕后的 hold 释放；(11) stock ESPHome 返回 `UNSUPPORTED`；(12) 从未配网的离线设备完成扫描、配网、`connecting`、持久化，并在同一任务内到达 `connected`，且不回显密码。

job 回归同时纠正了第 32 节的覆盖声明。`radar.reset_module` 在请求处理器内同步完成，running 与终态事件同毫秒，终态在任何合法订阅速率下都会被 20 Hz jobs 流合并。旧测试用 `if (capture_event(...))` 守护成功 reset 捕获，实际静默跳过 succeeded 事件及其配对：第 32 节所谓“successful reset”配对从未存在。`mwcp_job_test.cpp` 现在断言 20100 ms 的 running 事件、`svc.unsent_events()` 恰好 +1 的单个合并终态，以及 `JOB_GET` 的 succeeded 结果（`{"verified":false,"verification":"none"}`、`error:null`）；reset 成功通过 `JOB_GET` 覆盖，而不是伪造事件。测试另加 `UNSUPPORTED` 准入用例，并改为期望每次捕获。它打印 5 条 `JOBPAIR`（running scan、succeeded scan、射频失败、扫描超时、存储失败）。

本轮验证（Windows、Node、esphome 2026.9.1 / ESP-IDF 5.5.5，`MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`）：

- `mwcp_r_test`、`mwcp_af_test`、`mwcp_service_test`、`mwcp_close_test`、`mwcp_scan_test`、`mwcp_scan_gate_test`、`mwcp_job_test` 用 `-std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror` 构建：七个均打印 `passed`，退出码 0。
- 同上七个加 `-fsanitize=address,undefined -fno-sanitize-recover=all`：全部通过，退出码 0。
- 设 `MWCP_GPP` 后 `npm run test:unit`：107 通过，0 失败。JS 测试重编 r/af/close/scan/gate/job，校验事件与响应 schema，并逐字段检查 `JOBPAIR` 行的十个 job 字段。
- 工作区根执行 `python -m unittest tests.unit.test_mwcp_sources -v`：2 个测试 OK。
- 用 `PYTHONPATH` 指向打补丁树后 `esphome compile tests/r60abd1-esp32c3-host.yaml`：成功。生成的 `defines.h` 含 `MWCP_WIFI_SCAN_OWNERSHIP`、`USE_WIFI_SCAN_COMPLETION_LISTENERS`、`ESPHOME_WIFI_SCAN_COMPLETION_LISTENERS 1`、`USE_WIFI_RUNTIME_ROAMING_SUPPRESSION`。RAM 181656/321296，flash 904590/1835008（第 34 节的构建取代本次）。
- 本轮第一次 host 构建抓到宿主测试看不见的真实集成 bug：`mmwave_host.h/.cpp` 的 `ScanStart` 未限定命名空间（类型在 `mwcp_host`）。修好后 profile 编译通过；这也是为什么慢速 ESPHome 构建仍留在验证清单里。
- `clang-format==22.1.8` + 仓库 `.clang-format`：改动/新增的 3 个组件文件与 2 个扫描测试文件 `--dry-run --Werror` 干净。与第 31–32 节不同，组件改动文件是整体格式化，而非只格式化新区域。

本 R1 构建最终哈希（第 34 节以修正后的补丁与 host 构建取代）：Host OTA SHA-256 `FE47A7B398DA197ED798FF517B3EB2743991AA48E650696382448F0E3C04F572`（905072 字节）。Host factory `710E0B30CB379D27DEFABE554040116BD950C01ECCE6DFF264EEB57B73637276`（970608 字节）。工作区是脏的，`git_sha` 不是逐字节源码快照；ESP-IDF 会嵌入构建元数据，同一源码重建也不是逐字节相同。

仍未验证：没有跑真实 Wi-Fi 扫描、NVS 写入或 HA 实体测试；G2-01～G2-07 仍是 `not_run`。残留风险：(1) 完成监听器运行在 WiFi 组件主循环的事件处理中（`wifi_loop_` → `wifi_process_event_`），不是 Wi-Fi 事件任务；adapter 在该处拷贝列表，真实双核时序未测。(2) 已受理扫描若完成事件丢失，归属门会永久关闭；后续扫描在完成到达或设备重启前返回 `RADAR_UNAVAILABLE`。这是刻意的 fail-closed 选择，不是驱动保证。(3) ESP-IDF 驱动“先空闲、后入队完成事件”的顺序无法从公开 API 证明；独占生命周期避免依赖该顺序，但仍缺硬件证据。(4) 扫描 `auth` 只能是 `open`/`unknown`，因为 API 是布尔值。(5) 固定补丁必须在每次 ESPHome 升级时重新验证；脚本拒绝其他版本。没有烧写或提交。

## 34. R1-A 以独占门收口；离线首次配网与打补丁 host 构建已实测。G2 仍未跑

第 33 节夸大了第一版 R1 补丁的证明范围。旧补丁在 60 s 标记窗口后释放扫描归属，完成处理器使用“当前”代际，因此陈旧事件可能被盖上新请求的代际。红/绿复现（临时文件，在仓库外）把缺陷写死：

```text
legacy stamping with 60 s release:
  t=0     A start -> generation 1
  t=0     A SCAN_DONE queued, not processed
  t=61000 B start -> accepted=1 generation 2 (A released by time)
  legacy: completion of OLD_AP (generation 1) attributed to generation 2
  t=62000 A completion processed; B believes its request is done
legacy result: misattributed=1 (B published A's APs)

exclusive gate:
  t=0     A start -> accepted=1 generation 1
  t=0     A SCAN_DONE queued, not processed
  t=61000 B start -> accepted=0 (pending completion blocks it)
  gate: completion of OLD_AP delivered as generation 1
  t=62000 A completion processed
  t=62000 B retry -> accepted=1 generation 2
  gate: completion of NEW_AP delivered as generation 2
gate result: A delivered as 1, B as 2, backgrounds=0
```

补丁现在包含 5 个文件（4 个修改文件加新增 `wifi_scan_ownership.h`；+222/−3）。真实 host 构建还抓到一个原生 fake 看不见的集成缺陷：补丁声明并遍历 `scan_completion_listeners_`，却没有加入公开的 `add_scan_completion_listener()` 和监听器 vector；`components/mmwave_host/mmwave_host.cpp` 调用了该方法，第一次完整编译失败。两者已补入 `wifi_component.h`，补丁重新生成并更新哈希。

修正后的归属规则：

- `start_scan_for_component()` 不再要求站点已连接。仅在 Wi-Fi 禁用、连接状态机正在扫描/连接、漫游扫描/roam 进行中、先前组件请求仍挂起，或驱动拒绝启动时返回 false。从未配网的设备因此可以扫描、列出 AP、配网并在同一流程到达 `connected`。
- `ScanOwnership::begin()` 在已有请求挂起时返回 false；`take()` 只消费一次；`cancel()` 做代际校验，陈旧取消不能释放新请求。没有基于时间的释放。
- ESPHome 完成处理器取走归属门，并把启动时发放的代际交给监听器。无挂起请求的后台完成被丢弃，绝不归给任何请求。
- `ScanOwner::tick()` 只释放 60 s 漫游抑制 hold 并停止等待。依赖仍持有射频；迟到完成被 owner 忽略并重开归属门，在此之前重试仍被拒。若事件丢失，设备保持 fail-closed，直到完成到达或重启；绝不发布上一轮扫描结果。

回归覆盖新增专用 `mwcp_scan_gate_test.cpp`（begin/take 一次、第二次请求拒绝、陈旧 cancel、空参数、代际回绕），以及此前失败的扫描场景：A 超时且完成已排队；hold 边界只释放抑制、不释放归属门；重试被拒；A 的迟到事件不拷贝并重开归属门；B 只返回 `NEW_AP`，绝不返回 `OLD_AP`。另有离线场景：无连接扫描、配网 `HOME`、报告 `connecting`、持久化并到达 `connected`，不回显密码。已连接状态下的扫描现在还必须保持 `connected`，不能强制改成 `disconnected`；新扫描开始时会清除上一轮的 `truncated` 标志。60 秒配网截止时间也按 uint32 回绕比较，回绕前刚到的截止时间会在回绕后立即触发，而不是等到下一个 49 天周期。JS 测试从补丁本身提取新增头文件，编译并运行 gate 回归，纳入标准 `npm run test:unit` 入口。

`scripts/build_host_profile.py` 让打补丁与 stock 构建可重复。patched 模式应用固定补丁、编译 `tests/r60abd1-esp32c3-host.yaml`、断言生成的 `defines.h` 含 `MWCP_WIFI_SCAN_OWNERSHIP`、`USE_WIFI_SCAN_COMPLETION_LISTENERS`、`USE_WIFI_RUNTIME_ROAMING_SUPPRESSION`，并打印固件哈希。stock 模式编译同一 profile，并断言这些归属宏不存在。CI 在只做哈希校验的 `patch` job 之后新增 `patch-build` job；stock matrix 用 `esphome/build-action@v7` 的 `version: "2026.9.1"` 固定同一 profile。`apply_esphome_patch.py` 现在在应用后也校验新增头文件，而不只是 4 个修改文件。

本轮实测（Windows、esphome 2026.9.1 / ESP-IDF 5.5.5，`MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`）：

- 在全新 pristine 副本上 `python scripts/build_host_profile.py --mode patched`：成功，宏如上；RAM 181656/321296，flash 904648/1835008。`firmware.factory.bin` SHA-256 `75F633C36042D6002093C9B91FDF407FCA677A4B33DA4B9FC2B5998CF25AF531`（970544 字节）；`firmware.ota.bin` / app SHA-256 `F2CE960D11CF80761983F472DE24182C20468E394E08006268EBF52B2FF79EE2`（905008 字节）。
- 在 pristine esphome 上 `python scripts/build_host_profile.py --mode stock`：成功，归属宏不存在，`USE_WIFI_RUNTIME_ROAMING_SUPPRESSION` 存在；RAM 181624/321296，flash 903550/1835008。`firmware.factory.bin` SHA-256 `83A5EB5AFFF811311BD8A251EB1F59521011A653E2369E62CE9C70ABFA293C0D`（969440 字节）；OTA SHA-256 `BDB996F3C97A81DEDA29A89CDC67284E632722FC3D340303529BD39E7A0A1DFD`（903904 字节）。
- 旧 R60 profile `tests/r60abd1-esp32c3.yaml` 在打补丁树上 `python -m esphome compile`：成功，RAM 107704/321296，flash 940514/1835008。
- 设 `MWCP_GPP` 后 `npm run test:unit`：107 通过，0 失败。
- `mwcp_scan_test` 与 `mwcp_scan_gate_test` 用标准参数及 `-fsanitize=address,undefined -fno-sanitize-recover=all`：通过，退出码 0。
- 工作区根 `python -m unittest tests.unit.test_mwcp_sources -v`：2 个测试 OK。
- `clang-format==22.1.8 --dry-run --Werror` 检查改动/新增的组件与测试文件：干净。
- `apply_esphome_patch.py --check`（pristine）→ 应用 → 再次应用：clean、patched、already patched。

仍未验证：没有跑真实 Wi-Fi 扫描、NVS 写入、HA 实体、驱动拒绝、重连或漫游测试；G2-01～G2-07 仍是 `not_run`。没有烧写或提交。

## 35. WP-2 关闭全扫描归属漏洞：所有扫描入口共用同一协调器。G2 仍未跑

第 34 节的补丁只让 `start_scan_for_component()` 占用归属门；`start_scanning()`（首次连接、captive portal、重试/重启阶段）和 `check_roaming_()` 仍直接调用 `wifi_scan_start_()`，后台扫描可以在门外进行。失败时序是：后台 A 启动并把完成事件留在队列；ESPHome 扫描状态机超时进入 cooldown；组件 B 在组件专用门下启动；A 的 `SCAN_DONE` 到达后被当作 B 的完成，B 发布 `OLD_BACKGROUND_AP`。第 34 节的复现只覆盖了从组件路径启动的 A，没有覆盖这条旁路；组件专用门没有关闭 R1-A，只是把旁路移到了后台入口。

本节取代第 34 节及旧版第 35 节的补丁规模、post-image 哈希和构建数字；第 34 节仅保留为历史记录。

本轮对 2026.9.1 的全部扫描入口做了审计：

- 后台入口：`start_scanning()` 的首次连接、captive portal、重试阶段/重启适配器，以及 `improv_serial` 的调用；`check_roaming_()` 的漫游扫描。
- 组件入口：`start_scan_for_component()`。
- 所有入口最终只经过 `WiFiComponent::wifi_scan_start_platform_()`；该函数只在 `start_owned_scan()` 中被调用，四个平台实现（ESP-IDF、ESP8266、LibreTiny、Pico W）只定义驱动调用。非 host 的 stock 构建保留原有 `#else` 直调路径，但此时 MWCP 不上报 `wifi.scan`，不存在组件归属。
- `scripts/check_scan_ownership_sources.py` 静态核对上述调用点、单一驱动入口、监听器注册和 define；在旧树上运行会报 23 个错误并退出 1。

归属与完成分类：

- `ScanOwnership` 只有“进行中/空闲”两类状态：`begin()` 为组件扫描预留并发放非零、回绕跳零的代际；`begin_background()` 为后台扫描预留；任何未完成扫描都会让下一次启动返回 busy。`take()` 返回 `kNone`/`kBackground`/`kComponent`，只有 `kComponent` 携带代际；`cancel()` 校验代际，后台驱动拒绝用 `cancel_background()`。
- 头文件没有任何时钟、超时或状态机钩子。扫描超时、cooldown、重连、启用/禁用都不会释放归属；丢失 `SCAN_DONE` 时门保持关闭，后续请求失败关闭（fail-closed），直到完成到达或重启。
- `ScanCoordinator` 是连接/重试/漫游与组件扫描共用的生命周期：`start_background()`、`start_component()`、`take_completion()`。`notify_scan_completion_listeners_()` 先取完成；后台、重复或无预留事件一律不进入监听器，绝不因“当前有一个组件请求”而改写归属。
- 组件扫描仍不要求站点已连接；离线首次扫描→列出 AP→配网→`connected` 的路径保留，没有重新禁止未连接扫描。

可执行证据（`protocol/cpp/mwcp_scan_lifecycle_test.cpp`）：

- legacy 半段按已删除行为建模：后台 A 不预留即启动，完成事件留在队列，组件 B 被受理，随后 B 发布 `OLD_BACKGROUND_AP`。这证明该测试能捕获缺陷。
- 当前半段直接使用补丁里的 `ScanCoordinator`/`ScanOwner`：A 超时后 `in_flight()` 仍为真；B 的启动返回 busy，驱动未被调用，组件预留未建立；A 的完成返回 `kBackground` 且不产生结果；之后 B 才能启动，返回 `COMPONENT_B_AP`，绝不返回 `OLD_BACKGROUND_AP`。
- 恢复路径：连接失败重试在 A 未完成时 busy，A 完成后可启动；禁用/启用不清理门；失败的漫游在触碰驱动前拒绝，漫游结束后恢复；组件完成仍为 `kComponent`。
- `mwcp_scan_test.cpp` 场景 12 用真实 host adapter 复验同一顺序；已有的组件 A→B 超时隔离、重复完成、驱动拒绝、空结果、相同结果、同数量不同结果、uint32 回绕、离线配网且不回显密码等场景继续通过。`mwcp_scan_gate_test.cpp` 覆盖后台/组件双向占用、重复完成、取消和代际回绕。
- 测试没有向回调注入代际；代际只由被测协调器产生，完成分类由 `take_completion()` 决定。JS 测试从补丁本身提取新增头文件，再编译这些测试。

本轮实测（Windows、esphome 2026.9.1 / ESP-IDF 5.5.5，`MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`）：

- `npm --prefix static run test:unit`：107 通过，0 失败，退出码 0。
- 三个扫描测试在 `-fsanitize=address,undefined -fno-sanitize-recover=all` 下：`mwcp scan test passed`、`mwcp scan gate test passed`、`mwcp scan lifecycle test passed`，均退出码 0。
- 工作区根 `python -m unittest tests.unit.test_mwcp_sources -v`：2 个测试 OK，退出码 0。
- patched host profile（`.venv-esphome`，`scripts/build_host_profile.py --mode patched --venv .venv-esphome`）：退出码 0；含 `MWCP_WIFI_SCAN_OWNERSHIP`、`USE_WIFI_SCAN_COMPLETION_LISTENERS`、`USE_WIFI_RUNTIME_ROAMING_SUPPRESSION`；RAM 181664/321296，flash 904906/1835008；`firmware.factory.bin` SHA-256 `98f841059438afca81482f3e3af453ed6264e817b9664c7b98a131ee3ba2de12`（970800 字节）；`firmware.ota.bin` SHA-256 `7e09cdf1f2f03a5b44420eda76e128c2aee6504d9c68cba541cd405ea74fb010`（905264 字节）。
- stock host profile（全新 pristine venv，`--mode stock --data-dir .esphome-host-stock`）：退出码 0；归属宏不存在，`USE_WIFI_RUNTIME_ROAMING_SUPPRESSION` 存在；RAM 181624/321296，flash 903550/1835008；factory SHA-256 `8a0703223c01a3e081aa851301298f746c07a28ff61dee9416145c950e716e97`（969440 字节）；OTA SHA-256 `ba99c564345476c357f72cce5fba37a1fa22214402620e95d88f3163eb9b2ce5`（903904 字节）。
- 旧 R60 profile `tests/r60abd1-esp32c3.yaml` 在打补丁树上编译：退出码 0；RAM 107704/321296，flash 940514/1835008；factory SHA-256 `2a699f8d093ed15baf3cfeb1b84fdf3b5602f417e31bc9c602f05e233c0e4ab7`（1006416 字节）；OTA SHA-256 `488857701b765958a2b75858b501f58d82e07e6a650027ff7ad07934f70940a6`（940880 字节）。
- 补丁：8 个文件，+487/−10，31,749 字节；新增 `wifi_scan_ownership.h` SHA-256 `6b028c2477444b81e216f97aeafffa6de7e7154666ec3e9d1365ad8d78de9a3d`。`PRISTINE_SHA256`、`PATCHED_SHA256`、`PATCHED_ADDED_SHA256` 与磁盘逐项匹配。pristine `--check` 退出 0；在 pristine 副本上应用退出 0，第二次应用输出 `already patched` 退出 0；`check_scan_ownership_sources.py` 输出 `2 background entries, 1 component entry, 1 driver choke point, 4 platform implementations`，退出 0。
- `clang-format==22.1.8 --dry-run --Werror`：三个测试文件和新增头文件干净。打补丁的 upstream `wifi_component.cpp` 仍存在 pristine 版本中就有的 `WiFiScanResult` 构造函数换行差异，未改动该 upstream 区域。
- 构建环境修正：ESP-IDF `idf.py` 在 `MSYSTEM` 存在时只打印警告并直接退出 0，不运行 `main()`，导致“成功编译”但没有固件。`build_host_profile.py` 现在从子进程环境中移除 `MSYSTEM`；`.gitignore` 忽略 `.esphome-host/` 与 `.esphome-host-stock/`。这是本地 Windows/Git Bash 的构建可重复性修正，不改变 CI 的 Linux 路径。
- CI 触发：`web.yml` 的 `paths` 含 `patches/**` 与 `protocol/**`，只改补丁也会运行 `npm run test:unit`；`ci.yml` 未被 `paths-ignore` 排除，会运行补丁校验、`patch-build` 与新加的扫描入口审计。

边界与未验证项：

- 以上是软件证明与编译验证。没有连接真实串口、没有烧写、没有运行真实 Wi-Fi 扫描/NVS/HA 实体/驱动拒绝/重连/漫游；没有提交或推送；G2-01～G2-07 仍为 `not_run`。
- 结论只覆盖经过单一入口的启动：补丁保证“至多一个未完成扫描”，完成事件按预留分类；没有证明任意外部驱动/ESP-IDF 版本都不会产生无主事件。若完成事件丢失，系统按设计保持 fail-closed，而不是猜测结果。
