# 在线烧录页面维护

[English](./FLASHER.md)

页面面向个人 DIY，只覆盖 **mmwave-component + mmwave-card**。源码位于 `static/`，使用 React + Tailwind，分为雷达选型、主控接线、固件烧录、HA/卡片配置四阶段。旧 `#/technology` 链接回到 DIY 入口。

## 本地验证

```sh
python -m unittest discover -s tests -p test_releases.py -v
python scripts/releases.py catalog
cd static
npm ci
npm test
npm run build
npm run dev
```

仓库内 `static/public/releases.json` 故意保持空列表。本地开发不会偷偷使用旧 dev 固件或虚构版本；正式索引由已发布的 GitHub Release 产物生成。测试用假固件绝不能连接真机烧录。

要复验浏览器的版本分组和异常处理，构建后在 `static/` 运行 `python test/serve-fixtures.py`，打开 `http://127.0.0.1:5175/mmwave-component/?scenario=mixed`。场景为 `mixed`（Beta 默认 + Alpha 确认）、`alpha`（不自动选择）、`corrupt`（校验失败）、`error`（索引失败）和 `empty`。该服务只监听本机，显示 QA 横幅，故意不提供任何可烧录二进制；不要连接硬件。它同时覆盖 GitHub Pages 子路径资源解析。

## 设备目录

`static/device-catalog.json` 是上架清单，不是全部开发型号。只允许 README 中的 **Completed**；目录校验同时检查状态、factory YAML 和 TX21/RX20。新增型号必须先由人工验收，再补齐 1D/2D 分类、供电/引脚证据、卡片说明和图片（或明确占位图）。

首批只有 R60ABD1。Super Mini 图仅对应仓库参考布局，不代表所有同名板；用户必须核对实物丝印，YAML board 名也不能证明实物板型。R60ABD1 供电为 5V（手册第 3–4 页：4.9–6V，供电能力至少 200mA）；UART 仅写 TTL，没有明确数值电平，须另行确认与 3.3V 主控兼容。

## 发布 Alpha

GitHub Actions 中在 `main` 手动运行 **Publish**：

1. channel 选 `alpha`，填写新版本，例如 `v1.2.0-alpha.1`。
2. 填写精确 ESPHome 版本，例如 `2026.9.0`；禁止 `latest`。实际发布应选择已完成 CI/硬件验证的版本。
3. 工作流只构建上架的 Completed 型号，编译前写入 Alpha 版本，必须同时有 factory 和 OTA 产物。
4. 发布 prerelease，永久附件为 `release.json` 和 `firmware-bundle.zip`。ZIP、各文件和网页 manifest 都有 SHA-256 校验；Actions 临时 artifact 仅用于构建过程，不承担版本存储。

按维护者节奏手动发布（约半月一次），日常提交只运行 CI。版本号必须唯一，不覆盖附件；中断产生的残缺草稿由维护者正常处理后重试，网页部署会拒绝残缺版本。

构建目录与发布路径不同：[build-action v7 的入口实现](https://github.com/esphome/build-action/blob/v7/entrypoint.py) 使用小写 variant，产物目录为 `r60abd1-esp32c3`，下载后也可能套一层 `firmware-` 前缀。打包器兼容这些布局和旧 `r60abd1-ESP32-C3` 布局，统一对外目录为 `r60abd1-ESP32-C3/`，但不改动 manifest 内的二进制文件名。factory 和 OTA 声明的 MD5/SHA-256 必须匹配实际文件；存在多个候选 manifest 时拒绝猜测。

## 晋升 Beta

先对 Alpha 完成同型号真机验收：供电和接线、USB 烧录、Wi-Fi、HA 实体、卡片安装、安装/方向校准、实时走动验证、重启持久化，记录硬件和结果。

再运行 **Publish**：channel=`beta`，新版本如 `v1.2.0-beta.1`，source_alpha=`v1.2.0-alpha.1`，勾选 hardware_tested，填写 test_evidence。主/次/补丁版本必须一致。

Beta **不重新构建**，沿用被测试 Alpha 的完整 ZIP、二进制及 manifest。Beta 是已验收发布标记；**设备和 OTA manifest 仍报告原 Alpha 二进制版本**，页面分别显示两者。这样不会因 manifest 宣称了设备里不存在的版本，导致反复提示 OTA 更新。

网页构建通过不等于真机验收通过，此流程也不提供医疗或安全认证。

## 网页部署与旧 OTA 迁移

**Publish GitHub Pages** 独立构建网页，读取已发布 Release 附件，完整校验后生成：

- `releases.json`：明确 Alpha/Beta 的版本历史与兼容条件，dev/nightly 不混入。
- `firmware/<tag>/<model>-ESP32-C3/`：按版本固定的固件。
- `<model>-ESP32-C3/manifest.json`：已部署设备使用的旧 OTA 地址，只由最新 Beta 更新；Alpha 不推进稳定地址。
- `models.json`：仅作为旧 OTA 地址清单，不再作为网页固件选择数据。

部署前从现有 GitHub Pages URL 读取 models.json 和其引用的固件，保留未分类旧版本以及未上架型号的旧 OTA 地址，但不向新用户提供这些版本。索引返回 404 按新站点处理；其他网络、路径、manifest 或产物问题会使部署失败，不替换当前网站。若已迁移 Pages 基地址，首次部署前修改组装参数。迁移前备份在线 OTA 路径，部署后逐一核验。

回滚时不要偷偷改写固定 tag。由维护者撤下错误发布版本并重新部署页面，检查稳定 OTA 地址和旧设备行为；设备擦除或降级属于另外的明确硬件操作。

## 比较表依据（核对日期 2026-10-12）

基线是官方组件及示例配置，不是 ESPHome 任意自定义代码的能力：

- 存在、距离和参数调节：[官方 LD2410](https://esphome.io/components/sensor/ld2410/)，本地 `components/ld2410/` 和共享 YAML。
- 平面位置、原生矩形区域：[官方 LD2450](https://esphome.io/components/sensor/ld2450/)，本地 `components/ld2450/`。官方已有原生区域能力，不能误标“不支持”。
- 安装变换、房间多边形：本地 `components/r60abd1/r60abd1_transform.h`、`r60abd1.cpp` 及其他型号共享配置；这是相对上述官方示例的项目增强。1D 使用距离门限，不提供平面多边形。
- 交互式校准与实时图来自 [MMWave Card](https://github.com/zomco/mmwave-card)，不是雷达硬件自带能力。官方实体卡片示例不等于这一房间校准界面。

表格只写简短支持情况，具体型号差异在选型说明展示。卡片应绑定 **cm 单位的雷达局部原始坐标**，绑定 room 坐标会二次变换。

## 图片来源与限制

使用内置图像工具，保留生成器原始 1254×1254 RGBA，不宣称是 1024；CSS 缩放不改变归一化引脚坐标。

- `device-artwork/esp32-c3-supermini.png`：参考概念图。依据仓库 front/back/pinout 和说明书第 2–3 页；无同板实物照片，制造修订号未知。彩色标注仅适用于这个参考布局。
- `device-artwork/radar-placeholder.png`：通用占位图，**不是 R60ABD1 天线面图**。手册第 5 页与现有 JPG 不足以核实天线正视面。

完整图片提示词、来源和验收材料位于开发工作区 `docs/prompts/mmwave-*-artwork.md` 与 `docs/reviews/evidence/web-flasher-artwork/`。
