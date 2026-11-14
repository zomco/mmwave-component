# Firmware releases

This repository owns ESPHome components, MWCP firmware and published firmware bundles. The website and Web Serial console are maintained in [mmwave-flasher](https://github.com/zomco/mmwave-flasher).

`release-targets.json` is the firmware build inventory. `python scripts/releases.py catalog` validates Completed status against README, factory YAML and ESP32-C3 TX21/RX20. It does not read a website checkout. Only accepted models are released.

Run the **Publish** workflow explicitly on main with a version `vX.Y.Z-alpha.N` or `vX.Y.Z-beta.N`. Alpha requires an explicit ESPHome version and builds the accepted targets. Beta promotes a published and hardware-tested Alpha bundle with evidence; it does not rebuild bytes. Daily commits do not publish firmware.

Permanent assets are `release.json` and `firmware-bundle.zip`. Keep their schema, checksums, per-model paths and binary identity compatible. Beta may retain the tested Alpha binary version. Packaging/promotion validation is in scripts/releases.py; run `python -m unittest discover -s tests -p test_releases.py -v`.

After a release succeeds, separately trigger **Publish GitHub Pages in mmwave-flasher** to refresh available versions. There is no Pages workflow in this repository. Website-only updates must not compile or republish firmware. See the [Pages operation guide](https://github.com/zomco/mmwave-flasher/blob/main/docs/PUBLISHING.md) for deployment approval and domain cutover.
