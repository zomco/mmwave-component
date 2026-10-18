# MWCP/1 implementation draft

Status: **draft, not frozen.** This is the WP-1 contract draft for review. It does not replace [the design history](../../../../docs/plans/mmwave-web-console/protocol-v1.md) and it is not permission to start WP-2 or WP-3.

[中文](README_CN.md)

The machine schema is [schema/mwcp-v1.schema.json](schema/mwcp-v1.schema.json). Golden wire bytes remain the design file `docs/plans/mmwave-web-console/protocol-vectors.json`. Do not edit those bytes to match an implementation.

R60 descriptors are in [fixtures/r60abd1-capabilities.json](fixtures/r60abd1-capabilities.json). Unknown or unsupported fields are omitted rather than invented. `origin` of simulator output is `simulation`.

Host code:

- JavaScript codec, client, and simulator: `static/src/protocol/`
- C++14 codec: `protocol/cpp/`
- Differences still awaiting review: [design-differences.md](design-differences.md)
