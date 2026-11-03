# G2 tools after core acceptance

Current stage: [WP-3 may proceed](../../docs/reviews/web-console/current-stage.md). These are tooling and regression sources, not a requirement to rerun every historical hardware campaign.

For offline session/save regressions, call the `test_*` functions in `session_keeper_test.py`, and run `session_commit_guard_test.py NEW_OUTPUT_DIR` and `session_status_confirm_test.py ANOTHER_NEW_OUTPUT_DIR`. Do not call the keeper test's historical main when protecting old trace outputs. Use a new output directory for every run.

`mwcp.Client` and `SessionFlow` use real framing with injectable byte transport and clock. Browser WP-3 should reuse its JavaScript ProtocolClient; these Python tools provide behavior references, not an alternative browser implementation.

Files named `rN_*test.py` are active regression sources and may import each other. They are intentionally retained. Hardware collectors/runners are opt-in and may interact with USB, Wi-Fi or HA; reading this README does not authorize running them. Raw evidence and transient build outputs do not belong in this source directory.
