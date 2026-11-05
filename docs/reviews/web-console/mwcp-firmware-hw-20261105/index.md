# 证据索引：mwcp-firmware-hw-20261105

短真机未通过，也不是发布批准。原始 not_run 报告没有改写成通过。

| 材料 | 作用 | 不能当成 |
| --- | --- | --- |
| [attempt-1125/report.md](attempt-1125/report.md) | 11:25 截图与 11:51 一次网页烧录的分开记录。行为 4 为 fail，5～7 为 not_run | 本候选已经刷入或配置已恢复 |
| [attempt-1125/crop-done.png](attempt-1125/crop-done.png) | 安装器可见 `Installation complete!` | 设备身份或闪存哈希 |
| [attempt-1125/erase-or-next.png](attempt-1125/erase-or-next.png) | Erase device 未勾选 | 旧配置因此保留 |
| [attempt-1125/back-console.png](attempt-1125/back-console.png) | 交接后 open / online / healthy / valid，身份 `r60abd1 · 2D · mwcp-host` | 新鲜观测或本候选 profile |
| [attempt-1125/after-disconnect.png](attempt-1125/after-disconnect.png) | 断开后 closed / offline | 一次新的重连测试 |
| [本目录 report.md](report.md) | 早先查找结论，文首已指向后来的失败烧录 | 11:51 当时还没有烧录 |
| [原离线报告](../mwcp-firmware-20261105/report.md) | 构建、配置、not_run 的原始陈述；未修改 | 后来补上的烧录 |
| [artifact-summary.json](../mwcp-firmware-20261105/artifact-summary.json) | 构建时的 factory/OTA/manifest 哈希 | 设备运行身份 |
| `../mwcp-firmware-20261105/firmware/v0.0.0-local.20261105/r60abd1-ESP32-C3/` | 候选本体。2026-11-05 12:42 复算哈希仍一致，不复制二进制 | 已经写入设备的镜像 |
| `../mwcp-firmware-20261105/preview/` | 带“本地候选、未发布”的生产页。烧录使用 `127.0.0.1:8766` | 系统授权框本身 |
| [独立复核](../../../../../../docs/plans/mmwave-web-console/mwcp-firmware-review-2026-11-05.md) | 离线 138/138、浏览器 6/6、构建通过 | 短测完成 |
| `../wp3-core-evidence/hardware/` | 2026-11-03 COM9、身份 mwcp-host 的旧网页记录 | 本候选或本次烧录 |
| `../g2-hardware-report.md` | 更早的 G2 硬件材料 | 本次网页交接 |

`attempt-1125/` 里其余 PNG 是过程画面或裁剪，哈希和取舍只在该目录报告里。没有安装器下载日志，也没有闪存读回。分区与擦除依据仍是构建目录的 `flasher_args.json`、`partition_table/partition-table.bin`，以及 `static/node_modules/esp-web-tools/src/install-dialog.ts` 的 ASK_ERASE 模板；这些文件没有复制进本目录。
