# Web Console current stage — WP-3 starts

Updated 2026-11-03. WP-2/G2 core acceptance is complete (independent r29 review; R28-01 closed). Firmware/protocol/tooling baseline: `194524d`. Development may proceed to WP-3. This is not a claim that every hardware test passed or that a release is approved.

The maintainer has explicitly adopted core-function acceptance. Blocking issues are broken core user paths, configuration/data corruption or false success, privacy failures, and competing serial owners. Optional capabilities, exhaustive matrices and long endurance runs may be deferred with documented impact; they must not hold up all development. Old reports and their P0/P1 labels are historical, not instructions to restart G2.

The current work package and detailed policy live in the enclosing workspace at `docs/plans/mmwave-web-console/`: `current-status.md`, `development-policy.md`, `wp2-g2-lessons.md`, and `wp3-execution-prompt.md`. If working from this repository alone, obtain that handoff rather than treating old review prompts as new requirements.

Pending handoff: the presence query change is still a source candidate requiring a target build and short observation in G3. Show unknown until confirmed; do not infer absence from coordinates. WP-3 should implement the existing React/Tailwind console, safe serial ownership, capability-driven observations, drafts/save/recovery, and bounded diagnostics. A short designated-device check is distinct from software acceptance. Two-hour soaks, 50 unplug cycles, 20 power cuts and exhaustive HA/browser matrices are deferred, not silently marked pass.

Pre-commit validation: unit/contract tests 107/107; production C++ integration rerun after formatting passed; Vite build passed; changed component C++ files pass clang-format 22.1.8. A diagnostic-only ESP-IDF include was guarded by its actual feature macro to restore desktop compilation. No new target firmware build, hardware run or exhaustive browser matrix was claimed during commit preparation.

## History and evidence

Six accumulated phase/review reports are preserved byte-for-byte under `archive/wp2-g2/`, with original paths and SHA-256 in its manifest. Original report paths now redirect here and to their snapshots. The G0/G2 evidence indexes and G2 RUN files remain at their original locations for reference; their old gate conclusions do not override this current stage.

The workspace archive contains the independent review chain, including r29, plus a source-path manifest and a local-only ZIP of raw/synthetic evidence. The ZIP is not in Git; copying the repository alone does not copy that evidence. Original source logs remain in place. Do not run historical scripts merely to read a report; some have fixed output paths or touch hardware.

Historic report links resolve relative to their original directory. To reconstruct a snapshot, copy it to its `manifest.original` path in a separate checkout, verify the hash, and use the associated source commit/evidence. Do not overwrite current reports or reinterpret old firmware hashes as the current image.
