# MWCP/1 实现草案

状态：**草案，未冻结。** 这是 WP-1 供评审的契约草案，不取代 [设计历史](../../../../docs/plans/mmwave-web-console/protocol-v1.md)，也不授权开始 WP-2 或 WP-3。

[English](README.md)

机器 schema 在 [schema/mwcp-v1.schema.json](schema/mwcp-v1.schema.json)。黄金线字节仍以设计文件 `docs/plans/mmwave-web-console/protocol-vectors.json` 为准。不得为了迁就实现去改这些字节。

R60 描述在 [fixtures/r60abd1-capabilities.json](fixtures/r60abd1-capabilities.json)。不支持或未知的字段不杜撰。模拟器输出的 `origin` 为 `simulation`。

主机代码：

- JavaScript codec、客户端和模拟器：`static/src/protocol/`
- C++14 codec：`protocol/cpp/`
- 仍待评审的差异：[design-differences_CN.md](design-differences_CN.md)
