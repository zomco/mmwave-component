# MWCP 集成验收材料与提交范围

整理日期：2026-11-05。

本目录和相邻 `mwcp-firmware-hw-20261105`、`mwcp-firmware-r2-01-20261105` 保留候选构建、失败安装及整改后短真机的关键证据。历史报告保留原貌；当前结论以工作区 `docs/plans/mmwave-web-console/current-status.md` 和 `mwcp-firmware-review-2026-11-05-r3.md` 为准：基本功能通过，R2-01 关闭，发布未批准。

R2-01 现场报告推断的“输入框卸载”未被独立复核证实；现场脚本的 `input[type=text]` 未匹配没有显式 type 属性的输入框。独立实际 UI 测试已验证读取完成后的编辑、保存、重连。不要依据历史推断直接修改表单。

## 可回溯材料

- 本目录的 report、artifact-summary、构建/配置日志及 compiled.factory.yaml 为原始构建记录。compiled.factory.yaml 的相对 include 以原构建目录解释，不应在归档目录直接执行。
- `firmware/` 保留原 factory、OTA、manifest，哈希见 artifact-summary。这是本地测试候选，并非正式发布；安装器回归直接读取其中 factory 和 manifest，因此必须随代码保留。
- 相邻硬件目录保留 report/index、报告引用的关键截图和试写/重启/恢复 JSON。失败尝试不改写成成功。
- 源码基线仍是报告中的 f5470c9 加当时工作树差异。归档提交不会改变已经编译的固件身份。

## 不提交的本地材料

`preview/`、`site/` 是生成站点；`chrome-profile/` 是浏览器个人数据；未被报告引用的操作截图、坐标点击脚本及临时表达式不进入本次提交，仍留在本机。它们不作为可移植回归的依赖。

重新构建/组装请使用 `scripts/build_r60_candidate.py`、`scripts/assemble_local_preview.py` 的实际命令行帮助和 report 中的参数。新运行输出到新目录，不覆盖原始材料。重新构建不会重现既有真机证据，不能替代新的硬件授权或发布批准。
