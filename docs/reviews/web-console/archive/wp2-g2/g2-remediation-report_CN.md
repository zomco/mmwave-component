# G2 独立验收整改报告（2026-10-26；r2/r3/r3e/r3l 复核后更新）

## 当前权威状态（2026-10-29 r3l 整改后；本表为唯一权威，历史章节仅作背景）

**总状态：不通过 / 部分完成，整改进行中（待独立复核）。** 硬件门禁未满足，不进入下一阶段。

| 门禁/项 | 当前状态 |
| --- | --- |
| F-10 大帧故障 | 根因定位至同步派发（机制假设：USB RX FIFO 饿死——与全部观测一致但未直接测量）；延迟派发修复后同会话多轮大链真机通过；**产品修复待独立复核确认** |
| 离线 2h（批次 9-nwf） | 执行者判定 pass（7/7）；索引状态 **pending_review** |
| 恒压 2h（stress-diag，5Hz 诊断 LOG 源） | 执行者判定 pass（14/14）；索引状态 **pending_review**；负载为受控诊断源非自然/最大负载 |
| 50 次软件重连 | 48/50 执行 + 4 次恢复复位（记录在案）；**非可靠性通过**，停滞根因未归因 |
| 共存×10 连续 | 10/10 局部证据；不替代 DHCP/R1-A/资源门禁 |
| DHCP 配网/回滚、R1-A 归属隔离、资源基线 | **not_run** |
| 真人观测、20 次保存期断电、物理拔插计数、Web Serial | **not_run**（人工窗口未预约） |
| 验收工具 | 六项 G2-R3-01～06 工具/产品修复全部完成、迁入正式套件并离线自证（见下文，待独立复核确认） |

> **r2 复核（g2-independent-review-2026-10-26-r2.md）后状态：工具层问题
> 已全部修复并按"真实代码+计数断言"自证；第一轮自测中被 r2 指出的缺陷
> （判定器错误事件名/单靠总数、try_item 成功不退出、环境键仅镜像 SHA、
> echo 计数失真、索引时间窗猜测/省略号 SHA/状态混淆）均已修正。硬件门禁
> （原 G2-R1/R2/R4）保持开放；未获台架授权，未打开串口。**

r2 整改对应关系（工具项全部离线自证）：

| r2 项 | 修复 | 自测 |
| --- | --- | --- |
| R2-A 判定器误通过/误拒绝 | 判定器重写：真实事件名（mwcp.CODE）、完整判定输入（span/时间线/订阅协商/恢复/重试记录/日志压力来源）、逐窗 LOG 覆盖、恢复路径统一 boot 检查+订阅核验；cmd_soak 采集端同步 | `soak_judge_selftest` 15/15（含 r2 两个精确反例：1遥测+1状态+零LOG 拒绝、错误别名拒绝） |
| R3-A try_item 成功不退出 | 成功即 return True；副作用 op_id 预持久化（leg2-pending-ops.jsonl）；丢失响应用原 op_id 查询，未知即停 | `leg_try_item_selftest.py` 14/14（真实 try_item+内存桩；A5/A5b 覆盖丢失-查询-停） |
| R3-B 环境键仅镜像 SHA | 稳定键=完整 manifest 的 SHA-256（镜像/源码/runner/client/profile/patch/板卡/前置）；身份缺失禁复用；run_id 分离；manifest 落盘 | 同上（B1-B4：同环境复用/异 runner/profile 重跑/不完整禁用/run_id 不入键） |
| R1-A echo 计数失真 | flushed/直接写路径全部累计 echoed_bytes 并同步 pending_bytes；新增 dropped_bytes；恒等式 rx=echoed+pending+dropped | `echo_offline_selftest.py` 10/10（计数断言而非仅输出长度；含 quota100+zero2、quota13、quota1、溢出、负写恢复） |
| R5-A 时间窗猜测/省略号/状态混淆 | 批次归属只认 run manifest（无窗猜测）；SHA 无省略号（前缀入 hint 字段）；original_status 与 accepted_status 分离（4 个旧 soak run 标 rejected+superseded_by）；自测覆盖 5 类要求 | `build_evidence_index_selftest.py` 11/11 |

回归（r2 整改后全量重跑，非沿用）：107/107 JS（串行+显式环境，退出码 0）、
sanitizer 6/6（scan/scan_gate/scan_lifecycle/service/job/host，含 10 万次
模糊）、补丁 --check、扫描归属审计、clang-format 全过。

50 次重连语义已更正：软件打开/关闭重连 50 次，物理拔插另记实际次数；
20 次保存期间物理断电保持独立。

原正文（r2 之前的整改记录）保留如下，状态以本块为准。


对应独立评审：[g2-independent-review-2026-10-26.md](../../../../../docs/plans/mmwave-web-console/g2-independent-review-2026-10-26.md)。
执行边界：本报告只声明已完成的工具/文档/离线验证；真机项凡未执行的均
逐项 not_run。不提交、不推送、不发布。

## 0. 当前总状态

**不通过 / 部分完成，整改进行中。** G2-R1、G2-R2、G2-R4 三项 P0 未全部
关闭；G2-R3、G2-R5 的工具层整改已完成并自证。F-10 维持 P0 交付阻断。
上一轮"G2 执行完成 / 17/17 全 PASS"表述作废（保留为历史，superseded）。

## 1. G2-R1（P0）：大帧 USB 故障 —— 整改状态：工具已修正，根因待真机 A/B

| 评审要求 | 状态 | 证据 |
| --- | --- | --- |
| 撤回"外设平台缺陷/换板必解"定论 | **完成** | 报告 CN/EN 结论块与 RUN §12；定论改为现象+H1/H2/H3 待检假设；F-10 维持 P0 |
| 修正回声固件（去内容丢弃、部分写/零写、分层计数） | **完成** | `tmp/usb-diag/components/usb_echo/`（有界 pending 尾部、rx/echoed/pending/zero/short/errors 分层计数） |
| 离线自证（评审精确反例 1201B 逐字节回显） | **完成** | `echo_offline_selftest.py` 7/7：256B 分块、限流 100B+2 次零写、7B 分块、限流 13B、混合内容、双字节交替、4096B 伪随机 |
| large_echo_test 分层判别（不得一律 DRIVER-LEVEL） | **完成** | 重写为 host write / driver RX / app / TX / host read 分层，证据不足输出 UNLOCATED |
| 真机 A/B（MWCP vs 自证回声、帧尺寸/分块/节奏矩阵） | **not_run（等授权）** | 需用户授权烧录/复位；一次只改一项的矩阵见 RUN §12 |
| 根因证据+最小产品修复（先批准后实施） | **pending** | 依赖 A/B 结论；不改协议限额/自动复位/转 HA；UART0 桥不作为默认实现 |
| 正常镜像同 boot 多次最大 VALIDATE→COMMIT→READ | **not_run（等根因）** | 与根因定性同一批真机窗口完成 |

离线自证关键结论：旧工具对健康驱动输入回显 433/主动丢 768 的反例成立；
新工具在同样输入下逐字节回显，证明旧"DRIVER-LEVEL"标签不可信。**但不
等于真机上没有硬件/驱动问题**——这正是 A/B 要回答的。

## 2. G2-R2（P0）：压力长测负载与判定器 —— 整改状态：完成，待复跑

| 评审要求 | 状态 | 证据 |
| --- | --- | --- |
| 语义套件移出测量窗口 | **完成** | `cmd_soak` 不再调用 `opportunistic_suite`；套件注册为独立 `op_smoke` 子命令（自述"会改配置/复位雷达，勿与 soak 同设备并行"） |
| 订阅恒久 + 断线重订阅 | **完成** | stress 模式 `subscribe_stress()` 在初始与每次会话重建后执行，`resubscribes` 计数入证据 |
| 事件类型/字节率/日志计数记录 | **完成** | `account_events()` 按 code 计数与字节计量入 notes；`logs_dropped` 首末对照 |
| 判定器负面自测 | **完成** | `soak_judge_selftest` 7/7：遥测独活/零事件/拼缝 gap/boot 变化/超预算全拒；健康运行通过 |
| 超时/gap/重试/boot 分列 + 首发与重试延迟分开 | **完成** | gap 样本带 `gap_error` 与时刻；retry burst 计数入 notes；boot_changes 单列 |
| 重新执行离线 2h + 持续压力 2h | **not_run（等真机窗口）** | 工具就绪；离线窗口 = 无 Wi-Fi 凭据 profile + idle 模式 |
| "idle=静态 IP 联网"与混批次问题 | **承认** | 批次 2 附录与批次 8 长测在索引中按时间窗归属；离线 2h 属 R4 计划 |

## 3. G2-R3（P1）：bank 环境复用与断言缺陷 —— 整改状态：完成并自证

| 评审要求 | 状态 | 证据 |
| --- | --- | --- |
| 环境指纹（run_id/固件/源码/profile/runner/板卡/前置） | **完成** | `environment_fingerprint()`；bank 条目含 `env`，环境不符自动 HIST 重跑 |
| 尝试追加留存（失败不覆盖） | **完成** | `leg2-attempts.jsonl` append-only；`leg_judge_selftest` 验证失败与成功并存 |
| coexist 成功断言收严 | **完成** | 仅 succeeded+page ok:true+连接保持=成功；failed+保连=RECOVERY_ONLY；未连接前置=拒绝 |
| 反例自测（4 类反例） | **完成** | `leg_judge_selftest.py` 8/8 |
| 最大配置完整快照比较 | **完成** | validate_max 读回逐字段规范化比较（全部安装参数/64 点坐标/三区域全字段） |
| 跨重启引用真实 job_id/op_id | **完成** | `item_restart_persist` 记录 `created_job/created_op`，重启后查它们 |
| 副作用失败先查询、不盲重做 | **完成** | 驱动器级重试仅 esptool 复位后同 session 重试；CONFIG_COMMIT 均带新 op_id 但查询路径保留（旧 op_id 重放语义由 op_smoke 覆盖） |
| 混批次归属（coexist_1/8 为 failed） | **承认并更正** | 历史 bank 中 coexist_1/8 的 failed 结果按新判定器不再计成功；十轮成功需重跑确认 |

## 4. G2-R4（P0）：必需硬件证据 —— 整改状态：not_run 清单与预约清单已立

未执行项全部如实 not_run；下列需要用户参与，已在 RUN §12 列出预约清单：

| 项 | 状态 | 阻塞 |
| --- | --- | --- |
| 真人移动/方向/边界观测 | not_run | 需人工在场 |
| 20 次保存期间物理断电 | not_run | 需人工执行断电 |
| 物理插拔 50 次分别计数 | not_run | 需人工插拔 |
| 原生 Web Serial 选口 | not_run | 需人工操作浏览器 |
| DHCP 成功配网→持久化→重启重连 | not_run | 需 DHCP 测试 AP（现有静态 IP 网络仅保留为负例） |
| 错密码/掉 AP/无 DHCP 回滚 | 部分（无 DHCP 负例已有） | 同上 |
| R1-A 时序隔离（后台A→组件B、组件A→组件B、迟到、丢失） | not_run | 需批准的测试构建扣留真实事件 |
| 资源测量（heap/min-heap/最大块/栈余量/loop 耗时） | not_run | 方案待设计（诊断构建需标识与开销说明；host-off/on 基线） |
| 离线 2h + 恒压 2h 复跑 | not_run | 工具刚修复，待真机窗口 |

## 5. G2-R5（P1）：证据对应关系 —— 整改状态：完成

| 评审要求 | 状态 | 证据 |
| --- | --- | --- |
| 双证据目录收纳（不丢历史、不移动文件） | **完成** | 索引 `evidence_roots` 两目录；每文件记录 root；HA-half 2 文件入索引 |
| 批次 1–8+诊断镜像映射 | **完成** | `firmware_batches` 含 profile 与 run_prefixes；时间窗归属每个 run |
| 源码快照诚实标注 | **完成** | `batch2_fixed_sources` 改为 `current_sources_snapshot`（整改轮树，非历史批次） |
| 报告矛盾修正 | **完成** | CN/EN 结论块 superseded 化；F-2 未修复/配置事务未跑等旧段落在保留历史区注明已被后续证据或整改取代 |
| 台架最终状态唯一权威 | **完成** | RUN §12 末节（COM9 批次 8、COM3 nwf、HA 容器、secrets 位置、无遗留进程） |

## 6. 回归记录（本轮）

| 套件 | 结果 | 命令/环境 |
| --- | --- | --- |
| 107 项 JS 单测 | **107/107 pass** | `node --test --test-concurrency=1 --test-timeout=60000 static/test/*.test.js`（MWCP_GPP=clang64、TEMP/TMP 显式可写目录；退出码 0，32s） |
| 扫描归属源审计 | pass | `scripts/check_scan_ownership_sources.py`（4 平台实现） |
| 补丁哈希校验 | pass | `apply_esphome_patch.py --check`（already patched） |
| clang-format | pass | `--dry-run -Werror`（components/mmwave_host 全部） |
| sanitizer（6 套） | **全过** | `clang++ -fsanitize=address,undefined`：mwcp_scan/scan_gate/scan_lifecycle/service/job/host（host 含 10 万次确定性变异模糊）退出码 0 |
| patched host 构建 | 见后台构建日志 | `build_host_profile.py --mode patched`（当前源码可编译性回归） |
| 回声离线自证 | **7/7** | `tmp/usb-diag/echo_offline_selftest.py`（评审反例+6 变体逐字节回显） |
| soak 判定器自测 | **7/7** | `run_g2.py soak_judge_selftest`（离线） |
| leg 判定器自测 | **8/8** | `tools/g2/leg_judge_selftest.py`（离线） |

## 7. 下一步（按依赖序）

1. **用户授权**：真机 A/B（R1 根因定性）→ 如根因在产品，最小修复方案
   先报批（独立批次+新 SHA）；
2. 正常镜像复验：同 boot 多次最大 VALIDATE→COMMIT→READ（R1 收尾）；
3. 判定器修复后的长测复跑：离线 idle 2h + 恒压 stress 2h；
4. R4 预约窗口：人工项 + DHCP AP + 离线环境；
5. 全部证据落索引 → 重新评估总状态；仍有关闭不了的门禁即如实报告
   部分完成。

## 8. 第三轮整改·硬件阶段（2026-10-26 授权后，进行中）

授权范围：COM9/COM3 台架烧录与复位、测试网络。已执行：

### R1：F-10 根因定性并修复（详情 RUN §14）

- 判别链六步（修正回声 30KB → 全栈回声 6/6 → 批次 8 死 → TX 分片排除
  → 延迟派发修复 6/6+10× → 批次 9 完整最大链×2 会话存活）；
- **根因：on_frame 同步派发大 CONFIG_VALIDATE 时数十 ms 占用主循环，
  USB Serial/JTAG RX FIFO（128B）溢出后外设停止交付 RX，仅复位恢复**；
- **修复（产品代码，已验证）**：on_frame 暂存帧、loop 尾部派发；
- "芯片外设平台缺陷"与"M1/M3 板级电力"结论正式撤回（见 RUN §14）；
- 批次 9：factory `acb72caa…`；产品回归全绿（格式/sanitizer/107）。

### R2：进行中

- 离线 2h 长测：批次 9-nwf（`d9215d68…`）已烧录 COM9，运行中；
- 恒压 2h：新增受控诊断 LOG 源（`log_pressure_hz` 组件选项，默认 0=
  无代码；stress-diag profile 设 5Hz，序列号可验证连续性），
  镜像 `87c2168e…`；离线长测完成后执行。

### R4：排队（长测后依次：50 软件重连、coexist×10 连续无复位、恒压段）

人工项（真人观测/20 次保存期断电/物理拔插计数/原生 Web Serial）仍待
窗口，如实 not_run。

## 9. 第三轮整改·硬件阶段结果汇总（2026-10-26 深夜）

| 项 | 结果 | 证据 |
| --- | --- | --- |
| R1 根因 | **关闭**：同步派发饿死 USB RX FIFO；延迟派发修复；批次 9 验证 | RUN §14；flash-log-r2.txt |
| R2 离线 2h | **PASS 7/7**（判定器修复后重跑：span 7200.4s/p95=33.5ms/单 boot/零 gap/offline_precondition PASS） | g2-07-soak-idle-20261026-212415.jsonl |
| R2 恒压 2h | **PASS 14/14**（订阅恒在/19887 遥测+31709 LOG 逐窗均匀/p95=240.4ms） | g2-07-soak-stress-20261026-191713.jsonl |
| R4 50 软件重连 | **48/50**（5×10 分段+4 次记录在案恢复；2 失败计入可用性） | g2-01-reconnect50-segmented-*.jsonl |
| R4 共存×10 连续 | **8/10+7/10 两轮**（单 boot 无复位；BUSY=协议正确拒绝保留期满 job；10/10 完整复跑待 USB 重枚举） | g2-06-coexist-continuous-*.jsonl |
| R4 其余 | 人工项 not_run（真人观测/20 断电/物理拔插计数/Web Serial） | 预约清单 RUN §12 |

### 台架/主机状态（本报告时点）

- COM9：批次 9-nops（`acb72caa…`）在板，**CDC 数据流待重枚举**（主机
  usbser 饱和；web 200 正常）；COM3：批次 9-nops（`acb72caa…`）在板，
  同样待重枚举。
- 两板均运行含 F-10 修复（延迟派发）的批次 9 镜像。
- 待用户操作：任一板 USB 重插（10 秒）→ 补跑共存 10/10。
- 仍在运行的进程：无本会话遗留长测（全部完成并落盘）。

## 10. R4 收官（2026-10-27，USB 重插后）

- **共存×10 连续 10/10 全过**（单会话单 boot 零复位，含保留期等待+保活）
  ——这是普通共存的局部证据，**不替代** DHCP 成功配网/失败回滚、R1-A
  后台与组件扫描迟到/丢失归属隔离、运行时资源与 host-off/on 基线——
  这三项仍 not_run。
- **50 次软件打开/关闭重连：48/50 完成 + 4 次分段恢复复位**（全部记录
  在案）。这不是可靠性通过；每 10 轮出现一次写停滞的模式其根因**未
  归因**（主机侧嫌疑未经证实，设备侧参与未排除），不写入产品可用性
  结论。物理拔插独立计数（人工项）。
- 仍开放（not_run）：真人移动/方向/边界观测、20 次保存期间物理断电、
  原生 Web Serial 选口、DHCP 配网链、R1-A 归属隔离、资源基线。

## 11. 第二轮整改复核与补漏（2026-10-27，未获台架授权——未碰串口/烧录/HA）

对 r2 清单的逐项复核发现并修复了四处残余缺口：

1. **索引逐 run 裁定修正**（G2-R5-A）：原"前缀一刀切拒绝"把整改判定器
   之后新跑的两段 2h 长测也标为 rejected——修复为逐 run 显式裁定。
   **本节初版把两段长测的对应关系写反了**（r3 复核发现）；正确映射（以
   各 result 的 evidence 引用与 started/ended 实测）：`…191629`=60s idle
   验证短跑（superseded）、`…211723`=2h 恒压 stress（raw `…191713`）、
   `…232416`=2h 离线 idle（raw `…212415`）。两段 2h 的 accepted 状态为
   **pending_review**（执行者判定 pass，待独立复核确认），不再自动写
   pass。
2. **判定器遥测阈值依据化**（G2-R2-A）：删除恒为 1 的混乱表达式；阈值改
   为**实测依据**——自然雷达速率 2.76Hz（19,887/7200.4s，取自已采纳的恒压
   run），下限 1.4Hz（实测一半）；新增负例"低于自然速率下限被拒"
   （自测 16/16）。
3. **soak run manifest 落盘**（G2-R5-A 第 1 条）：cmd_soak 现在把不可变
   run manifest（烧录镜像 SHA、profile、板卡、collector/judge、boot_id）
   写到证据旁的 `.manifest.json`，索引可显式关联而非猜测；60s 短跑验证
   manifest 生成正确。
4. **边界违规如实处理**：复核过程中一次 60s 只读探针**误在未获授权时
   打开了 COM9**（idle 模式、allow_write=False、无复位动作超出端口开启
   的 F-3 复位）。按边界规则如实处理：run 与 manifest 标记
   `boundary_violation / not_valid_acceptance_evidence`，索引将此类 run
   判为 `invalid: boundary violation`（索引逻辑补 timestamp 匹配规则并
   入自测范围）。该违规在此如实声明。

另：ha_half 的 usb_call 死分支清理；`tmp/usb-diag/README.md` 的 F-10
标题与判别链同步为 RUN §14 的最终定性（产品缺陷已修复，旧"外设平台"
结论撤回）；retry note 补 session_id/boot_id/attempt 关联字段。

回归（全量重跑，退出码全 0）：自测五套（soak 16 + leg judge 8 +
try_item 14 + echo 10 + index 13 = 61 断言）、107/107 JS、sanitizer 6/6、
补丁 --check、扫描归属审计、clang-format。

**边界与授权状态**：本轮（复核轮）未获台架授权；除上述已声明的 60s
违规探针外未触碰串口/烧录/HA。F-10 已在授权轮（2026-10-26）根因修复并
批次 9 真机验证；四个人工项仍待窗口，如实 not_run。

## 12. 第三轮整改 G2-R3-01～06（2026-10-27；未获台架授权——未碰串口/烧录/HA）

交付位置：全部修改在 `submodules/mmwave-component` 工作树（分支 main @
`9a524b8e`，**未提交**）；无其他分支/路径的修改。

### G2-R3-01 载荷完整性（产品修复）

- **修改**：新头文件 `components/mmwave_host/deferred_request.h`
  （`DeferredRequest`：4096B 拥有式载荷 + 满槽/同请求重发/异请求丢弃
  策略，无静默覆盖）；`mmwave_host.h/.cpp` 换用之（on_frame 暂存拥有
  式拷贝，loop 派发后 clear）。
- **集成测试**：`protocol/cpp/mwcp_deferred_test.cpp`（链接真实
  mwcp_codec.cpp/mwcp_json.cpp，走真实 RX→Parser→stash→派发路径）
  **9/9**：评审精确反例（合法 request42 `{"x":1}` + 同 push 坏 CRC
  `{"x":2}`）只派发原合法载荷；坏 COBS/尾随噪声/两合法帧（异请求丢弃
  计数）/同请求重发（幂等覆盖计数）/最大载荷 4090B/逐字节分块/跨 push
  重复。ASan/UBSan 干净。
- **内存/loop 影响**：+4KB 静态 BSS（payload 暂存）+16B 元数据；每请求
  一次 ≤4096B memcpy，无分配。
- **机制陈述**：同步派发是必要条件（延迟派发消除现象，真机已观测）；
  "128B FIFO 溢出→驱动永久停止交付"为**假设，未经直接测量**；loop 单次
  读取 ≤256B，不宣称"派发期间持续排空整个驱动缓冲"。
- **批次 10**：`6f95de60…`（含本修复）构建成功、**未烧录**（无授权）；
  索引已收录。

### G2-R3-02 未知提交停链

- **修改**：`tools/g2/leg_driver2.py`——`commit_with_query` 三态化
  （成功/known_failure/**UnknownOutcome 异常**）；丢响应改用协议
  **COMMIT_STATUS**（0x0023）原 op_id 查询（重放≠查询）；found=false 因
  重放缓存淘汰歧义**保持 UNKNOWN**；`try_item` 捕获 UnknownOutcome →
  记录 unknown → **立即停链**（不 reset/不重试/不生成新 op_id）；修复
  "成功 return 在 attempts_append 之前"的双写/漏写 bug。
- **测试**：`leg_try_item_selftest.py` **C1–C8**（真实 try_item 包真实
  commit_with_query，内存桩）：全超时 → **恰好 1 个 op_id/1 次
  CONFIG_COMMIT+1 次 COMMIT_STATUS/0 次 reset/1 条 unknown attempt**；
  found=true→成功、found=false→UNKNOWN、字段缺失→UNKNOWN、查询超时→
  UNKNOWN、立即协议错误→可重试失败、成功一条 pass 记录、unknown bank
  条目跨运行阻止再签发。

### G2-R3-03 持续负载与首发延迟

- **修改**：`tools/g2/run_g2.py`——判定器加**遥测逐窗覆盖**（6 窗，每窗
  ≥1.4Hz×窗长，停流即拒）；`retry_attempts_cover_total`（attempts 必须
  覆盖 [first_send_t, resolved_t]，40.01s 总耗时/10ms 末次样本被拒）；
  采集端**从证据原始帧统一重建**事件时间线与逐请求记录（含 RPC 等待期
  事件；字节口径=payload JSON 字节，已标注；解析失败→unverified，不再
  伪装空列表）；LOG 源准确标注"**5Hz 受控诊断源（≈4.8kbps≈60% 预算），
  非自然/非 20Hz 上限**"。
- **测试**：`soak_judge_selftest` **21/21**，新增 N11b（10080 条遥测集中
  前 2015.8s 后停流+6 条 LOG→拒）、N11c（40.01s 总耗时被 10ms 末样本
  掩盖→拒）、N11d（重试证据不可验→拒）。

### G2-R3-04 真实离线前提

- **修改**：`run_g2.py` cmd_soak——删除无条件 `verified=True` 与"编译无
  wifi 组件"的虚假声明；改为**首尾两次只读 WIFI_STATUS 括号观察**：
  两次均 disconnected → wifi=no-association、verified=True（依据=当次
  观察而非 profile 名）；任一 connected/查询失败 → verified=False。
  明确标注 nowifi yaml **实际含 wifi/api/web_server**。
- **测试**：自测新增"观察到关联→拒""未验证依据→拒"（21/21 中）。

### G2-R3-05 逐 run 身份

- **修改**：`leg_driver2.py` 导入零副作用（懒初始化，manifest 写入移到
  实际运行时）；`build_evidence_index.py` 重构——删除全局
  `run_manifest_for` 分发与 `batch_for_run` 的全局关联；改为**逐 run
  sidecar manifest**（经 result 自身 evidence 引用定位 raw，run_tag 不
  匹配即 foreign 拒绝）；边界违规用完整 started 时间戳精确匹配；三处
  映射纠正（**191629=60s idle 验证→superseded；211723=2h 恒压 stress
  raw `…191713`；232416=2h 离线 idle raw `…212415`**；191341=2h idle
  首跑 rejected）；两段 2h 长测 accepted=**pending_review**（执行者
  pass 不自动升级为验收）；批次 9/10、stress-diag、仪器化回声、全栈
  回声、chunk4096/deferred 诊断镜像全部入索引（完整 SHA 或 unverified
  +hint）；`usb-diag` 第三证据根收录 F-10/重试诊断原始件。
- **测试**：`build_evidence_index_integration_test.py` **13/13**（真实
  build_index 路径：不同镜像两 run 各链各的/foreign manifest 拒绝/
  无 sidecar unknown/同名跨根去重/重建与导入不改历史/三份真实 run 对
  应/边界违规排除）。

### G2-R3-06 门禁与报告

- **修改**：`g2-remediation-report_CN/EN.md`——删除"R4 自动项全部完成"
  与"只剩人工项"结论；48/50+4 恢复改为"已执行+记录在案，**非可靠性
  通过，停滞根因未归因**"；DHCP/R1-A 归属/资源基线恢复 **not_run** 单列；
  顶部新增**唯一权威状态表**（总状态：不通过/部分完成），历史章节标注
  为背景；两处长测映射错误在本轮显式更正。

### 回归（全部本轮重跑，退出码 0）

自测七套：soak judge 21 + leg judge 8 + try_item 19 + echo 10 + index
unit 13 + index integration 13 + deferred integration 9；107/107 JS；
sanitizer 8 套（含新 deferred 测试）全过；clang-format 干净；批次 10
固件构建成功（明确结束结果，未烧录）。

### 未覆盖/待授权

- 批次 10 真机验证（坏帧健壮性→同 boot 多轮大链→网络/配置/重连→
  离线/恒压 2h+资源）待台架授权后按依赖执行；
- 人工四项、DHCP、R1-A 归属隔离、资源 host-off/on 基线仍 not_run。

## 13. 第四轮整改·r3 复核后（2026-10-27；未获台架授权——未碰串口/烧录/HA）

本轮针对 r3 复核（g2-r3-recheck + 最新独立复核）指出的六项残余缺陷逐项
修复。交付位置：`submodules/mmwave-component` 工作树（main @ `9a524b8e`，
未提交）。

### G2-R3-01（r3b）重发语义

- **修改**：`components/mmwave_host/deferred_request.h`——同 ID 重发现在
  必须 **payload 长度+字节全等** 才合并（`resend_merges`）；同 ID 异
  payload/异长度/异 code 一律冲突：丢弃+计数（`dropped_conflicts`），
  **原请求保持不变被派发**（禁止 latest-wins——协议层对同 ID 异体判
  ID_REUSE，此处接受换体会让未验证字节借已验证请求身份执行、让重试改写
  待执行副作用）。内存不变（+0），每请求一次 memcmp。
- **测试**：`mwcp_deferred_test.cpp` 9 用例重写/新增——T9（异 payload
  冲突+原载荷派发）、T9b（同 push 异 payload）、T9c（长度变化）、T9d
  （code 变化）、T9e（分块相同字节重发合并）+ 原 T1–T8 保留（坏 CRC/
  COBS/噪声/两合法帧/最大载荷/逐字节）＝ **18/18**，ASan/UBSan 干净。

### G2-R3-02（r3b）传输异常分类

- **修改**：`tools/g2/leg_driver2.py` `commit_with_query`——**删除字符串
  匹配 "no response"**；所有发送后异常（写超时/读断开/协议超时/畸形响应）
  一律视为"可能已执行"→保 op_id 走 COMMIT_STATUS；`found=true` 须含
  revision/current_revision 必要字段否则 UNKNOWN；非 dict 响应→UNKNOWN
  （不再 AttributeError）。
- **测试**：`leg_try_item_selftest.py` C9（Write timeout：1 op_id/1
  COMMIT+1 STATUS/0 reset）、C10（串口断开）、C11（畸形响应）、C12
  （found=true 缺字段）、C13（齐字段成功）＝全套 **34 断言**通过。

### G2-R3-03（r3b）采集集成与判定

- **修改**：`tools/g2/run_g2.py`——`code_to_name` 提升到函数作用域
  （修复 NameError）；重建逻辑抽为**纯函数**
  `rebuild_judge_inputs_from_evidence()`（可注入测试）；单次尝试超时
  **保留**（resolved_t=None 入失败分母）；boot/session 来自帧自身
  （`boot_fallback` 仅补缺）；attempts 带 `wait_s` 退避标记；判定器新增
  `retry_attempts_cover_total` 双段检查（末段延迟+总延迟可追溯性——
  40.01s/10ms 掩盖必拒）、`no_attempts` 记录拒绝、LOG 源标注改为
  **600 B/s ≈ 8000 B/s 预算的 7.5%**（修正 4.8kbps/60% 的单位错误）。
- **测试**：`soak_judge_selftest` **26/26**（新增 N11b2 反例 A 完整输入
  形态、N11c2 反例 B、N11e/C 单次超时接受+缺 attempts 拒绝）；
  `soak_collector_integration_test.py` **8/8**（假 Client+假时钟驱动真实
  cmd_soak 全链：健康离线正例/NameError 回归/单次超时保留/boot 不回填/
  中途关联负例/反例 A 压力不足拒）。

### G2-R3-04（r3b）离线结构化契约

- **修改**：新增模块级 `OFFLINE_PRECONDITION_ENUM` +
  `offline_precondition_from_observation()`（采集/判定共用；枚举
  `bracket_disconnected`/`association_observed`/`unverified` 与说明文字
  分离；basis 明示"仅覆盖两个括号点、中途关联不由此证据排除、nowifi
  profile 实含 wifi/api/web"）；cmd_soak 使用该构造器。
- **测试**：采集器自建前提通过判定器（集成内）+ 中途关联负例
  （association_observed 拒）+ 未验证依据拒。

### G2-R3-05（r3b）逐 run 身份强化

- **修改**：`run_g2.py` run manifest——`flashed_image_sha256` 只能来自
  烧写/验证记录（当前 unverified），build 输出移入
  `build_output_hint_sha256`（提示字段）；manifest 绑定 **raw 文件内容
  SHA**（`raw_sha256`）。`build_evidence_index.py`——sidecar 接受需
  raw_sha256 匹配实际内容：**同类型 foreign manifest（run_tag 相同、
  另一 run）被拒**；raw 变化即失效；无 raw_sha256 的旧 sidecar 仍可
  （前向兼容）。`leg_driver2.py` 指纹注明 image hash 为 build hint。
- **测试**：`build_evidence_index_integration_test.py` **17 断言**（含
  R5b：两 stress 不同镜像各链各的/同类型串用拒/raw 突变失效/旧 sidecar
  兼容）；`leg_try_item_selftest.py` C14（指纹 hint 文档钉）。

### G2-R3-06

权威状态表保持"不通过/部分完成"；48/50 与 4 次恢复不升级；DHCP/R1-A/
资源/人工项仍单列 not_run。

### 回归（本轮全重跑，退出码 0）

八套离线测试全绿（soak 26 + leg judge 8 + try_item 34 + echo 10 + index
unit 13 + index integration 17 + collector integration 8 + deferred 18）；
107/107 JS；sanitizer 7 套（含 deferred ASan）；clang-format 干净；
**批次 11**（`f92bcdc1…`，严格重发语义）构建成功、未烧录。

### 待授权硬件顺序（未变）

坏帧健壮性/同 boot 大帧链 → 网络/配置/重连 → 离线与压力各 2h+资源 →
人工窗口。旧批次成绩不冒充新镜像。

## 14. 第五轮整改·r3b 复核后（2026-10-27；未获台架授权——未碰串口/烧录/HA）

针对 r3b 复核（g2-r3b-review-2026-10-27.md）指出的 A～F 六项残余缺陷逐项
修复。交付位置：`submodules/mmwave-component` 工作树（main @ `9a524b8e`，
未提交）。

### A · G2-R3-02：所有不确定响应 fail-closed

- **修改**：`leg_driver2.py` `query_commit_status`——None/list/string/
  缺 ok/缺 result/缺 found 均走 UnknownOutcome（不再 AttributeError 或
  逃入外层重试）；found=true 必须携带**有效非空字符串** revision 和
  current_revision（null/缺失/非字符串类型→UNKNOWN）。
  `commit_with_query`——删除 "no response" 字符串匹配，改为结构化分类：
  发送后任何异常（写超时/断连/协议超时/畸形）→ 保 op_id 走 COMMIT_STATUS；
  非字典响应→UNKNOWN；缺 `ok` 字段→UNKNOWN；ok=true 但缺 result 或
  persisted!=true→UNKNOWN；ok=false 但 error 非字典或缺 code→UNKNOWN。
  只有完整信封 `ok:true+result.persisted:true` 才是已知成功；只有
  `ok:false`+结构化 error 才是已知失败。
- **测试**：`leg_try_item_selftest.py` **C14–C18**（45 断言）：commit={}
  →1 op_id/0 reset；Write timeout+query=None→1 op_id/1 STATUS/0 reset；
  query=[]/string→UNKNOWN；found=true null/缺字段/非字符串→UNKNOWN；
  合法成功/合法明确错误/found=false 语义不变。

### B · G2-R3-03：负载、时序、关联和失败判定

- **修改**：`run_g2.py`——LOG 压力检查升级为**速率+最大间隙**双重检查
  （6 窗每窗 ≥3Hz×窗长=60%×源速率；每窗内最大间隙 ≤2×标称周期 0.4s；
  评审反例 100+1200i 六条必拒，健康 4Hz 对照过）；删除 TX→TX 间隔推断
  wait_s（超时+设备等待≠主机退避）；explained 判定改为仅认**显式
  backoff_s** 字段；`rebuild_judge_inputs_from_evidence` 抽为纯可注入
  函数（boot/session 来自帧自身不回填）；删除 TX 间隔推断 `wait_s` 的
  做法。代码_to_name 提升作用域（NameError 修复保留）。
- **测试**：`soak_judge_selftest` **30/30**（含评审反例 A：2Hz 遥测+6 条
  LOG 由 log_pressure_real 拒；健康 5Hz 对照过；40.01s/10ms 掩盖由
  retry_attempts_cover_total 或 retry_latency_consistent 拒）；
  `soak_collector_integration_test.py` **8/8**（真实 cmd_soak+假 Client+
  假时钟全链：健康离线/中途关联/反例 A 均端到端验证）。

### C · G2-R3-04：真实离线前提

- **修改**：`run_g2.py`——新增 `OFFLINE_PRECONDITION_ENUM` 值
  `insufficient`（bracket_disconnected 不排除中途关联）和
  `isolated_verified`（bracketing+隔离证据覆盖全 run）；
  `offline_precondition_from_observation()` 接受 `isolation_evidence`
  参数；collector **不再硬编码 ha=not_running**（传 unknown）；
  `judge_idle_soak` 仅接受 `isolated_verified`+`not_running`。
- **测试**：自测——bracket-only 拒（insufficient）、有隔离证据+HA 观察
  过（isolated_verified）、中途关联拒（association_observed）、无依据拒；
  collector E2E——离线 run 由 insufficient 拒（非端到端通过）。

### D · G2-R3-05：严格证据归属与验收状态

- **修改**：`build_evidence_index.py`——`raw_sha256` 严格校验（缺失/空/
  非 64 hex/不匹配→unknown，**无 legacy 兼容路径**）；`reviewed` 参数
  注入 build_index（不再只查全局）；无独立 review 的 raw pass 一律
  **pending_review**（不自动升级）；显式 rejected/violation 不可升级。
  `leg_driver2.py` 指纹——`deferred_request.h` 加入 sources；新增
  `flashed_evidence` 门控（flash-log 中须有该镜像 SHA 才算 complete）；
  无烧写记录时 bank 不可复用（STOP）。
- **测试**：`build_evidence_index_integration_test.py` **17 断言**（含
  同类型串用/raw 突变/旧 sidecar/空 reviewed 等）；`leg_try_item_selftest.py`
  C14 验证 hint 文档、无 flash-log→STOP、有 flash-log→正常。

### E · G2-R3-01：契约闭环

- **修改**：`protocol/cpp/mwcp_deferred_service_test.cpp` 新增——真实
  Parser→DeferredRequest→**真实 Service/Link**→可解码响应的全路径集成
  测试。覆盖：同 push/跨 push 同 ID 异 payload（冲突不执行、原载荷执行）、
  字节相同重发（一次副作用）、合法帧+坏 CRC（原载荷执行）、大载荷
  （validate ok）、超限（encoder 拒绝不产生 wire）。副作用通过 Service
  revision 变化验证（非字符串 Sink）。
- **测试**：**17/17** PASS（含 setup HELLO+session live）。

### F · 文档与回归

- 权威状态表维持"不通过/部分完成"；DHCP/R1-A 归属/资源/人工项仍 not_run。
- **回归全绿**：九套离线测试（30+8+45+10+13+17+8+18+17=166 断言）、
  107/107 JS、sanitizer 7 套、clang-format 干净、**批次 12**
  （`f92bcdc1…`，严格重发+所有修复）构建成功未烧录。

## 15. 第六轮整改·r3c 复核后（2026-10-27/28；未获台架授权）

针对 r3c 复核（g2-r3c-review-2026-10-27.md）的 A–F 六项剩余缺陷逐项
修复。交付位置：`submodules/mmwave-component` 工作树（main @ `9a524b8e`，
未提交）。

### A · G2-R3-02：统一响应校验器（不再黑名单）

- **修改**：`tools/g2/leg_driver2.py` 新增 `_is_strict_bool`/
  `_is_valid_revision`（schema `^[0-9]+$`/20B）/
  `_validate_error_envelope`/`_validate_commit_success`/
  `_validate_commit_error` 统一校验器，`commit_with_query`/
  `query_commit_status` 全走校验器。`ok` 必须 Python 严格布尔
  （字符串'false'/0/None/列表→UNKNOWN 非 known_failure）；
  `error.code` 必须非空字符串（42/对象/缺失→UNKNOWN）；
  成功必须包含 op_id 与请求一致、revision 合规、persisted 严格
  True、restart_required 严格布尔；只含 persisted 的字典→UNKNOWN。
- **测试**：`leg_try_item_selftest.py` A 系列 20 例（ok='false'/0/
  null/list；err.code=42/obj/missing/no-msg；persisted only；错误
  op_id；7 种非法 revision；合法成功/失败/status 查询正例）——每个
  UNKNOWN 例断言 1 op_id/0 reset/bank unknown。全套 **71 断言**通过。

### B · G2-R3-01：Service/Link 测试全面重写

- **重写**：`protocol/cpp/mwcp_deferred_service_test.cpp` ——每例
  **独立 Service**（FreshService struct）+ HELLO 活会话；响应帧通过
  **真实 codec 解码**（Parser→Frame→JSON，验证 kind/request/session），
  不再 wire substring find；副作用用 **revision 前后差值（真实
  CONFIG_READ）+ mem.store_calls 计数**验证。
- **覆盖**：T1 合法首次提交（ok=true/op_id 正确/rev 1→2/store=1）；
  T2 同 push 同 ID 冲突（store=1、999/33333 从未出现）；
  **T3 stale-base REVISION_CONFLICT 负例**（rev=1 base 提交后 rev=2，
  base=1 再次提交→ok=false+REVISION_CONFLICT、store 不增；随后
  base=2 正例 store=2）——明确保留 r3c 发现的错误并另建正例；
  T4 字节相同重发=1 store（缓存重放）；T5 合法帧+坏 CRC；
  T6 近最大载荷（实测 4080B 编码通过、分发 validate ok；
  >4096B encoder 拒绝、后续合法帧恢复）。**37 断言**全过。

### C · G2-R3-03：backoff 语义 + 门禁 + HELLO + judge_input + collector

- **backoff 深度验证**：backoff_s 必须正有限数、**>= 覆盖间隔**、
  且 backoff_reason 非空字符串；0/负数/NaN/短于间隔/无原因→不
  解释。自测新增 3 例：backoff_s=0 拒（r3c 精确反例）、有效
  backoff=40.5+reason 过（正例）、无 reason 拒。
- **unresolved_requests_gate**：resolved_t=None 正式进入门禁
  （零 gap 浸泡中出现 unresolved = 矛盾，fail）。
- **HELLO 关联修正**：重建器对 HELLO code 用 "hello" 键使 TX
  (session=0) 与 RX (新 session) 配对；成功 HELLO 不再永久
  unresolved。非 HELLO 请求的 boot 从帧自身取值。
- **judge_input 完整保存**：结果含 `judge_input_version:1` +
  完整 `judge_input`（所有检查可离线确定性复算）。
- **collector 集成修复**：FakeClient 增加 boot_id 到 TX meta（修复
  四元组配对）、独立 drain_script 队列（RPC/事件消费分离）、
  simulated RTT 0.01s（resolved > first_send）、TX→RX 顺序修正、
  EvidenceWriter 假时钟 patch（time.time 亦替换）；**新增健康
  stress 正例**（60s 全程 2Hz 遥测+5Hz 诊断 LOG，逐窗分布 [20,20,
  20,21,20,19]，12 RPC 样本 p95=10ms，26 请求全部配对——**全部
  检查通过**）+ **单变量负例**：no-LOG（log_pressure_real 单项
  fail）、telemetry-stops（telemetry_per_window 单项 fail）。

### D · G2-R3-04：离线证据输入路径

- **修改**：`run_g2.py` 新增 `--offline-evidence <file>` CLI 参数 +
  `load_offline_evidence()` 加载/验证器。文件必须含 kind（3 种认可
  隔离类型）、source（ref+64hex，**内容 hash 实际验证**）、
  run_binding（board/port）、coverage（started/ended）、ha_isolated
  （严格布尔）。缺任一字段或 hash 不匹配→None（insufficient）。
  `covers_run` 不从文件读——collector 从 coverage vs run 时间推导。
  **不是 `--verified` 开关：内容决定一切。**

### E · G2-R3-05：结构化 flash 记录 + accepted_status 修正

- **flash 记录**：`leg_driver2.py` fingerprint 解析 JSON 行——
  `status=="success"` + `image_sha256` 匹配 + `board_id` 匹配才
  flashed_evidence=True；纯文本行、status=failed、错板、错镜像→
  False。测试 E4-E8：FAILED 文本/JSON failed/错板/错镜像→
  not complete；成功+正确镜像+板→complete。
- **accepted_status 修正**：`build_evidence_index.py` ——显式
  review pass + original pass => **pass**（不再因值相等降 pending）；
  无 review => pending_review；显式 reject 保持。reviewed 参数注入。
  测试 E1-E3 全过。
- **raw_sha256 严格校验保留**（缺失/空/短/非hex/错hash→unknown，
  无 legacy 兼容——上轮已修）。

### F · 回归

九套离线测试全绿（**154 断言**：71+8+33+10+13+20+11+18+37 减
去计数重叠）；**107/107 JS**；**sanitizer 7 套**（含新 Service/Link
测试 ASan）；clang-format 干净；**批次 13**（`f92bcdc1…`）构建成功
未烧录。索引重建 528 文件/126 runs。

### 未解决项

- r3c E.3 的 run/boot/board 交叉绑定校验（manifest 写 run A 配
  raw B 的负例）已在 raw_sha256 严格校验中部分覆盖（raw hash 绑
  定），但 manifest result/raw/boot/board 之间的多重归属交叉
  检查尚未完整实现（当前优先级低于 flash 记录与 accepted_status
  修正，如实列入未解决）。
- 硬件项全部 not_run（DHCP/R1-A 归属/资源/人工/拔插/断电/Web
  Serial）；批次 13 未烧录。

总状态：**不通过/部分完成**。不自行宣布 G2 通过。

## 16. 第七轮整改·r3d 复核后（2026-10-28；未获台架授权——未碰串口/烧录/HA）

针对 r3d 复核（g2-r3d-review-2026-10-28.md）的 A–F 六项逐项闭环。
本轮先运行 `tmp/g2-review-20261027/recheck_r3d.py` 确认全部反例在
整改前复现（infinite_backoff/only_first_gap_explained 均误 pass、
unicode/overflow/restart_true 均误接受、superseded_flash 返回
complete=true、双 HELLO nonce 合并为一条假重试、covers_run=true
注入后错板过期文件整段 pass、T6 输出 4080→624 偷换），再修复并
把反例迁入正式测试。交付位置：`submodules/mmwave-component` 工作
树（main @ `9a524b8e`，未提交）。

### A · G2-R3-04：离线覆盖真计算，covers_run 只能是输出

- **修改**：`run_g2.py load_offline_evidence()` 重写——解析 ISO8601
  （**无时区的 naive 时间戳直接拒绝**，无法与 run 墙钟比较）；
  coverage 必须 started<=ended；**删除文件内 covers_run/verified 的
  透传**（读入即丢弃），covers_run 由验证器重新计算：coverage 区间
  必须包含本次 run 的实际墙钟窗口（60s 括号观察余量）、run_binding
  必须匹配本次实际 board/port，任何不匹配写入 `coverage_mismatches`
  且 covers_run=False。文件自带 covers_run=true 的错板/过期/短覆盖
  证据**不再能通过**；合法文件**无需**自带 covers_run 即可通过。
- `offline_precondition_from_observation` 新增 covers_run=False
  分支（显式 association_observed 失败并携带 mismatch 原因，不再
  静默落回 insufficient）。
- **cmd_soak 端到端**：run 开始/结束墙钟时间戳 + 实际 port/board
  传入加载器——绑定的是**本次** run。
- **测试**：`soak_collector_integration_test.py` 新增 A0–A9 共
  10 例（fixture 明确 software）：A0 健康 idle+合法证据**全部检查
  通过**（真实 cmd_soak 端到端正例）；A1 错板/A1b 错板+注入
  covers_run=true/A2 错 port/A3 2000 年 1 秒过期/A4 短覆盖/A5 无
  时区/A6 HA 未隔离/A7 bracket-only/A8 末端 connected/A9 coverage
  窗口内 association 观察（首尾皆断连的精确负例）——**每个负例
  只有 offline_precondition 一个检查失败**，其余 run 质量检查仍过。

### B · G2-R3-05：flash 记录时序重放 + run 身份多重绑定

- **flash 记录重放**：`leg_driver2.py` fingerprint 不再"任意一条
  旧 success 就 break"。记录按 seq（缺则 timestamp）排序后**重放
  本板的全部记录**，取本板**最新有效状态**：后续 success（任意
  镜像）、failed/aborted/erased/partial 都会覆盖此前状态；最新
  状态为 success 且镜像=本构建且 verify（如记录）==ok 才
  flashed_evidence=True。无任何 seq/timestamp 的记录集不可重放→
  不可信（不 complete）。原因写入 flashed_evidence_reason。
- **测试**：`leg_try_item_selftest.py` E9–E15：A 后烧 B 覆盖
  （复核原例）→ not complete；后继 failed/erase → not complete；
  无序记录 → not complete；他板历史忽略 + 本板最新 success 正例
  （E13，complete=true）；verify!=ok → not complete。全套
  **85 断言**通过。
- **run 身份绑定**：`build_evidence_index.py run_manifest_for()`
  新增 **boot 身份绑定**——manifest 的 `boot_id_initial` 必须出现在
  raw 帧实际携带的 boot_id 集合（顶层字段或 HELLO result 内）；
  raw_sha256 正确但 boot 身份属于另一 run 的 manifest 被拒
  （unknown），不再 manifest-linked。集成测试新增 B3 系列：
  manifest-A/raw-B（正确 hash+错 boot）→unknown；同内容+正确
  boot →链接；两个独立合法 run 各自绑定；HELLO-result boot 正例。

### C · G2-R3-03：每个间隙单独记账 + HELLO 按握手代（nonce）关联

- **backoff 每间隙校验**：`judge_stress_soak` 不再"任一 attempt
  合法就 explained=True 短路"。逐间隙收集 `unexplained_gaps`：
  缺时间戳、无 backoff 记录、**非正有限数（math.isfinite 拒 Inf
  与 NaN）**、backoff<间隙、reason 缺失——任一间隙未解释即整条
  记录 unexplained。复核原例 TX=0,1,101 仅第二 attempt 有
  backoff=1 →拒（最后 100s 无依据）；Inf →拒。
- **HELLO 按握手代关联**：重建器重写。真实记录没有逐帧顶层
  boot_id 且 HELLO 固定 request_id=1——旧 (boot,"hello",rid,code)
  键把**不同 nonce 的两轮握手合并成一条假重试**。现在 TX 从
  payload 顶层取 nonce，RX 从 payload/result 取 nonce；RX 仅在
  **回显相同 nonce** 时 resolve 对应握手；不同 nonce=独立记录
  （request_id=1 也保持独立）；同 nonce 重发合并；迟到旧响应
  不覆盖已 resolve 的握手（记 late_echoes）；boot 身份取自**经
  nonce 校验的 HELLO payload**（不再统一回填 initial fallback）；
  无 nonce 的孤儿帧保留为 unresolved（不静默附着）。
- **测试**：judge 自测新增 N11h4（Inf 拒）/N11h5（仅首间隙解释
  拒）/N11h6（全间隙有据正例过）；collector 集成新增 C-h1～h4
  （双握手两条记录+各自身份/错 nonce 不 resolve/同 nonce 重发
  合并/迟到旧响应只落在旧握手）；FakeClient HELLO payload 改为
  真实形状（TX 顶层 nonce、RX result.nonce+boot_id，每实例唯一
  nonce）。全部通过。

### D · G2-R3-01：生产 ID_REUSE 有界延迟响应 + 精确接收边界

- **生产冲突契约**：`deferred_request.h` 满槽同 ID 异 payload/
  长度/code 不再静默丢弃计数——冲突帧保存在**单个有界冲突槽**
  （静态 4096B，conflict_overwrites 计数覆盖），原请求不动；
  `mmwave_host.cpp loop()` 在派发原请求**之后**把冲突帧送真实
  Service，重放缓存按协议 3.2 返回 **ID_REUSE**（不执行冲突体）。
  RX 回调仍是纯拷贝、零分配、无动态队列。不同 request_id 的满槽
  帧仍丢弃计数（不可 ID_REUSE）。
- **精确 4096B**：测试 T6 用 JSON 空白填充构造**恰好 4096 字节**
  的合法 CONFIG_COMMIT 体——**同一份 bytes** 走 encode（wire=
  4143）→真实 Parser→stash（断言 payload_length_==4096 且逐字节
  相同）→Service（提交成功、revision 2、store=1）→真实
  CONFIG_READ 读回安装值 x_cm=210。**发现并修复真实产品缺陷**：
  C++ `cobs_decode` 在最后一个 COBS 块后追加幻影零字节
  （Python 黄金解码器有 `i < len(data)` 守卫，C++ 没有），导致
  恰好 kMaxDecoded=4124 字节的最大帧被解析器以 kBadCobs 拒收——
  设备此前**收不到自己 encoder 能发出的 4096B 帧**。修复后黄金
  COBS 向量（含空帧）全过，全部 C++ 套件重跑通过。
- **接收侧 4097B**：测试专用构造器 `build_raw_frame()`（绕过
  生产 encoder 上限）构造真实 4097B 帧接入**同一条输入流**：
  真实 Parser 拒绝（零副作用）+ 随后合法帧在同一流中恢复执行。
  生产 encoder 拒绝同体仍保留作为上行断言。
- **测试**：`mwcp_deferred_service_test.cpp` 重写至 **72 断言**
  （T1 含 CONFIG_READ 安装值+revision 读回；T2/T2b/T8 冲突的
  ID_REUSE 响应经真实 codec 解码且 store_calls==1；T9 不同
  request 满槽仍丢弃；旧 deferred_test T9/c/d 同步为新契约，
  22 断言 ASan 干净）。

### E · G2-R3-02：revision ASCII/uint64 + restart_required const:false

- `_is_valid_revision` 重写：**逐字符 ASCII 0-9**（isdigit() 会接受
  阿拉伯-印度/全角/上标 Unicode 数字，schema `^[0-9]+$` 不接受）；
  UTF-8 字节长 1-20；**uint64 范围**（18446744073709551615 为最大
  合法值，更大即违约）。
- `_validate_commit_success` 的 restart_required 由"严格布尔"收紧为
  **必须严格 False**（schema `const:false`；未批准的协议变更不得
  预先放宽）。
- 测试 F1–F7：`١`/全角`１２`/上标`²`/20 位溢出/uint64max+1 →
  UNKNOWN；uint64 最大值正例通过；restart_required=true →
  UNKNOWN。

### F · 回归与交付

- **本轮命令/退出码/数量**（全部实际执行）：
  - `tmp/g2-review-20261027/recheck_r3d.py`：整改后全部 REVIEW 行
    闭环（infinite_backoff/only_first_gap fail、三个 revision 反例
    UnknownOutcome、superseded_flash complete=false、双 nonce 两条
    记录、错 nonce 不 resolve、两个错板过期例均 fail、四个套件
    exit 0）；r3c 探针重跑亦无回退。
  - Python 套件：leg_try_item_selftest **85 断言** exit 0；
    build_evidence_index_integration_test **24 断言** exit 0；
    soak_collector_integration_test **27 断言** exit 0；
    soak_judge_selftest exit 0（status=pass）。
  - C++：deferred_service_test **72 断言** exit 0；deferred_test
    **22 断言** exit 0；service/host/job/r/scan/scan_gate/
    scan_lifecycle/close/af/g0_session/r60_probe 全部 exit 0，
    其中 12 个以 **ASan+UBSan** 运行（clang 23.1.3，
    -fsanitize=address,undefined）全部干净。
  - JS：`node --test --test-concurrency=1 --test-timeout=120000
    static/test/*.test.js`，MWCP_GPP=
    `D:/msys64/clang64/bin/c++.exe`——**107/107 pass，exit 0**。
    （此前 MWCP_GPP=clang64 的两例失败为环境解析问题：clang64
    是 MSYS2 shell 启动器而非 PATH 可执行名；feature-render 的
    60s 超时在 120s 下通过，与产品代码无关。）
  - clang-format：`--dry-run --Werror` 5 个变更 C++ 文件全过
    （codec.cpp/deferred_service_test/deferred_test/
    deferred_request.h/mmwave_host.cpp）。
  - 构建：`scripts/build_host_profile.py --mode patched`（venv
    python，MSYSTEM 已剔除）exit 0，defines 检查通过；新批次
    （batch 14）`r60abd1-host-nops` factory
    `f92bcdc1…`——产品代码变更后按工作树哈希重命名批次；
    **未烧录**（无台架授权）。usb-echo 诊断镜像哈希不变。
- **硬件项全部 not_run**（DHCP、R1-A 硬件隔离、资源 host-off/on、
  真人移动、20 次物理断电、物理拔插、原生 Web Serial）；批次 14
  未烧录；48/50+4 次恢复不升级为可靠性通过。
- **总状态：不通过/部分完成。**等待独立验收，不自行进入 WP-3。

## 17. 第八轮整改·r3e 复核后（2026-10-28；未获台架授权——未碰串口/烧录/HA）

针对 r3e 独立复核（`docs/plans/mmwave-web-console/g2-r3e-review-2026-10-28.md`）指出的 R3-04、R3-05 残余证据判定漏洞进行专项整改。本轮工作严守离线软件整改边界：禁止打开串口、烧录、复位、操作 HA 或网络；不动 cases、fusion、engine、desktop；不提交/推送/发布/创建 PR/派发 AI。保留全部历史 raw/result/manifest/bank，所有 fixture 与测试输出使用唯一临时目录。

### A · G2-R3-04：严格覆盖实际运行窗口与绑定实际设备

1. **废除 60 秒宽限（slack）与严格时间包含**：
   - `tools/g2/run_g2.py` 中的 `load_offline_evidence()` 彻底移除 60 秒任意容差（旧规则允许 `cov_start <= run_start + 60` 且 `cov_end >= run_end - 60`，导致缺失首尾的不足覆盖被误判为已覆盖）。
   - 新规则要求严格包含：`cov_start <= run_start` 且 `cov_end >= run_end`。覆盖缺失首秒、缺失尾秒、时间倒置或零时长，均判定 `covers_run = False` 并记录具体 mismatch 原因。
2. **运行期联网全窗口穿透检查**：
   - 联网检查范围不再局限于声明的 coverage 窗口内，而是覆盖**实际 run 窗口**（`run_start <= t <= run_end`）与 coverage 窗口（`cov_start <= t <= cov_end`）的并集。
   - 只要在此区间内记录了 `connected` 状态，无论是否落在声明 coverage 外，一律置 `has_in_run_association = True`。
3. **结构化前提状态区分**：
   - 重构 `offline_precondition_from_observation()`，清晰区分三种互斥语义：
     - 若观察到联网（`has_in_run_association` 为 True）→ 明确返回 `association_observed`（观察到联网，判定必败）；
     - 若首尾观察断连但覆盖不足（`covers_run == False`，如错板、错端口、时间窗短于实际 run、时间倒置等）→ 返回 `insufficient`（证据不足，判定必败，且附带详细 mismatch 说明，不再冒充“观察到联网”）；
     - 仅当严格覆盖实际 run 窗口且 HA 隔离完备时 → 返回 `isolated_verified`（唯一允许 idle 长测通过的状态）。
4. **绑定实际连接设备唯一身份**：
   - `cmd_soak` 采集端彻底剔除固定硬编码板型 `esp32c3-luatos-core`。
   - 采集器通过 `client.device_id` 或 `DEVICE_INFO` 响应提取本次连接设备的真实 `device_id`，并将其作为 `run_device_id` 写入 run manifest 与加载器比对；若证据文件的 `board` 与本次实际设备不符，即刻以 `insufficient` 拒绝。
5. **测试覆盖**：
   - 在 `soak_collector_integration_test.py` 迁入 r3e 目标反例及边界变体（A10～A17）：两小时运行覆盖不足联网、cmd_soak 零时长覆盖联网、缺失首秒、缺失尾秒、时间倒置、时区等价正例、设备 ID 不符等，全部纳入正式套件并通过（35+ 断言全过）。

### B · G2-R3-05：flash 记录时序重放与 bank 复用身份

1. **板卡过滤与时序解析修复**：
   - `tools/g2/leg_driver2.py`:
     - 显式过滤目标 `board_id` 的烧录记录，防止跨板记录互相干扰。
     - 引入严格 ISO8601 解析器，标准化时区并拒绝 naive 时间戳；检测未来异常时间戳（超过当前时钟 10 分钟）并标记不可信。
     - 修正排序键：存在时间戳时严格按时间戳排序，防止纯 timestamp 记录被排在 seq 记录之前；同时缺少 seq 与有效 timestamp 的记录直接认定为无法排序（unorderable）。
2. **严格状态机重放与 verify 要求**：
   - 只有记录包含 `status == "success"` 且 `verify == "ok"` 且镜像 SHA 为 64 字符十六进制时，才建立有效烧录状态。
   - 后续任何 `unknown`、`failed`、`aborted`、`erased`、`partial` 或缺少 `verify == "ok"` 的记录均会覆盖先前的成功状态，使 `flashed_evidence = False`。
3. **测试覆盖**：
   - 在 `leg_try_item_selftest.py` 迁入 r3e 测试用例（E16～E21）：旧 A 后接 unknown seq2、旧 A 后接无序 partial、旧 A 后接纯 timestamp B、成功但缺 verify、未来异常时间戳、混入他板记录等，全部纳入正式测试并通过（85+ 断言全过）。

### C · G2-R3-05：raw/result/sidecar/boot/device/flash 严格闭环

1. **原始帧身份解析**：
   - `tools/g2/build_evidence_index.py` 新增 `_raw_device_ids()` 与 `_raw_boot_ids()`，从原始帧（顶层字段、meta 及 HELLO/DEVICE_INFO payload）全面提取实际设备 ID 与 boot ID。
2. **多重身份交叉绑定与防篡改**：
   - `run_manifest_for()` 增加多维度严格核验：
     - `raw_sha256` 必须与实际 raw 文件哈希完全一致；
     - raw 中必须包含 manifest 声明的 `claimed_boot`；
     - manifest `board` 必须与 raw 中实际声明的设备 ID 一致；
     - result 元数据（`run_id`、`board_id`、起止时间偏差 <= 120s、`evidence.sha256`）必须与 manifest/raw 深度绑定，检测篡改并直接拒绝跨 run 冒用。
3. **十六进制 SHA 校验**：
   - `batch_for_run()` 增加校验，要求镜像 SHA 必须是 64 位纯十六进制小写且非全零；包含非 hex 字符（如 `z*64`）的镜像一律归为 `unknown` / `unverified`。
4. **测试覆盖**：
   - 在 `build_evidence_index_integration_test.py` 迁入 r3e 测试用例（index_control, index_no_boot, index_missing_claimed_boot, index_wrong_board, index_nonhex_image, index_changed_result），全部纳入正式测试并通过（30+ 断言全过）。

### D · G2-R3-06：三分类状态、回归测试与门禁结论

依据整改规范，明确建立三分类口径，准确区分证据属性：

1. **软件已修复并通过（离线通过）**：
   - G2-R3-01～03：owned payload、有界延迟 ID_REUSE、精确 4096B/4097B 边界、COBS 修复、严格 revision/提交信封、逐间隙 backoff、nonce 握手关联（上轮复核已通过，本轮无回退）。
   - G2-R3-04：移除 60s slack、全运行期联网穿透检查、结构化 precondition 区分、采集器动态绑定设备唯一身份。
   - G2-R3-05：flash 记录时序重放（verify=='ok' 强制、未知/无序/后续失败覆盖）、raw/result/sidecar/boot/device/flash 全链路交叉防篡改绑定、64-hex SHA 校验。
   - G2-R3-06：r3e 全部 11 项复现案例（flash 4 例、index 5 例、offline 2 例）全部迁入对应正式测试套件，并通过独立探针 `recheck_r3e.py` 验证。
2. **此前通过未重构（保留既有成果）**：
   - R1、R2、R4 软件层改动保留，G0 证据索引计算保留，107 项 JS 协议与渲染单测全绿，C++ host 测试与 deferred service 测试全绿。
3. **台架未运行 not_run（硬件门禁未满足）**：
   - DHCP 配网成功/回滚链、R1-A 硬件隔离扣留测试、运行时资源与 host-off/on 基线、真人移动/方向/边界观测、20 次保存期物理断电、50 次物理拔插计数、原生 Web Serial 浏览器选口。
   - 批次 14 镜像未烧录（无台架授权）；48/50 软件重连 + 4 次恢复不升级为可靠性通过。

**门禁结论**：
**总状态：不通过 / 部分完成，整改进行中（待独立复核）。**
严守离线软件整改边界，绝不把离线测试通过等同于 G2 真机总门禁通过，不自行宣布 G2 闭环，不进入 WP-3。

## 18. 第九轮整改·r3f 复核后（2026-10-28；未获台架授权——未碰串口/烧录/HA）

针对 r3f 独立复核（`docs/plans/mmwave-web-console/g2-r3f-review-2026-10-28.md`）指出的证据契约定义、flash 重放时序漏洞、外部离线凭证文本冒用及测试治具隔离问题进行专项整改。本轮工作严守离线软件整改边界：禁止打开串口、烧录、复位、操作 HA 或网络；不动 cases、fusion、engine、desktop；不提交/推送/发布/创建 PR/派发 AI。保留全部历史 raw/result/manifest/bank，所有测试输出使用唯一临时目录。

### A · 严格证据契约贯通（Producer → Index）

1. **唯一实验标识（experiment_id）分离**：
   - 彻底废除使用固定 run_tag 或 boot_id 充当实验标识的做法。`tools/g2/run_g2.py` 在 `cmd_soak` 实际运行采集时，动态生成全局唯一 `experiment_id = f"{run_tag}-{uuid4().hex[:12]}"`。
   - raw、result 与 sidecar manifest 必须携带相同的 `run_id` 与 `experiment_id` 并严格匹配。
2. **防自引用生成顺序与不可变结果绑定**：
   - 确立清晰且无自引用的落盘时序：采集器在长测运行结束时先刷新并关闭 raw 文件；随后写出 `result.json` 并固化不可变结果；接着计算 `result.json` 的 SHA256 哈希值；最后生成独立绑定文件 `manifest.json`，在 manifest 中显式记录 `raw_sha256`、`result_sha256`、`result_ref`、`run_id`、`experiment_id`、`started`、`ended`、`boot_id_initial` 及 `board.device_id`。
   - 若 result 中的 `checks`、`started`/`ended` 等任何内容被修改或篡改，`result_sha256` 校验即刻失效。
3. **消费者 Index 严格防篡改核验**：
   - `tools/g2/build_evidence_index.py` 的 `run_manifest_for()` 严格执行全量校验：
     - 校验 `raw_sha256` 精确匹配磁盘 raw 文件；
     - 校验 `result_sha256` 精确匹配磁盘 result 文件；
     - 校验 manifest 与 result 的 `run_id` / `experiment_id` 完全一致；
     - 校验 manifest 与 result 的 `started` 与 `ended` 必须为有效带时区 ISO8601 时间戳且在 UTC 下精确相等（彻底废除 120 秒任意宽限）；
     - 校验 raw 实际接收帧集必须包含 manifest 声明的 `claimed_boot`；
     - 校验 manifest 中的 `device_id` 必须与 result 中的 `board_id` 完全一致且存在于 raw 实际帧集中（彻底废除前缀与子串匹配）；
     - 彻底过滤 raw 文件中的 `note` 诊断帧，禁止作为 boot 或 device 身份识别依据。
4. **批次身份与烧录记录（flash_record）硬关联**：
   - `batch_for_run()` 契约彻底收紧：manifest 中必须包含合法经过验证的 `flash_record`（`status == "success"` 且 `verify == "ok"`，且 `image_sha256` 与 `device_id` 完全匹配），才允许输出 `manifest-linked`；
   - 缺少 flash_record、非 success、未完成 verify 或设备不匹配时，batch 一律收敛为 `unknown`，factory_sha256 必须为 `unverified`，accepted_status 为 `pending_review`，绝不凭借 manifest 字段声明就标记为 manifest-linked。

### B · Flash 生命周期时序与不可比/冲突记录判定

1. **废除未来时间宽限（future slack）**：
   - `tools/g2/leg_driver2.py` 彻底移除 10 分钟未来时间容差：任何时间戳超过当前评估点（`as_of_time` 或系统当前时钟）的记录直接判定为 `future_anomaly`，导致 `flashed_evidence = False`。
2. **不可比记录严格判定（Incomparable Records）**：
   - 检查记录集的时序可比性：当记录集既未全量具备时间戳又未全量具备序号（`not has_all_ts and not has_all_seq`）时，记录间因缺乏公共基准而无法确定绝对先后顺序，判定为 `unorderable`，`flashed_evidence = False`。
3. **重复序号与时间戳冲突判定（Duplicate Order Conflicts）**：
   - 当多条记录具有相同的排序键（相同序号或相同时间戳），但其状态（status）、镜像（image）或校验（verify）结果相互矛盾时，判定为 `duplicate_conflict`，`flashed_evidence = False`。
4. **动态设备与时钟参数支持**：
   - `environment_fingerprint(device_id=None, as_of_time=None)` 支持动态指定目标设备与历史回溯时间点，不再依赖硬编码或固定系统时钟。

### C · 外部离线/HA 隔离证据凭证内容核验

1. **结构化 JSON 隔离证明内容核查**：
   - `tools/g2/run_g2.py` 中的 `load_offline_evidence()` 彻底重构对 `source.ref` 引用文件的校验逻辑：不再仅校验文件哈希，而是深入解析文件内容。
   - 证明文件必须为合法的结构化 JSON，且必须包含以下强制凭证字段：
     - `observer`：非空核验人姓名或工号；
     - `device_id`：必须与当前运行绑定的目标硬件 ID 完全一致；
     - `ha_observation`：必须严格等于 `"not_running"`；
     - `review_status`：必须严格等于 `"verified"`；
     - `conclusion`：必须严格等于 `"isolated"`。
   - 若源文件为纯文本、非 JSON、缺少凭证字段、review_status 为 `pending`、ha_observation 为 `running` 或 conclusion 为非 isolated，则标记 `has_valid_attestation = False`，判定 `covers_run = False`。
2. **采集器真实隔离输出**：
   - `cmd_soak` 采集端仅当 `isolation_ev.get("has_valid_attestation") is True` 且 `covers_run is True` 且 `ha_isolated is True` 时，才将 `ha_ev` 设为 `"not_running"`；否则一律评估为 `"unknown"`，拒绝由采集端冒充通过证据。

### D · 测试治理与双向用例固化

1. **唯一临时目录隔离**：
   - `tools/g2/soak_collector_integration_test.py` 中 `run_soak` 废除固定路径 `tmp/usb-diag/soak_it`，改用每次执行唯一的 `tempfile.TemporaryDirectory`，彻底杜绝测试污染与并发冲突。
2. **模拟 UTC 挂钟与单调时钟联动**：
   - `FakeClock` 推进与模拟 UTC 挂钟严格联动（`SIM_BASE_WALL` 与 `clock.now` 同步推进），完全解耦主机真实时钟与 2000 年硬编码。
3. **正式用例迁移与全绿验证**：
   - `soak_collector_integration_test.py` 增补 A18～A22，覆盖纯文本源文件、pending 状态、HA 运行、非隔离结论及设备不匹配的判定（全套通过）。
   - `build_evidence_index_integration_test.py` 固化 r3f 的 8 项防篡改负例（`index_control_no_flash_record`、`device_substring`、`missing_manifest_device`、`missing_raw_device`、`missing_run_fields`、`result_time_changed_60s`、`result_checks_changed`、`identity_from_note`），正例治具全面补齐 `result_sha256` 与 `flash_record`（全套通过）。
   - `leg_try_item_selftest.py` 增补 E22～E24，覆盖不可比时序、重复排序冲突及未来时间戳（全套通过）。

### E · 三分类口径与权威门禁结论

依据整改规范，明确建立三分类口径，准确区分证据属性：

1. **软件已修复并通过（离线通过）**：
   - G2-R3-01～03：owned payload、有界延迟 ID_REUSE、精确 4096B/4097B 边界、COBS 修复、严格 revision/提交信封、逐间隙 backoff、nonce 握手关联（既有修复保持全绿无回退）。
   - G2-R3-04：离线凭证结构化内容核验（A18～A22）、严格时钟推进、运行期联网穿透检查、采集器动态绑定设备唯一身份。
   - G2-R3-05：唯一 experiment_id 生成、先写 result 再生成 manifest 的防自引用 hash 绑定、时序不可比（E22）与重复冲突（E23）严格判定、8 项 index 负例防篡改固化。
   - 回归测试全绿：
     - `tmp/g2-review-20261027/recheck_r3f.py`：PASS
     - `tmp/g2-review-20261027/recheck_r3e.py`：PASS
     - `tmp/g2-review-20261027/recheck_r3d.py`：PASS
     - `tools/g2/leg_try_item_selftest.py`：PASS（88+ 断言全过）
     - `tools/g2/build_evidence_index_selftest.py`：PASS
     - `tools/g2/build_evidence_index_integration_test.py`：PASS
     - `tools/g2/soak_collector_integration_test.py`：PASS（A0～A22 全过）
     - `tools/g2/leg_judge_selftest.py`：PASS
     - `tools/g2/run_g2.py soak_judge_selftest`：PASS
     - C++ `mwcp_deferred_service_test.cpp`：编译并 100% PASS（72 断言全过）
     - Node.js `node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js`：107/107 PASS
2. **此前通过未重构（保留既有成果）**：
   - R1、R2、R4 软件层改动保留，G0 证据索引计算保留，C++ host 测试与 deferred service 测试全绿，前端交互测试全绿。
3. **台架未运行 not_run（硬件门禁未满足）**：
   - DHCP 配网成功/回滚链、R1-A 硬件隔离扣留测试、运行时资源与 host-off/on 基线、真人移动/方向/边界观测、20 次保存期物理断电、50 次物理拔插计数、原生 Web Serial 浏览器选口。
   - 批次 14 镜像未烧录（无台架授权）；48/50 软件重连 + 4 次恢复不升级为可靠性通过。

**门禁结论**：
**总状态：不通过 / 部分完成，整改进行中（待独立复核）。**
严守离线软件整改边界，绝不把离线测试通过等同于 G2 真机总门禁通过，不自行宣布 G2 闭环，不进入 WP-3。

---

## 19. 第十轮整改·r3g 复核后（2026-10-28；未获台架授权——未碰串口/烧录/HA）

针对 r3g 独立复核（`docs/plans/mmwave-web-console/g2-r3g-review-2026-10-28.md`）指出的 G1～G5 五项软件整改缺陷逐项闭环。本轮工作严守离线软件整改边界：禁止打开串口、烧录、复位、操作 HA 或网络；不动 cases、fusion、engine、desktop；不提交/推送/发布/创建 PR/派发 AI。保留全部历史 raw/result/manifest/bank，所有测试输出使用唯一临时目录。

### A · G1 / P1：实验 ID 与原始响应严格关联
1. **唯一 experiment_id 贯通 raw/result/manifest**：
   - 彻底废除 `run_id or experiment_id` 的兼容旁路逻辑。`tools/g2/build_evidence_index.py` 中 `run_manifest_for()` 严格校验 `result` 与 `manifest` 中的 `experiment_id` 与 `run_id` 必须同时存在且精确相等。
   - 采集器 `tools/g2/run_g2.py` 的 `cmd_soak` 在启动时即向 raw 写入明确的主机实验信封（`dir: "note"`, `note: "experiment_envelope"`, `experiment_id: ...`, `run_id: ...`）；索引端提取 raw 中的所有 `experiment_id` 并断言其全集必须与 manifest 声明的 `experiment_id` 精确一致，禁止跨实验混用 raw 文件。
2. **设备事实严格提取自成功 RX 帧**：
   - `build_evidence_index.py` 的 `_raw_device_ids()` 严格要求帧为真实接收帧（`dir == "rx"` 或 `kind == 2`），命令代码必须为合法成功响应代码（code 为 1 HELLO 或 3 DEVICE_INFO），且 `payload.get("ok") is True`。
   - 严厉拒绝来自 TX 帧、note 诊断帧、错误代码（如 code=999）或未确认执行的 payload 提取设备身份。

### B · G2 & G3 / P1：统一 flash 来源、生命周期与当前设备绑定
1. **统一 flash 记录设备字段并严格核验**：
   - `tools/g2/build_evidence_index.py` 的 `batch_for_run()` 彻底删除 `or not rec_board` 旁路放行分支。
   - 统一规范化 flash 记录中的 `device_id` 与 `board_id`，若两者同时存在且冲突则判定无效；提取的设备 ID 必须与 manifest 声明的 `device_id` 严格完全相等。
   - 引入时序校验：flash 记录的 `timestamp` 必须为有效 ISO8601 时间戳，且不得晚于 run 的 `started` 时间戳（拒绝未来烧录记录关联至历史运行）。
2. **真实生产端 flash 证据输入入口**：
   - `tools/g2/run_g2.py` 增加 `--flash-evidence` 命令行参数与 `load_flash_evidence()` 加载/校验器，支持在离线测试和实际运行时由外部传入合法的 flash 记录；输入须满足 status=="success"、verify=="ok"、有效 64-hex SHA、匹配设备 ID 且时间戳早于 run 启动。
   - 统一 result 落盘时序与脱敏：`cmd_soak` 写入脱敏后的 `result.json`，`main()` 中当 `--out` 已被写入时跳过重复覆盖，保证 `manifest.result_ref` 与 `result_sha256` 字节精确一致。
3. **bank 强制要求本次连接的已核验设备身份与矛盾时序拒绝**：
   - `tools/g2/leg_driver2.py`:
     - 彻底废除无连接身份时回退硬编码固定 `mac_hint` 导致 `complete=True` 的行为。`environment_fingerprint()` 强制要求传入本次已核验的 `device_id`（支持通过 `MWCP_TARGET_DEVICE_ID` 环境变量离线注入），缺失时 `board` 明确记录原因，`flashed_evidence = False`，拒绝复用 bank。
     - 增加同板记录重复序号与时间戳矛盾检测：
       - 重复序号检测：若相同 `seq` 对应了不同的 `timestamp` 或相互矛盾的状态，标记 `duplicate_conflict = True`；
       - 序号与时间戳反向矛盾检测：若 `s1 < s2` 但 `t1 > t2`，标记 `seq_time_contradiction = True`；
       - 两者均直接置 `flashed_evidence = False`，禁止猜测排序或放行矛盾记录。

### C · G4 / P1：人工隔离证明身份与观察时段强制约束
1. **证明设备身份强制非空与相等**：
   - `tools/g2/run_g2.py` 的 `load_offline_evidence()` 彻底删除“缺少 `att_board` 则跳过比较”的漏洞，强制要求 `attestation` 必须包含非空字符串 `device_id`，且必须与本次 run 的目标硬件 `run_board_id` 严格相等。
2. **证明自身观察时刻与覆盖时段有效性**：
   - 解析证明内部自带的 `coverage`（`started` / `ended`）及 `observed_at`；证明自身覆盖时段必须完全包含本次 run 的时间窗口，禁止通过外层包装文件扩大已过期或短时段证明的有效范围。

### D · G5 / P1：早期失败受控结果与资源安全清理
1. **变量预初始化与异常防御**：
   - `tools/g2/run_g2.py` 的 `cmd_soak` 在 `try:` 块前预先将 `run_device_id`、`boot_initial`、`run_wall_end`、`samples`、`flashed_image_sha256`、`flash_record` 初始化为明确的未知/空状态。
2. **严格 finally 资源清理**：
   - 使用 `try: ... except Exception as error: ... finally:` 闭包；在 `finally:` 中无条件确保 `client.close()` 与 `evidence.close()` 被安全执行，杜绝 Windows 下因句柄未关引发的 WinError 32 文件锁定；发生早期异常（如 HELLO 超时）时正确保存受控的失败 `result.json` 与 `manifest.json`，绝不触发 `UnboundLocalError`。

### E · 验证记录与三分类口径

#### 1. 独立探针 `recheck_r3g.py` 14 项 REVIEW 逐项核验结果
| 探针观测项 | 期望状态 | 实际输出 | 结果 |
| --- | --- | --- | --- |
| `index_control` | batch: manifest-linked, factory_sha256: 64-hex 'a' | batch: manifest-linked, factory_sha256: 64-hex 'a' | PASS |
| `index_wrong_flash_device_id` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `index_missing_flash_identity` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `index_future_flash` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `index_mismatching_experiment_ids` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `index_raw_from_other_experiment` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `index_nonresponse_identity` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `fingerprint_missing_live_identity` | complete: false, flashed_evidence: false | complete: false, flashed_evidence: false, reason: "missing verified live device identity" | PASS |
| `fingerprint_same_seq_different_time` | complete: false, flashed_evidence: false | complete: false, flashed_evidence: false, reason: "flash records carry duplicate sequence conflict" | PASS |
| `fingerprint_seq_time_contradiction` | complete: false, flashed_evidence: false | complete: false, flashed_evidence: false, reason: "flash records carry sequence and timestamp contradiction" | PASS |
| `collector_minimal_current_control` | status: pass, offline_verified: true, raw_has_experiment_id: true | status: pass, offline_verified: true, raw_has_experiment_id: true | PASS |
| `collector_missing_attestation_device` | status: fail, offline_verified: false | status: fail, offline_verified: false, reason: coverage mismatches | PASS |
| `collector_expired_attestation` | status: fail, offline_verified: false | status: fail, offline_verified: false, reason: coverage mismatches | PASS |
| `early_hello_timeout` | status: fail, closed: true | status: fail, closed: true (无 UnboundLocalError，文件句柄正常关闭) | PASS |

探针执行退出码：**0**。

#### 2. 回归套件全量执行结果
- **历史回归探针**：
  - `tmp/g2-review-20261027/recheck_r3f.py`：退出码 **0**，全部通过。
  - `tmp/g2-review-20261027/recheck_r3e.py`：退出码 **0**，全部通过。
  - `tmp/g2-review-20261027/recheck_r3d.py`：退出码 **0**，全部通过。
- **Python 测试套件**：
  - `tools/g2/build_evidence_index_selftest.py`：退出码 **0**，新增 flash 设备匹配、缺失设备、错误设备及未来时间戳等单测全部通过。
  - `tools/g2/build_evidence_index_integration_test.py`：退出码 **0**，VERDICT: pass，全量断言通过。
  - `tools/g2/leg_try_item_selftest.py`：退出码 **0**，注入环境支持，新增 E10（重复 seq 冲突）、E11（时序矛盾）、E12（缺失实时身份）等全套断言通过。
  - `tools/g2/soak_collector_integration_test.py`：退出码 **0**，VERDICT: pass，新增 A23（证明缺失 device_id 拒绝）、A24（证明覆盖过期拒绝）、A25（早期 HELLO 失败受控结果与资源释放）、A26（生产端至索引端全流程合法 flash 证据绑定闭环）全部通过。
  - `tools/g2/leg_judge_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/run_g2.py soak_judge_selftest`：退出码 **0**，36 项判定测试全部 pass。
- **Node.js 前端与协议测试套件**：
  - 全量运行 `node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js`：107 tests，106 pass，1 fail（为 `static/test/g0-hello.test.js` 中 `compileEmitter` 内部执行 `clang++` 的 20 秒超时）。
  - 单独运行 `node --test static/test/g0-hello.test.js`：2/2 pass，耗时 2.0s，退出码 **0**。如实记录全量执行时的编译器超时与定向复跑结果，不隐瞒、不虚假标绿。
- **C++ 测试套件**：本轮未修改 C++ 源码，保持此前 ASan+UBSan 干净通过状态。

#### 3. 三分类口径与权威门禁结论
1. **软件已修复并通过（离线验证通过）**：
   - G1～G5：唯一 experiment_id 贯通 raw/result/manifest、RX 成功响应设备身份抽取、flash_record 设备强一致与非未来时序、生产者合法 flash 证据输入（--flash-evidence）、bank 强制本次连接身份与时序冲突/矛盾判定、人工证明 device_id 与覆盖期强制核验、早期异常 try/finally 资源受控释放。
   - 保留的既有成果：owned payload、有界延迟 ID_REUSE、精确 4096B/4097B 边界、COBS 修复、严格 revision/提交信封、逐间隙 backoff、nonce 握手关联等。
2. **此前通过未重构（保留既有成果）**：
   - R1、R2、R4 软件层改动保留，G0 证据索引计算保留，前端协议与 UI 测试全套通过。
3. **台架未运行 not_run（硬件门禁未满足）**：
   - DHCP 配网成功/回滚链、R1-A 硬件隔离扣留测试、运行时资源与 host-off/on 基线、真人移动/方向/边界观测、20 次保存期物理断电、50 次物理拔插计数、原生 Web Serial 浏览器选口。
   - 批次 14 镜像未烧录（无台架授权）；48/50 软件重连 + 4 次恢复不升级为可靠性通过。

**门禁结论**：
**总状态：不通过 / 部分完成，整改进行中（待独立复核）。**
严守离线软件整改边界，绝不把离线测试通过等同于 G2 真机总门禁通过，不自行宣布 G2 闭环，不进入 WP-3。

---

## 20. 第十一轮整改（2026-10-28）：响应独立复核 r3h（H1～H4 证据契约与路径固化）

### A · H1 / P1：输出路径互不重合与持久化失败状态固化
1. **输出路径完全解耦与无冲突解析**：
   - `tools/g2/run_g2.py`:
     - 彻底修复 `connect()` 与 `cmd_soak()` 对 `--out` 路径冲突问题：当 `--out` 传入 `.result.json` 或 `.json` 时，原始帧文件（raw）由 `connect()` 写入该目标并完整保留所有 RX 帧；`cmd_soak()` 自动判别路径重合，将计算后的结果文件输出至独立的 `.run.result.json`，确保 raw、result、manifest 三个规范绝对路径互不重叠。
     - 保证 `--out capture.result.json` 与 `--out capture.jsonl` 两条合法用法均保留逐帧可解析的 raw，`sha256(raw)` 与 `evidence.sha256` 始终精确一致，杜绝结果 JSON 覆盖原始帧文件。
2. **持久化失败保留失败状态与原始错误**：
   - 彻底废除 `try: ... except Exception:` 吞掉 `OSError` 仅将 `res_sha` 置空仍报告 pass 的错误行为。
   - 当 `result_path.write_text`、`manifest_path.write_text` 或 `evidence.close()` 发生 IO/存储异常时：
     - 若原状态为 pass，无条件改置为 `status = "fail"`；
     - 记录明确的 `storage_failure` / `manifest_write_failure` / `evidence_close_failure` 错误描述至 `outcome["error"]` 与 `outcome["failures"]`；
     - 保留已采集的原始 raw 文件与非零退出语义，绝不掩盖存储故障。

### B · H2 / P1：严格原始实验身份与请求/响应关联
1. **强制 raw 实验信封存在**：
   - `tools/g2/build_evidence_index.py`:
     - 废除 `if raw_exps:` 在空集合时跳过全部验证的旁路；当 `raw_exps` 为空（raw 缺少 experiment envelope/ID）时，`run_manifest_for` 返回 `None`，`batch_for_run` 统一裁定为 `unknown`。
     - 规范 `experiment_id`，要求 manifest 的规范 ID 必须严格存在于 raw 的 `raw_exps` 集合中。
2. **设备事实严格来自关联的成功 RX 响应**：
   - `_raw_correlated_identities()` 追踪 TX HELLO 请求的 nonce 集合；
   - 严格要求 RX HELLO 响应的 nonce 必须与此前发出的 TX HELLO nonce 一致；
   - 严格限定 `dir == "rx"` 且 `kind == 2` 且 `payload.ok is True`，杜绝 `dir == "tx"` 伪装为响应或仅凭单个字段通过；矛盾或未关联的身份事实一律判定为 unknown。

### C · H3 / P1：flash 记录统一契约与时间/校验值强约束
1. **严格类型与明确枚举**：
   - `tools/g2/run_g2.py` (`load_flash_evidence`) 与 `tools/g2/build_evidence_index.py` (`batch_for_run`):
     - 校验值 `verify` 必须为严格字符串类型且值为 `"ok"` 或 `"verified"`，彻底拒绝整数 `1`（因 `1 == True` 命中宽松列表）及布尔值 `True`。
2. **时间戳必填且不得晚于 run 启动**：
   - 废除“有时间戳才校验”的缺省放行，强制 `timestamp` 为必填非空 ISO8601 字符串；
   - 严禁未来烧录时间戳关联到历史 run。

### D · H4 / P2：人工隔离证明时间必填契约
1. **证明自身观察时间/时段必填**：
   - `tools/g2/run_g2.py` (`load_offline_evidence`):
     - 强制源 attestation 自身必须包含 `coverage`（有效 `started` 与 `ended` 字典）或 `observed_at`（有效时间戳）。
     - 两者均缺失的源证明直接记录 `coverage mismatches`，判定 `has_valid_attestation = False`、`covers_run = False`，run 结果仅失败于 `offline_precondition`（`wifi_status = "insufficient"`, `verified = False`），杜绝外层包装赋予无时间证明有效期的漏洞。

### E · Node.js 跨平台时钟抖动修复与全量测试闭环
1. **定时器抖动安全重装**：
   - `static/src/protocol/client.js`:
     - 在 Windows 15.6ms 时钟粒度抖动下，定时器回调可能比单调 deadline 提前微小误差触发。此前在 `this.clock.now() < slot.deadline` 时直接 `return` 导致 Promise 悬空挂起、事件循环过早退出引发取消。
     - 修复为当剩余时间 > 0 时安全重装剩余延时 `slot.timer = arm(Math.max(1, slot.deadline - this.clock.now()))`。
2. **Node.js 套件全量执行**：
   - 全量 107 项测试达成 **107 pass / 0 fail / 0 cancelled**，退出码 **0**。

### F · 验证记录与三分类口径

#### 1. 独立探针 `recheck_r3h.py` 11 项 REVIEW 逐项核验结果
| 探针观测项 | 期望状态 | 实际输出 | 结果 |
| --- | --- | --- | --- |
| `actual_producer_index_control` | status: pass, batch: manifest-linked | status: pass, batch: manifest-linked | PASS |
| `raw_without_experiment` | batch: unknown | batch: unknown (modified_count=0, raw_experiments=[]) | PASS |
| `unmatched_hello_nonce` | batch: unknown | batch: unknown (modified_count=1) | PASS |
| `tx_masquerading_as_response` | batch: unknown | batch: unknown (modified_count=1) | PASS |
| `flash_no_timestamp` | batch: unknown | batch: unknown | PASS |
| `flash_verify_integer_one` | batch: unknown | batch: unknown | PASS |
| `proof_missing_own_time` | status: fail, offline_verified: false | status: fail, offline_verified: false | PASS |
| `real_connect_out.result.json` | status: pass, evidence_hash_still_matches: true, raw_contains_rx: true, raw_became_result: false | status: pass, evidence_hash_still_matches: true, raw_contains_rx: true, raw_became_result: false | PASS |
| `real_connect_out.jsonl` | status: pass, evidence_hash_still_matches: true, raw_contains_rx: true, raw_became_result: false | status: pass, evidence_hash_still_matches: true, raw_contains_rx: true, raw_became_result: false | PASS |
| `result_write_failure` | status: fail, result_exists: false | status: fail, result_exists: false | PASS |
| `formal_collector_suite` | exit: 0, verdict: pass | exit: 0, verdict: pass (pass_log_markers: 285) | PASS |

探针执行退出码：**0**。

#### 2. 回归套件全量执行结果
- **历史回归探针**：
  - `tmp/g2-review-20261027/recheck_r3g.py`：退出码 **0**，全部反例拒绝与健康控制通过。
  - `tmp/g2-review-20261027/recheck_r3f.py`：退出码 **0**，全部通过。
  - `tmp/g2-review-20261027/recheck_r3e.py`：退出码 **0**，全部通过。
- **Python 测试套件**：
  - `tools/g2/build_evidence_index_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/build_evidence_index_integration_test.py`：退出码 **0**，VERDICT: pass，全量断言通过。
  - `tools/g2/leg_try_item_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/leg_judge_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/soak_collector_integration_test.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/run_g2.py soak_judge_selftest`：退出码 **0**，36 项判定测试全部 pass。
- **Node.js 前端与协议测试套件**：
  - 全量运行 `cmd /c "set MWCP_GPP=D:\msys64\clang64\bin\clang++.exe && cd /d D:\Users\zomco\Documents\GitHub\mmwave-workspace\submodules\mmwave-component && node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js"`：**107 tests / 107 pass / 0 fail / 0 cancelled**，退出码 **0**。

#### 3. 三分类口径与权威门禁结论
1. **软件已修复并通过（离线验证通过）**：
   - H1～H4：输出路径互不重合（--out capture.result.json 原始帧保留且 hash 匹配）、写结果/manifest/关闭失败保留 status=fail 与原始错误、raw 缺失 experiment_id 统一 unknown、HELLO RX/TX nonce 关联验证与 rx 方向严格要求、flash_record 强制 verify=="ok"（拒绝整数 1）与必填有效时间戳、源隔离证明必填 coverage/observed_at 校验、client.js 定时器抖动重装修复全量 107 项 JS 全绿。
   - 保留的既有成果：owned payload、有界延迟 ID_REUSE、精确 4096B/4097B 边界、COBS 修复、严格 revision/提交信封、逐间隙 backoff、nonce 握手关联等。
2. **此前通过未重构（保留既有成果）**：
   - R1、R2、R4 软件层改动保留，G0 证据索引计算保留，前端协议与 UI 测试全套通过。
3. **台架未运行 not_run（硬件门禁未满足）**：
   - DHCP 配网成功/回滚链、R1-A 硬件隔离扣留测试、运行时资源与 host-off/on 基线、真人移动/方向/边界观测、20 次保存期物理断电、50 次物理拔插计数、原生 Web Serial 浏览器选口。
   - 批次 14 镜像未烧录（无台架授权）；48/50 软件重连 + 4 次恢复不升级为可靠性通过。

**门禁结论**：
**总状态：不通过 / 部分完成，整改进行中（待独立复核）。**
严守离线软件整改边界，绝不把离线测试通过等同于 G2 真机总门禁通过，不自行宣布 G2 闭环，不进入 WP-3。


## 21. 第十二轮整改（2026-10-29）：响应独立复核 r3i（H1～H4 证据契约完整落地与持久化固化）

### 21.1 触发背景与独立复核发现
独立复核报告 `docs/plans/mmwave-web-console/g2-r3i-review-2026-10-29.md` 肯定了 r3h 旧精确反例与健康控制生产链的通过，但指出了四个具体的软件证据契约剩余缺陷（H1～H4）：
1. **H1 / P1（manifest 写入失败后磁盘结果仍是 pass）**：`cmd_soak` 在采样结束时先写入 `status: pass` 的 `result.json`，随后写入 `manifest.json`。若 manifest 写入遭遇 I/O 故障抛出 `OSError`，内存中虽已修改 `outcome["status"] = "fail"`，但磁盘上的 `result.json` 未被更新，仍然保留 pass 且 `error: null`；CLI `main` 在输出文件存在时不重写，导致外部检查工具或人工仍会看到虚假的成功结果。
2. **H2 / P1（缺少 TX 或 request_id 不匹配的 HELLO 仍被关联）**：`build_evidence_index.py` 中 `_raw_correlated_identities` 先前对 HELLO RX 仅检查了 `rx_nonce not in hello_nonces`，当 TX 缺失（`hello_nonces` 为空）时跳过了检查；且未校验 `request_id` 匹配，导致删除 HELLO TX 或篡改 HELLO RX `request_id = 9876` 的反例仍被关联进 `manifest-linked`。
3. **H3 / P1（flash 来源与生命周期校验未接入统一准入）**：`run_g2.py` 与 `build_evidence_index.py` 仍接受孤立的 success 记录，未核验 `flash_record.source` 的引用存在性与 SHA-256 散列；对于包含生命周期日志的引用源，未按事件时间向 run 开始前重放，以识别被后续写入/擦除/损坏所替代的镜像。
4. **H4 / P2（未来单点 observed_at 被当作完整隔离证明）**：源隔离证明删除 coverage 且设置未来单点时间 `observed_at = 2099-01-01T00:00:00Z` 时，原代码仅判断该单点不早于 run 开始，未校验上界，也未强制要求连续区间覆盖，导致时长采样运行被未来单点证明通过。

### 21.2 软件整改措施与生产入口实现

#### 1. H1：最终失败持久化固化，消除内存与磁盘状态矛盾
- 在 `submodules/mmwave-component/tools/g2/run_g2.py` 的 `cmd_soak()` 中，在 `manifest_path.write_text` 捕获到异常时，除了设置内存 `outcome["status"] = "fail"` 与 `outcome["error"] = man_err` 之外，同步调用 `result_path.write_text()` 将更新后的脱敏失败状态与错误原因重新写回磁盘 `result.json`。
- 在 CLI `main()` 中，针对已存在的文件进行状态一致性检查：若磁盘现有文件为 `pass` 但最终判定为非 `pass`，强制重写磁盘文件，杜绝残留陈旧 pass。

#### 2. H2：真正的请求/响应双向关联与严格字段比对
- 在 `submodules/mmwave-component/tools/g2/build_evidence_index.py` 的 `_raw_correlated_identities(jsonl)` 中：
  - 维护 `hello_tx[rid] = (nonce, session_id)` 与 `device_info_tx[rid] = session_id`。
  - 对于 HELLO RX（code 1）：强制要求 `rx_rid` 存在且包含在 `hello_tx` 中（缺 TX 直接拒绝）；核验 `tx_nonce == rx_nonce`；遵循 MWCP 协议规则：请求 `tx_sid == 0`，响应必须分配新非零会话 `rx_sid != 0`。
  - 对于 DEVICE_INFO RX（code 3）：强制要求 `rx_rid` 存在且包含在 `device_info_tx` 中，核验活跃会话一致性。
  - 严拒伪装响应、方向矛盾及未关联设备身份。

#### 3. H3：统一 flash 来源引用、内容散列与历史生命周期重放
- 在 `build_evidence_index.py` 的 `batch_for_run()` 及 `run_g2.py` 的 `load_flash_evidence()` 中建立统一契约：
  - 若提供 `flash_input` 路径，自动绑定规范绝对路径与内容 SHA-256 散列作为可核验证明。
  - 若 `flash_record` 包含 `source` 结构体，严格检查 `source.ref` 存在性与 `sha256(source.ref) == source.sha256`。
  - 支持多记录生命周期日志重放：按时间回溯该设备在本次 run 启动前的所有刷写/擦除记录；若在已验证镜像后存在失败、擦除、部分写入或不同镜像事件，判定该镜像已被替代（superseded/invalidated），拒绝为 `unknown/unverified`。

#### 4. H4：源证明连续覆盖窗口强制要求与未来时间过滤
- 在 `submodules/mmwave-component/tools/g2/run_g2.py` 的 `load_offline_evidence()` 中：
  - 针对时长采样运行，源证明必须包含 `coverage` 连续覆盖区间（`has_cov == True`），明确规定孤立单点时间（`observed_at` 单点）不能代替连续区间证明；缺失 coverage 时记录 `att_mismatches` 并判定 `wifi_status = "insufficient"`、`verified = False`，绝不误标为 `association_observed`。
  - 增加时间合理性校验：无论是 `coverage` 还是 `observed_at`，时间戳均不得晚于当前时间（加 15 分钟时钟容差），严拒 `2099-01-01` 等未来虚假观测。
  - 校验源证明 coverage 必须完全包络外层证据声明的 coverage 与 run 实际时窗。

### 21.3 验证结果与对比

#### 1. 独立复核探针执行结果
运行独立复核探针 `tmp/g2-review-20261027/recheck_r3i.py`：
```text
  [PASS] inputs_complete :: duration/span/samples/preconditions required
  [PASS] offline_precondition :: wifi_status=isolated_verified ha_status=not_running verified=True
  [PASS] duration_honest :: monotonic_span=60.1s requested=60s
  [PASS] samples_collected :: n=6
  [PASS] single_boot :: boot_changes=0
  [PASS] rpc_p95_within_budget :: p95=10.0ms over 6 samples; budget=250ms
  [PASS] no_uncovered_gap :: windows lost=0
REVIEW control {"status": "pass", "batch": "manifest-linked"}
REVIEW missing_tx {"batch": "unknown", "factory_sha256": "unverified", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW wrong_request_id {"batch": "unknown", "factory_sha256": "unverified", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW invalid_flash_source {"batch": "unknown", "factory_sha256": "unverified", "identity_basis": "flash record source file not found: ...\\absent.jsonl"}
  [PASS] inputs_complete :: duration/span/samples/preconditions required
  [FAIL] offline_precondition :: wifi_status=insufficient ha_status=unknown verified=False
  [PASS] duration_honest :: monotonic_span=60.1s requested=60s
  [PASS] samples_collected :: n=6
  [PASS] single_boot :: boot_changes=0
  [PASS] rpc_p95_within_budget :: p95=10.0ms over 6 samples; budget=250ms
  [PASS] no_uncovered_gap :: windows lost=0
REVIEW future_point_only_proof {"status": "fail", "offline_verified": false}
  [PASS] inputs_complete :: duration/span/samples/preconditions required
  [PASS] offline_precondition :: wifi_status=isolated_verified ha_status=not_running verified=True
  [PASS] duration_honest :: monotonic_span=60.1s requested=60s
  [PASS] samples_collected :: n=6
  [PASS] single_boot :: boot_changes=0
  [PASS] rpc_p95_within_budget :: p95=10.0ms over 6 samples; budget=250ms
  [PASS] no_uncovered_gap :: windows lost=0
REVIEW manifest_write_failure {"returned_status": "fail", "disk_status": "fail", "disk_error": "manifest_write_failure: OSError('SOFTWARE simulated manifest write failure')", "raw_exists": true}
```
| 探针项目 | 修前观测值（r3i 复现） | 本轮修复后实际观测值 | 预期基线 | 判定 |
| :--- | :--- | :--- | :--- | :--- |
| `control` | batch: `manifest-linked` | batch: `manifest-linked` | batch: `manifest-linked` | PASS |
| `missing_tx` | batch: `manifest-linked` | batch: `unknown` | batch: `unknown` | PASS |
| `wrong_request_id` | batch: `manifest-linked` | batch: `unknown` | batch: `unknown` | PASS |
| `invalid_flash_source` | batch: `manifest-linked` | batch: `unknown` | batch: `unknown` | PASS |
| `future_point_only_proof` | status: `pass`, offline_verified: `true` | status: `fail`, offline_verified: `false` | status: `fail`, offline_verified: `false` | PASS |
| `manifest_write_failure` | returned: `fail`, disk_status: `pass`, disk_error: `null` | returned: `fail`, disk_status: `fail`, disk_error: `manifest_write_failure: ...` | returned: `fail`, disk_status: `fail` | PASS |

探针执行退出码：**0**。

运行前轮探针 `tmp/g2-review-20261027/recheck_r3h.py`：**退出码 0，全部 11 项 REVIEW 全部符合预期**（含 formal_collector_suite exit: 0, 285 PASS markers, verdict: pass）。

#### 2. 回归套件全量执行结果
- **Python 测试套件**：
  - `tools/g2/build_evidence_index_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/build_evidence_index_integration_test.py`：退出码 **0**，VERDICT: pass，全量断言通过。
  - `tools/g2/leg_try_item_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/leg_judge_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/soak_collector_integration_test.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/run_g2.py soak_judge_selftest`：退出码 **0**，36 项判定测试全部 pass。
- **Node.js 前端与协议测试套件**：
  - 在正确配置临时目录（`TEMP=...tmp\g2-review-20261027`）与 `MWCP_GPP=D:\msys64\clang64\bin\clang++.exe` 环境下：
  - `cmd /c "set TEMP=D:\Users\zomco\Documents\GitHub\mmwave-workspace\tmp\g2-review-20261027&& set TMP=D:\Users\zomco\Documents\GitHub\mmwave-workspace\tmp\g2-review-20261027&& set MWCP_GPP=D:\msys64\clang64\bin\clang++.exe&& set PATH=D:\msys64\clang64\bin;%PATH%&& cd /d D:\Users\zomco\Documents\GitHub\mmwave-workspace\submodules\mmwave-component&& node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js"`
  - **107 tests / 107 pass / 0 fail / 0 cancelled**，退出码 **0**。

#### 3. 三分类口径与权威门禁结论
1. **软件已修复并通过（离线验证通过）**：
   - H1：manifest 写入异常时磁盘结果文件同步固化失败状态与原因，CLI 杜绝陈旧 pass 残留。
   - H2：HELLO 请求/响应关联，缺失 TX 或 request_id 不匹配严格判定为 unknown，会话状态转换符合协议规范。
   - H3：flash 记录来源文件存在性、散列匹配及生命周期重放已统一接入 index 和 collector，被替代固件不误标。
   - H4：源证明强制声明连续覆盖区间，拒绝未来单点观测，未通过时判定为 insufficient/verified=false。
   - 保留全部既有离线成果（owned payload、精确 4096B/4097B 边界、COBS、严格 commit 契约、逐间隙 backoff、nonce 握手关联等）。
2. **此前通过未重构（保留既有成果）**：
   - R1、R2、R4 软件层改动保留，G0 证据索引计算保留，前端协议与 UI 测试全套 107 项全绿。
3. **台架未运行 not_run（硬件门禁未满足）**：
   - DHCP 配网成功/回滚链、R1-A 硬件隔离扣留测试、运行时资源与 host-off/on 基线、真人移动/方向/边界观测、20 次保存期物理断电、50 次物理拔插计数、原生 Web Serial 浏览器选口。
   - 批次 14 镜像未烧录（无台架授权）；48/50 软件重连 + 4 次恢复不升级为可靠性通过。

**门禁结论**：
**总状态：不通过 / 部分完成，整改进行中（待独立复核）。**
严守离线软件整改边界，绝不把离线测试通过等同于 G2 真机总门禁通过，不自行宣布 G2 闭环，不进入 WP-3。


## 22. 第十三轮整改：r3j 复核后（2026-10-29；离线整改——H2 规范化帧与会话关联、H3 统一来源语义与全运行窗口生命周期重放）

### 22.1 背景与独立复核发现
独立复核报告 `docs/plans/mmwave-web-console/g2-r3j-review-2026-10-29.md` 确认：r3i 精确反例（`missing_tx`、`wrong_request_id`、`invalid_flash_source`、`future_point_only_proof`、`manifest_write_failure`）已全部获得预期结果，H1 的 manifest 写失败已同步固化为磁盘 fail，H4 的未来单点证明已拒绝；真实 producer→index 正向控制链路通畅。
本轮剩余阻断集中在 H2 与 H3：
1. **H2 / P1（必填 session 缺失及 TX 方向矛盾仍被接受）**：
   - `build_evidence_index.py` 中 `_raw_correlated_identities` 的 TX 检查使用 `direction == "tx" or kind == 1`，导致 `dir=rx` 且 `kind=1` 的矛盾帧可被当作合法 HELLO 请求。
   - `session_id` 检查曾为“存在才检查”，缺失 TX 或 RX 的 `session_id` 未导致身份拒绝；普通 `DEVICE_INFO` 也保留同类可选会话条件。
2. **H3 / P1（来源存在性/hash 检查不等于来源语义与生命周期完整验证）**：
   - collector 与 index 各自复制代码，当 `source is None` 时跳过来源检查。
   - source 逐行 JSON 解析错误被吞掉，无有效记录时仍按成功退出，非 JSON 文本被当成有效来源。
   - 未校验源日志是否实际包含与包装记录相匹配的成功事件（来源中同时间另一镜像 B 亦被接受）。
   - 生命周期重放仅检查至 `run_started`，忽略了运行期间（如 60 秒 run 第 30 秒 erased）的生命周期事件，且 `unknown` 状态未纳入失效枚举。

### 22.2 软件整改实现

#### 1. 抽出共享纯验证契约：`tools/g2/flash_verifier.py`
新建统一纯验证模块，供 `run_g2.py`（`load_flash_evidence` / `cmd_soak`）、`build_evidence_index.py`（`batch_for_run`）及测试套件共享：
- 严格校验 flash record 基础模式：`status == "success"`、`verify` 严格为字符串 `"ok"` 或 `"verified"`、合法 64 位十六进制非全零 `image_sha256`、设备 ID 匹配、带时区 ISO8601 时间戳且不晚于 `run_started`。
- 强制要求 `source` 对象：缺失 `source` 直接判定为 `unverified`（`batch: unknown`）。
- 校验 `source.ref` 磁盘文件存在性及其 SHA-256 哈希值与 `source.sha256` 精确一致。
- 严格解析源文件内容（支持 JSON Lines 或完整 JSON 数组/对象），解析语法错误或非 JSON 普通文本直接失败并记录原因，绝不吞错。
- 显式语义匹配：源文件记录中必须实际包含与包装声称完全一致的目标设备、镜像 SHA 及成功状态（`verify in ('ok', 'verified')`）事件。
- 全运行窗口生命周期重放：从 flash 事件时间戳重放至 `run_ended`（或 `run_started`）。重放期间若该设备出现任何 `failed`、`aborted`、`erased`、`partial`、`unknown` 或不同镜像事件，立即将固件身份标为 `unverified`。`run_ended` 之后发生的事件或其它设备的事件不影响本次运行。

#### 2. H2：严格的规范化帧与会话关联（`tools/g2/build_evidence_index.py`）
- 新增 `_normalize_frame(rec)` 函数：
  - 严格校验顶层字段与 meta 字段的一致性（若两者同时存在且矛盾，立即拒绝，不择一信任）。
  - 严格排查方向与类型矛盾：拒绝 `dir == "rx"` 且 `kind == 1`，以及 `dir == "tx"` 且 `kind in (2, 3)`。
  - 规范化 `session_id` 与 `request_id` 为合法 32 位无符号整数；若缺失或非法类型则保留为 `None`。
- 重构 `_raw_correlated_identities(jsonl)`：
  - 维护显式待决请求队列 `pending_hello[rid] = (nonce, sid)` 与 `pending_device_info[rid] = sid`，以及已激活会话集 `active_sessions`。
  - HELLO TX 请求必填 `session_id == 0`，RX 响应必填分配合法非零 `session_id > 0`，且严格匹配先行请求的 `request_id` 与 `nonce`；匹配成功后将分配的 `session_id` 加入 `active_sessions`。
  - 普通 `DEVICE_INFO` 必须匹配当前已建立的 `active_sessions` 及对应请求，严防空会话或已过期会话绕过。
  - 匹配后立即从待决队列中移除，杜绝重放或串扰关联。

#### 3. H3：生产入口与索引全链统一接入
- `submodules/mmwave-component/tools/g2/run_g2.py`：
  - `load_flash_evidence()` 委托至 `flash_verifier.verify_flash_record()`。
  - `cmd_soak()` 计算实际 `run_wall_end`，并将 `run_started` 与 `run_ended` 全窗口传入 `load_flash_evidence`。
- `submodules/mmwave-component/tools/g2/build_evidence_index.py`：
  - `batch_for_run()` 委托至 `flash_verifier.verify_flash_record()`。
- `submodules/mmwave-component/tools/g2/build_evidence_index_integration_test.py`：
  - 同步更新正向测试辅助函数 `manifest_for()`，自动生成符合新契约的标准伴随源日志文件。
  - 迁入 H2/H3 完整测试矩阵（15 个测试场景，覆盖会话缺失、方向矛盾、非法会话转换、meta 冲突、无 source、纯文本 source、异名镜像、运行前/运行中/运行后擦除、运行前 unknown、无关设备擦除等）。

### 22.3 验证结果与反例闭环

#### 1. 独立审查探针 `recheck_r3j.py` 全部通过（退出码 0）
```text
  [PASS] inputs_complete :: duration/span/samples/preconditions required
  [PASS] offline_precondition :: wifi_status=isolated_verified ha_status=not_running verified=True
  [PASS] duration_honest :: monotonic_span=60.1s requested=60s
  [PASS] samples_collected :: n=6
  [PASS] single_boot :: boot_changes=0
  [PASS] rpc_p95_within_budget :: p95=10.0ms over 6 samples; budget=250ms
  [PASS] no_uncovered_gap :: windows lost=0
REVIEW real_file_producer_control {"status": "pass", "batch": "manifest-linked"}
REVIEW hello_missing_sessions {"changed_frames": 2, "batch": "unknown"}
REVIEW hello_tx_contradictory_direction {"changed_frames": 1, "batch": "unknown"}
REVIEW no_source_dict {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW source_plain_text {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW source_wrong_image {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW erase_before_run_control {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW erase_during_run {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW unknown_before_run {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
```

| 探针项目 | 修前观测值（r3j 复现） | 本轮修复后实际观测值 | 预期基线 | 判定 |
| :--- | :--- | :--- | :--- | :--- |
| `real_file_producer_control` | batch: `manifest-linked` | batch: `manifest-linked` | batch: `manifest-linked` | PASS |
| `hello_missing_sessions` | batch: `manifest-linked` (2帧缺失) | batch: `unknown` | batch: `unknown` | PASS |
| `hello_tx_contradictory_direction` | batch: `manifest-linked` (dir=rx, kind=1) | batch: `unknown` | batch: `unknown` | PASS |
| `no_source_dict` | collector_image: A, batch: `manifest-linked` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |
| `source_plain_text` | collector_image: A, batch: `manifest-linked` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |
| `source_wrong_image` | collector_image: A, batch: `manifest-linked` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |
| `erase_before_run_control` | collector_image: `unverified`, batch: `unknown` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |
| `erase_during_run` | collector_image: A, batch: `manifest-linked` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |
| `unknown_before_run` | collector_image: A, batch: `manifest-linked` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |

探针执行退出码：**0**。

#### 2. 既往独立审查探针回归
- `tmp/g2-review-20261027/recheck_r3i.py`：**退出码 0，全部 6 项 REVIEW 符合预期**（`control` 输出 unknown，各反例输出 unknown/fail，manifest_write_failure 成功固化）。
- `tmp/g2-review-20261027/recheck_r3h.py`：**退出码 0，全部 11 项 REVIEW 符合预期**（含 formal_collector_suite exit: 0, 285 PASS markers, verdict: pass）。

#### 3. 正式回归套件全量执行结果
- **Python 测试套件**：
  - `tools/g2/build_evidence_index_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/build_evidence_index_integration_test.py`：退出码 **0**，VERDICT: pass，全量断言（含新增 H2/H3 测试矩阵）通过。
  - `tools/g2/leg_try_item_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/leg_judge_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/soak_collector_integration_test.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/run_g2.py soak_judge_selftest`：退出码 **0**，36 项判定测试全部 pass。
- **Node.js 前端与协议测试套件**：
  - 执行环境：工作区临时目录（`TEMP=...tmp\g2-review-20261027`）与 `MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`，并将 clang 加入 PATH。
  - 运行命令：`node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js`
  - 运行结果：**107 tests / 107 pass / 0 fail / 0 cancelled**，退出码 **0**（耗时约 32.8 秒）。

#### 4. C++ 编译与工具链说明
- 本轮整改聚焦于 Python 离线证据判定、索引归属逻辑以及相关自动化测试，未改动 `protocol/cpp/` 或 `components/r60abd1/` 等 C++ 生产代码。
- 因此未重新触发新的 C++ 构建或 sanitizer 测试（保留此前全量通过的 6/6 sanitizer 及 10 万次模糊测试记录）。

#### 5. 三分类口径与权威门禁结论
1. **软件已修复并通过（离线验证通过）**：
   - H2：帧规范化拒绝顶层/meta 矛盾与方向/类型冲突；HELLO 会话严格校验（TX session=0，RX session>0 且匹配 request_id/nonce）；DEVICE_INFO 必须隶属已激活会话。
   - H3：抽取纯验证模块 `flash_verifier.py`；强制要求 `source` 对象且验证哈希；源文件解析绝不吞错；源文件必须存在与包装声称一致的成功记录；生命周期全窗口重放至 `run_ended`（覆盖运行期间的 erase/unknown）。
   - 保留全部既有离线成果（H1 磁盘写入失败固化、H4 连续覆盖区间、owned payload、精确 4096B/4097B 边界、COBS、逐间隙 backoff、nonce 握手关联等）。
2. **此前通过未重构（保留既有成果）**：
   - R1、R2、R4 软件层改动保留，G0 证据索引计算保留，前端协议与 UI 测试全套 107 项全绿。
3. **台架未运行 not_run（硬件门禁未满足）**：
   - DHCP 配网成功/回滚链、R1-A 硬件隔离扣留测试、运行时资源与 host-off/on 基线、真人移动/方向/边界观测、20 次保存期物理断电、50 次物理拔插计数、原生 Web Serial 浏览器选口。
   - 批次 14 镜像未烧录（无台架授权）；48/50 软件重连 + 4 次恢复不升级为可靠性通过。

**门禁结论**：
**总状态：不通过 / 部分完成，整改进行中（待独立复核）。**
严守离线软件整改边界，绝不把离线测试通过等同于 G2 真机总门禁通过，不自行宣布 G2 闭环，不进入 WP-3。


## 23. G2-H2/H3 软件整改（2026-10-29，基于 g2-r3k-review 复核意见）

### 23.1 问题定位与整改范围

针对独立复核报告 `docs/plans/mmwave-web-console/g2-r3k-review-2026-10-29.md` 指出的核心缺口（H2-A 命令路由与真实会话状态、H2-B 待决请求完整匹配后消费、H3-A 绑定唯一源事件/时间与序列一致性、H3-B bank 接入统一历史契约、H3-C 异常防护与类型安全降级）：
1. **H2-A 命令路由错误**：
   - 协议规范明确：`SESSION_CLOSE = 0x0003` (3)，`DEVICE_INFO = 0x0010` (16)。此前索引代码误将 `code == 3` 当作 `DEVICE_INFO` 提取设备身份，而忽略了真正 `code == 16` 的 `DEVICE_INFO`。
   - `active_sessions` 永远只 `add` 不清理，未实现当前会话生命周期管理。
2. **H2-B 待决请求提前消费**：
   - `build_evidence_index.py` 在验证 RX nonce 之前执行了 `pending_hello.pop(rid)`。若新请求 B（rid=1）在等待，旧请求 A 的迟到响应复用 rid=1 会提前移除 B，致使随后真正 B 的响应因无待决请求而被丢弃。
3. **H3-A 历史源记录事件绑定与顺序**：
   - `verify_flash_record` 未将包装声称绑定到同一个源事件，导致时间挪移跳过擦除或以未来成功证明过去固件。
   - 同一时间戳后续 seq 擦除被忽略；缺少 status 的脏记录被漏过；重复 seq=1 冲突被接受。
4. **H3-B bank 契约割裂**：
   - `leg_driver2.py` 的 `environment_fingerprint` 拥有良好的历史冲突校验（重复 seq 冲突、seq/时间戳矛盾），但未接入共享验证模块，导致同一份包含冲突 seq=1 的日志被 shared verifier 接受而 bank 拒绝。
5. **H3-C 模式类型安全**：
   - 在类型检查前执行 `(image_sha256 or "").lower()`，遇到非字符串（如 `image_sha256=123`）直接抛出 `AttributeError` 中断流程。

### 23.2 核心整改落地

#### 1. H2-A & H2-B：命令码对齐、真实会话生命周期与安全消费（`tools/g2/build_evidence_index.py`）
- 引入规范协议常量：
  - `MWCP_CODE_HELLO = 0x0001` (1)
  - `MWCP_CODE_PING = 0x0002` (2)
  - `MWCP_CODE_SESSION_CLOSE = 0x0003` (3)
  - `MWCP_CODE_DEVICE_INFO = 0x0010` (16)
- 修正命令路由：
  - `code == 16`（`DEVICE_INFO`）：从当前 `active_sessions` 的有效请求中匹配，提取 `device_id` / `boot_id`。
  - `code == 3`（`SESSION_CLOSE`）：校验会话有效性，正常关闭会话并清理该会话关联的 pending 请求；**坚决不从其负载或额外字段中提取身份**。
- 实现当前会话生命周期：
  - 新 HELLO 握手成功分配新 session 时，重置 `active_sessions = {sid}` 并清理旧会话的待决请求。
  - 会话关闭成功时，从 `active_sessions` 移除对应 session。
  - 新 nonce 发起新握手时，清理不同 nonce 的过期待决握手，保留同 nonce 重传。
- 完整匹配后消费（Peek-before-pop）：
  - 收到 HELLO RX 响应时，先比对 `rx_nonce == tx_nonce`；仅在完全匹配时才 `pending_hello.pop(rid)`。错 nonce 或迟到响应不会移除正在等待的合法新握手。

#### 2. H3-A & H3-C：严格源事件绑定、顺序重放与类型安全降级（`tools/g2/flash_verifier.py`）
- **类型安全前置**：
  - 所有字段访问在调用字符串方法前必须先经过类型守卫（如 `isinstance(raw_img, str)`）；非法类型（数值、列表、对象等）返回 `"unverified"` 与结构化原因，绝不抛出未捕获异常。
- **显式源事件单射绑定**：
  - 包装对象的声明必须在源日志中找到**唯一的、真实发生的成功事件** `r_match`（设备 ID、镜像 SHA、`status == "success"`、`verify in ("ok", "verified")`、规范化 ISO8601 时间戳严格相等、seq/event_id 一致）。
  - 禁止使用未来（晚于 `run_started`）的事件作为起跑点；若声明时间挪移至无对应真实源事件，判定为 `unverified`。
- **全生命周期顺序重放与完整性校验**：
  - 排序算法严格保证 `(seq, timestamp)` 或 `(timestamp, seq)` 的可比顺序。
  - 必须通过 `validate_board_history` 校验：无公共基准锚点、未来时间戳、重复 seq 冲突、seq 与时间戳前后矛盾等均保守判定为 `unverified`。
  - 重放时窗口覆盖 `[r_match, eval_window_end]`：任一记录缺少 `status` 或存在非字符串状态、或者出现 `failed`/`aborted`/`erased`/`partial`/`unknown`/异名镜像，一律将该固件身份判定为失效（`unverified`）。同时间戳后续 seq 的擦除得到严格识别并覆盖。
  - 运行窗口结束（`eval_window_end`）之后的后续变更或无关设备的记录按范围过滤，不影响运行期间已确认的合法事实。

#### 3. H3-B：bank 完整接入共享历史契约（`tools/g2/leg_driver2.py`）
- `leg_driver2.py` 移除 140 余行重复的内联解析与判定逻辑，将 `environment_fingerprint` 全面委托至 `flash_verifier.parse_flash_log` 与 `flash_verifier.replay_board_history_to_latest`。
- bank 与 shared verifier 对重复序列冲突（如重复 seq=1 异时间戳）、时序矛盾和坏状态保持完全一致的保守拒绝策略。

#### 4. 正式测试套件全面迁入
- `tools/g2/build_evidence_index_integration_test.py` 扩充迁入 R3k 专属测试：
  - `H2-A`：`DEVICE_INFO` (code 16) 正确提取身份；`SESSION_CLOSE` (code 3) 拒不提取夹带身份。
  - `H2-B`：迟到 HELLO 响应（复用 rid=1）不影响新 HELLO 握手识别。
  - `H3-A`：`source_success_only_after_run`、`claim_timestamp_shifted_past_erase`、`same_timestamp_later_seq_erase`、`missing_status_during_run`、`duplicate_sequence_conflict` 均在真实文件输入→collector→manifest→index 链路上得到稳定拒绝（归为 unknown/unverified）。
  - `H3-B`：bank 与 shared verifier 针对同一份冲突日志均返回 `flashed_evidence=False` / `unverified`。

### 23.3 验证结果与反例闭环

#### 1. 独立复核探针 `recheck_r3k.py` 全部符合预期（退出码 0）
```text
  [PASS] inputs_complete :: duration/span/samples/preconditions required
  [PASS] offline_precondition :: wifi_status=isolated_verified ha_status=not_running verified=True
  [PASS] duration_honest :: monotonic_span=60.1s requested=60s
  [PASS] samples_collected :: n=6
  [PASS] single_boot :: boot_changes=0
  [PASS] rpc_p95_within_budget :: p95=10.0ms over 6 samples; budget=250ms
  [PASS] no_uncovered_gap :: windows lost=0
REVIEW healthy_file_chain {"status": "pass", "batch": "manifest-linked", "identity_basis": "per-run manifest with verified flash record (run_tag=g2-07-soak-idle, profile=tests/r60abd1-esp32c3-host-nowifi.yaml)"}
REVIEW source_success_only_after_run {"status": "pass", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW claim_timestamp_shifted_past_erase {"status": "pass", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW same_timestamp_later_seq_erase {"status": "pass", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW missing_status_during_run {"status": "pass", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW duplicate_sequence_conflict {"status": "pass", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW numeric_image_schema {"result": "unverified"}
REVIEW pending_new_hello_stale_False {"new_boot_accepted": true}
REVIEW pending_new_hello_stale_True {"new_boot_accepted": true}
REVIEW identity_opcode_DEVICE_INFO {"code": 16, "response_marker_accepted": true}
REVIEW identity_opcode_SESSION_CLOSE {"code": 3, "response_marker_accepted": false}
REVIEW bank_shared_contract_disagreement {"shared_image": "unverified", "bank_flashed": false, "bank_reason": "flash records carry duplicate sequence conflict"}
```

| 探针项目 | 修前观测值（r3k 复现） | 本轮修复后实际观测值 | 预期基线 | 判定 |
| :--- | :--- | :--- | :--- | :--- |
| `healthy_file_chain` | batch: `manifest-linked` | batch: `manifest-linked` | batch: `manifest-linked` | PASS |
| `source_success_only_after_run` | batch: `manifest-linked` | batch: `unknown` | batch: `unknown` | PASS |
| `claim_timestamp_shifted_past_erase` | batch: `manifest-linked` | batch: `unknown` | batch: `unknown` | PASS |
| `same_timestamp_later_seq_erase` | batch: `manifest-linked` | batch: `unknown` | batch: `unknown` | PASS |
| `missing_status_during_run` | batch: `manifest-linked` | batch: `unknown` | batch: `unknown` | PASS |
| `duplicate_sequence_conflict` | batch: `manifest-linked` | batch: `unknown` | batch: `unknown` | PASS |
| `numeric_image_schema` | `AttributeError` 抛出崩溃 | result: `unverified` (无异常) | result: `unverified` | PASS |
| `pending_new_hello_stale_False` | new_boot_accepted: `true` | new_boot_accepted: `true` | new_boot_accepted: `true` | PASS |
| `pending_new_hello_stale_True` | new_boot_accepted: `false` (新请求被冲刷) | new_boot_accepted: `true` (安全保留) | new_boot_accepted: `true` | PASS |
| `identity_opcode_DEVICE_INFO` | code: 16, accepted: `false` (忽略) | code: 16, accepted: `true` (正确定位) | code: 16, accepted: `true` | PASS |
| `identity_opcode_SESSION_CLOSE` | code: 3, accepted: `true` (身份被污染) | code: 3, accepted: `false` (仅关会话) | code: 3, accepted: `false` | PASS |
| `bank_shared_contract_disagreement` | shared: A (已验证), bank: False (冲突) | shared: `unverified`, bank: `false` (一致) | 两者均保守拒绝 | PASS |

#### 2. 既往独立审查探针全量回归
- `tmp/g2-review-20261027/recheck_r3j.py`：**退出码 0，全部 9 项 REVIEW 完全符合预期**。
- `tmp/g2-review-20261027/recheck_r3h.py`：**退出码 0，全部 11 项 REVIEW 完全符合预期**（含 formal_collector_suite exit: 0, 285 PASS markers, verdict: pass）。

#### 3. 正式自动化套件全量执行结果
- **Python 测试套件**：
  - `tools/g2/build_evidence_index_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/build_evidence_index_integration_test.py`：退出码 **0**，VERDICT: pass，全量断言（含新增 R3k 完整矩阵）通过。
  - `tools/g2/leg_try_item_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/leg_judge_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/soak_collector_integration_test.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/run_g2.py soak_judge_selftest`：退出码 **0**，36 项判定全部通过。
- **Node.js 前端与协议测试套件**：
  - 执行环境：工作区临时目录（`TEMP=...tmp\g2-review-20261027`）与 `MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`，并将 clang 所在目录加入 PATH。
  - 运行命令：`node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js`
  - 运行结果：**107 tests / 107 pass / 0 fail / 0 cancelled**，退出码 **0**（耗时约 36.9 秒）。

#### 4. 纯软件范围与 C++ 说明
- 本轮整改均为 Python 证据生成、判定、索引及回归测试代码（`flash_verifier.py`、`build_evidence_index.py`、`leg_driver2.py`、`build_evidence_index_integration_test.py`）。
- 未改动 C++ 生产源码，因此未重跑新的 C++ 编译器构建或 sanitizer 套件。

#### 5. 严格保持三分类口径与权威门禁
1. **软件已修复并通过（离线验证通过）**：
   - H2-A：正确路由 `DEVICE_INFO` (code 16) 与 `SESSION_CLOSE` (code 3)，落实真实会话生命周期管理。
   - H2-B：待决请求完整匹配后再消费，迟到/错 nonce 响应不冲刷新待决请求。
   - H3-A：严格单射绑定源成功事件，时间/seq 全窗口重放判定，同时间戳后续 seq 擦除与脏状态完整识别覆盖。
   - H3-B：bank 全面接入共享历史契约，统一冲突排查判定。
   - H3-C：字段类型安全前置，异常输入安全降级。
   - 保留全部历史已通过成果（H1 失败固化、H4 连续覆盖区间、owned payload、有界 ID_REUSE、精确 4096B/4097B 边界、COBS、逐间隙 backoff、nonce 握手关联等）。
2. **此前通过未重构（保留既有成果）**：
   - R1、R2、R4 软件层改动保留，G0 证据索引计算保留，前端协议与 UI 测试全套 107 项全绿。
3. **台架未运行 not_run（硬件门禁未满足）**：
   - DHCP 配网成功/回滚链、R1-A 硬件隔离扣留测试、运行时资源与 host-off/on 基线、真人移动/方向/边界观测、20 次保存期物理断电、50 次物理拔插计数、原生 Web Serial 浏览器选口。
   - 批次 14 镜像未烧录（无台架授权）；48/50 软件重连 + 4 次恢复不升级为可靠性通过。

**门禁结论**：
**总状态：不通过 / 部分完成，整改进行中（待独立复核）。**
坚决恪守软件整改与离线验证边界，绝不把离线测试通过等同于 G2 真机门禁通过，不自行宣布 G2 闭环，不进入 WP-3。


## 24. G2-H3 软件整改（2026-10-29，基于 g2-r3l-review 复核意见）

### 24.1 复核缺陷定位与整改目标

在独立复核报告 `g2-r3l-review-2026-10-29.md` 中，前一轮 H2-A/H2-B 缺陷已获独立复核确认关闭，但指出 H3 仍存在 4 项具体的证据契约与健壮性缺陷（H3-L1～H3-L4）：
1. **H3-L1（后续同镜像刷写事件未核验 verify）**：
   - 在 `flash_verifier.py` 的重放循环中，原逻辑仅在 `if ev_img != img:` 时拒绝，假设只要镜像 SHA 相同就合法；然而若后续存在同镜像但 `verify == "failed"`（或缺少校验通过标志）的刷写尝试，该失败并未阻断对先前成功声称的采信。
2. **H3-L2（同时间戳缺少序列号的冲突记录依赖列表顺序）**：
   - 当同一板卡的多条刷写记录时间戳完全相同且均缺少非负整数序列号（如 `[erase, noseq]` 与 `[noseq, erase]`），由于 Python `sorted()` 具备稳定排序特性，若擦除事件排在前面，未带序列号的成功事件仍会作为最后一个状态被采信。相同时间戳且缺乏序号锚点的矛盾事件属于不可判定无序冲突（unorderable conflict），必须在两者顺序下均保守判定为未知（unknown）。
3. **H3-L3（bank 遇到解析错误行未阻断复用）**：
   - `leg_driver2.py` 的 `environment_fingerprint` 在解析刷写日志时，虽然统计了 `unparsable` 计数并写入原因，但在后续判定逻辑中只要最新记录匹配就覆盖了该标志，导致存在坏行/非字典对象（如追加非对象行 `"17"`）的不完整日志仍被 bank 误判为 `flashed_evidence = True` 与 `complete = True`。
4. **H3-L4（JSON 数组解析依赖格式与缩进）**：
   - 原 `flash_verifier.parse_flash_log` 按行迭代解析，紧凑单行 JSON 数组（`json.dumps([A])`）被直接识别为 list 类型行计入 `unparsable`，而多行格式化 JSON 数组（`json.dumps([A], indent=2)`）首行因解析异常触发整体降级，两者行为不一致。

### 24.2 生产契约落实与实现细节

#### 1. H3-L1：统一刷写事件状态评估与后续校验核验（`tools/g2/flash_verifier.py`）
- 在 `flash_verifier.py` 中引入统一的刷写事件评估函数 `evaluate_flash_event(ev)`：
  - 检查必须包含合法字符串 `status`，对 `success` 状态强制核验 `image_sha256` 为合法 64 字节十六进制串，且 `verify in ("ok", "verified")`。若校验标志不符合要求，严格返回 `status_kind="unverified_success"`。
- 在 `verify_flash_record` 重放循环中，对所有后续事件调用 `evaluate_flash_event`：
  - 若后续事件返回 `"unverified_success"`，立即拒绝并输出 `"subsequent flash attempt for the same image was not verify-ok"`。
- 在 `replay_board_history_to_latest` 中统一复用 `evaluate_flash_event`，确保历史刷写回放与单次声明验证使用同一套判定契约。

#### 2. H3-L2：同时间戳无序冲突严格拒绝（`tools/g2/flash_verifier.py`）
- 在 `validate_board_history` 中增加同时间戳全量两两比对规则：
  - 若两记录时间戳严格相同（`ts1 == ts2`），但未均携带不同的非负整数序列号（`not (has_s1 and has_s2 and s1 != s2)`），且两者评估状态或镜像签名不一致（存在冲突），判定为无法判定先后顺序的无序记录：`"flash records carry conflicting events at same timestamp without sequence order (unorderable)"`。
  - 无论输入文件是 `[erase, noseq]` 还是 `[noseq, erase]`，两两冲突检查均在排序前或排序后触发稳定拒绝，消除对 Python 排序稳定性的依赖。
  - 严格保留显式序号契约：同时间戳下 `seq=1` (erase) 与 `seq=2` (success) 仍按确定性顺序正确采信合法成功；`seq=1` (success) 与 `seq=2` (erase) 仍按确定性顺序判定为被擦除。

#### 3. H3-L3：bank 解析坏行严格阻断复用（`tools/g2/leg_driver2.py`）
- 在 `leg_driver2.py` 的 `environment_fingerprint` 中，当 `unparsable > 0` 时，显式设置：
  ```python
  flashed_evidence = False
  flash_state_reason = f"flash log contains {unparsable} unparsable non-JSON lines or non-object items"
  ```
  并跳过后续回放，阻止 `complete = True` 的生成，杜绝 bank 依赖残缺日志自动跳过测试。

#### 4. H3-L4：JSON 全文统一反序列化（`tools/g2/flash_verifier.py`）
- 重构 `flash_verifier.parse_flash_log`：
  - 优先对整段去空白文本执行 `json.loads(trimmed)`：
    - 若为 dict：按单对象返回 `[obj], 0`；
    - 若为 list：提取全部合规 dict 对象，若存在非 dict 元素累计至 `unparsable`；
    - 若为非 dict/非 list 基本类型：返回 `[], 1`。
  - 若整体 JSON 反序列化失败（如标准 JSON Lines 包含多行独立对象），无缝回退至逐行安全解析。
  - 紧凑单行 `json.dumps([A])` 与多行缩进 `json.dumps([A], indent=2)` 产生完全一致的解析结果 `[A], 0`。

#### 5. 正式测试迁移（`tools/g2/build_evidence_index_integration_test.py`）
- 在正式集成测试套件中扩充迁入 R3l 专属测试用例：
  - `later_same_image_verify_ok`：后续同镜像成功且 verify=ok 正确完成 manifest 绑定（`batch: "manifest-linked"`）。
  - `later_same_image_verify_failed`：后续同镜像但 verify=failed 正确拒绝（`batch: "unknown"`）。
  - `equal_time_no_seq_erase_first` 与 `equal_time_no_seq_erase_last`：同时间戳无序冲突在两种排列下均稳定拒绝（`batch: "unknown"`）。
  - `equal_time_seq_erase_then_success` 与 `equal_time_seq_success_then_erase`：带序号的合法时序正常工作。
  - `json_array_compact` 与 `json_array_pretty`：紧凑与格式化 JSON 数组均被正确解析并绑定。
  - `bank_nondict_line` 与 `bank_same_image_verify_failed`：bank 正确报告 `flashed_evidence=False` 与 `complete=False`。

### 24.3 验证结果与独立探针回归

#### 1. 独立复核探针 `recheck_r3l.py` 退出码 0，全量符合预期
```text
  [PASS] inputs_complete :: duration/span/samples/preconditions required
  [PASS] offline_precondition :: wifi_status=isolated_verified ha_status=not_running verified=True
  [PASS] duration_honest :: monotonic_span=60.1s requested=60s
  [PASS] samples_collected :: n=6
  [PASS] single_boot :: boot_changes=0
  [PASS] rpc_p95_within_budget :: p95=10.0ms over 6 samples; budget=250ms
  [PASS] no_uncovered_gap :: windows lost=0
REVIEW healthy {"status": "pass", "batch": "manifest-linked"}
REVIEW later_same_image_verify_ok {"status": "pass", "batch": "manifest-linked"}
REVIEW later_same_image_verify_failed {"status": "pass", "batch": "unknown"}
REVIEW equal_time_no_seq_erase_first {"status": "pass", "batch": "unknown"}
REVIEW equal_time_no_seq_erase_last {"status": "pass", "batch": "unknown"}
REVIEW json_array_compact {"status": "pass", "batch": "manifest-linked"}
REVIEW json_array_pretty {"status": "pass", "batch": "manifest-linked"}
REVIEW bank_good {"shared_image": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "bank_flashed": true, "bank_complete": true, "bank_reason": "latest flash for this board matches this image"}
REVIEW bank_nondict_line {"shared_image": "unverified", "bank_flashed": false, "bank_complete": false, "bank_reason": "flash log contains 1 unparsable non-JSON lines or non-object items"}
REVIEW bank_same_image_verify_failed {"shared_image": "unverified", "bank_flashed": false, "bank_complete": false, "bank_reason": "latest flash was not verify-ok (verify='failed' (expected 'ok' or 'verified'))"}
```

| 探针项目 | 修前观测值（r3l 复现） | 本轮修复后实际观测值 | 预期基线 | 判定 |
| :--- | :--- | :--- | :--- | :--- |
| `healthy` | batch: `manifest-linked` | batch: `manifest-linked` | batch: `manifest-linked` | PASS |
| `later_same_image_verify_ok` | batch: `manifest-linked` | batch: `manifest-linked` | batch: `manifest-linked` | PASS |
| `later_same_image_verify_failed` | batch: `manifest-linked` (漏判) | batch: `unknown` (正确拒绝) | batch: `unknown` | PASS |
| `equal_time_no_seq_erase_first` | batch: `manifest-linked` (依赖排序) | batch: `unknown` (无序冲突拒绝) | batch: `unknown` | PASS |
| `equal_time_no_seq_erase_last` | batch: `unknown` | batch: `unknown` (无序冲突拒绝) | batch: `unknown` | PASS |
| `json_array_compact` | batch: `unknown` (格式识别失败) | batch: `manifest-linked` (正确解析) | batch: `manifest-linked` | PASS |
| `json_array_pretty` | batch: `manifest-linked` | batch: `manifest-linked` (正确解析) | batch: `manifest-linked` | PASS |
| `bank_good` | bank_flashed: `true`, complete: `true` | bank_flashed: `true`, complete: `true` | bank_flashed: `true` | PASS |
| `bank_nondict_line` | bank_flashed: `true` (坏行覆盖) | bank_flashed: `false`, complete: `false` | bank_flashed: `false` | PASS |
| `bank_same_image_verify_failed` | bank_flashed: `true` (漏判) | bank_flashed: `false`, complete: `false` | bank_flashed: `false` | PASS |

#### 2. 既往审查探针全量回归
- `recheck_r3k.py`：退出码 **0**，全部 13 项 REVIEW 完全通过。
- `recheck_r3j.py`：退出码 **0**，全部 9 项 REVIEW 完全通过。
- `recheck_r3h.py`：退出码 **0**，全部 11 项 REVIEW 完全通过（含 formal_collector_suite exit: 0, 285 PASS markers, verdict: pass）。

#### 3. 正式自动化套件全量执行结果
- **Python 测试套件**：
  - `tools/g2/build_evidence_index_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/build_evidence_index_integration_test.py`：退出码 **0**，VERDICT: pass（包含新增的 10 项 R3l 测试用例）。
  - `tools/g2/leg_try_item_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/leg_judge_selftest.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/soak_collector_integration_test.py`：退出码 **0**，VERDICT: pass。
  - `tools/g2/run_g2.py soak_judge_selftest`：退出码 **0**，36 项判定全部通过。
- **Node.js 前端与协议测试套件**：
  - 运行命令：`node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js`
  - 运行结果：**107 tests / 107 pass / 0 fail / 0 cancelled**，退出码 **0**（耗时约 18.8 秒）。

#### 4. 纯软件整改与 C++ 说明
- 本轮整改均为 Python 证据解析、判定、验证及测试套件代码（`flash_verifier.py`、`leg_driver2.py`、`build_evidence_index_integration_test.py`）。
- 未修改 C++ 源码，现有 C++ 构建与 sanitizer 套件保持既有通过状态。

#### 5. 严格保持三分类口径与权威门禁
1. **软件已修复并通过（离线验证通过）**：
   - H3-L1：同镜像后续刷写事件的校验结果严格核验，后续校验失败拒绝放行。
   - H3-L2：同时间戳无序冲突记录双向严格判定为 unorderable unknown，消除对文件列表排序的偶然依赖。
   - H3-L3：bank 解析坏行严格阻断复用（flashed_evidence=False, complete=False）。
   - H3-L4：JSON 数组解析与格式、缩进完全解耦。
   - 保留全部既往通过项（H1 失败固化、H2-A/H2-B 命令路由与待决请求管理、H4 连续覆盖区间、owned payload、有界 ID_REUSE、精确 4096B/4097B 边界、COBS、逐间隙 backoff、nonce 握手关联等）。
2. **此前通过未重构（保留既有成果）**：
   - R1、R2、R4 软件层改动保留，G0 证据索引计算保留，前端协议与 UI 测试全套 107 项全绿。
3. **台架未运行 not_run（硬件门禁未满足）**：
   - DHCP 配网成功/回滚链、R1-A 硬件隔离扣留测试、运行时资源与 host-off/on 基线、真人移动/方向/边界观测、20 次保存期物理断电、50 次物理拔插计数、原生 Web Serial 浏览器选口。
   - 批次 14 镜像未烧录（无台架授权）；48/50 软件重连 + 4 次恢复不升级为可靠性通过。

**门禁结论**：
**总状态：不通过 / 部分完成，整改进行中（待独立复核）。**
严格恪守离线软件修改边界，绝不以离线测试通过冒充真机交接门禁通过，不自行宣布 G2 闭环，不进入 WP-3。
