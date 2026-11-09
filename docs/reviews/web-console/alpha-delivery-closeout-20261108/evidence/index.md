# 运行索引：Alpha 交付收口（2026-11-08）

三条结论线分开，不合并：**构建通过 ≠ 真机通过 ≠ 已发布**。

| 编号 | 事项 | 状态 | 材料 |
| --- | --- | --- | --- |
| R-1 | 候选工具/发布工具/USB 检查回归 | 通过（22/22、23/23、exit 0） | `test-build-r60-candidate.log`、`test-releases.log`、`check-r60-usb-profile.log` |
| R-2 | 真实构建 run `closeout-alpha-20261108`（v0.1.0-alpha.2，独立运行目录 `tmp/closeout/{data,out}-v010a2`） | **未完成**：source-state/盖章配置/配置检查完成；目标编译因注册表网络出口阻断失败，`artifact-summary.json` status=failed stage=compile_command | `real-run-source-state.json`、`real-run-source-dirty.patch`、`real-run-compiled.factory.yaml`、`real-run-failed-summary.json`、`real-run-compile-failure.log`、`network-probe.log` |
| R-3 | source-state 抽查 | 通过（真实运行）：48 输入哈希与实际文件一致；HEAD `2c0c0e9d…`；dirty 范围 2 文件 | `real-run-source-state.json`（`evidence/` 内副本） |
| R-4 | 盖章配置真实 ESPHome 校验（从运行目录） | 通过，退出 0：`version: "v0.1.0-alpha.2"`、`release_channel: alpha`、深目录 include 解析正确 | `real-run-compiled.factory.yaml`；重跑命令见报告 |
| R-5 | 打包/校验（新候选） | **not_run**：无新产物（依赖 R-2 重跑） | 打包校验路径未变：`test-releases.log` 23/23；`archive-bundle-revalidate.log` 用当前工具重校验 2026-11-06 存档通过 |
| R-6 | 新候选真机 | **not_run**：无授权，且前置编译未完成 | — |
| R-7 | 发布 | **未批准**：由维护者决定首次 Alpha 短真机/发布 | — |
| R-8 | 本轮工具源码身份 | 已存档（未提交工作树） | `source-diff-closeout.patch`、`source-files-closeout.sha256`、`worktree-state.txt` |

## 已知限制

- 本环境当前 HTTP 出口不可达（注册表/github 超时，DNS 正常）：R-2 的编译阶段被阻断。网络恢复后在新运行目录重跑同一条构建命令即可，工具无需再改。
- `source-state` 覆盖组件自有源码/配置与三个工具脚本（48 文件）；不追溯全部 ESPHome 依赖源码（固定版本 + venv 锁已记录，按包边界延期）。
- 2026-11-06 旧演练构建的时点快照缺失是既有事实，本轮未补造；其产物哈希与构建记录仍有效。
- 脏树演练构建不是发布候选；正式 Alpha 必须由维护者选定提交经 Publish 工作流构建。

## 复核命令（组件根目录）

```bash
python -m unittest discover -s tests -p test_build_r60_candidate.py -v
python -m unittest discover -s tests -p test_releases.py -v
python scripts/check_r60_usb_profile.py
.esphome/candidate-venv/Scripts/python.exe -m esphome config tmp/closeout/data-v010a2/r60abd1.factory.yaml
python ../../docs/.../alpha-review-20261107/input-probe.py   # 可选：上轮独立探针
```

重建/重跑新候选（网络恢复后，新运行目录）：

```bash
python scripts/build_r60_candidate.py --python .esphome/candidate-venv/Scripts/python.exe \
  --data-dir tmp/closeout/data-<new> --output tmp/closeout/out-<new> \
  --version v0.1.0-alpha.2 --run-id <new-run-id>
```

无秘密、无浏览器目录、无 node_modules、无重复站点混入本目录；大二进制留在 `tmp/closeout/` 本地运行目录，不入 Git。
