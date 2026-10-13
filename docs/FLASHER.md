# Web installer maintenance

[中文](./FLASHER_CN.md)

The personal DIY installer covers **mmwave-component + mmwave-card** only. It is React + Tailwind, built from `static/`. The four stages are radar, board/wiring, firmware, and HA/card setup. `#/technology` redirects to the DIY entry.

## Local checks

```sh
python -m unittest discover -s tests -p test_releases.py -v
python scripts/releases.py catalog
cd static
npm ci
npm test
npm run build
npm run dev
```

The checked-in `static/public/releases.json` is deliberately empty. Local development does not silently use old `dev` artifacts or fictitious releases. The deployed index is generated from published, validated GitHub release assets. Never connect real hardware to synthetic test firmware.

## Hardware catalog

`static/device-catalog.json` is the curated storefront, not the whole development inventory. Only README **Completed** models may appear; `scripts/releases.py catalog` cross-checks README, factory YAML and TX21/RX20 wiring. Add a model only after human acceptance, with 1D/2D classification, verified power/pin evidence, card instructions and artwork (or a labeled placeholder).

Current entry: R60ABD1. ESP32-C3 Super Mini artwork depicts the repository reference layout, not every board sold under that name. Check the physical labels. The YAML board identifier is not proof of a particular physical board. R60ABD1 uses 5V (manual pp. 3–4: 4.9–6V, supply at least 200mA); its UART is specified as TTL, not an explicit numeric logic voltage. Verify logic-level compatibility separately.

## Publish Alpha

In GitHub Actions, run **Publish** on `main`:

1. Choose `alpha`, enter a new tag such as `v1.2.0-alpha.1`.
2. Set an exact ESPHome version, such as `2026.9.0`; floating `latest` is rejected. Select a version already validated by CI/hardware for the release.
3. The workflow builds only Completed catalog entries and requires both factory and OTA artifacts. It stamps the Alpha version before compilation.
4. It uploads permanent `release.json` and `firmware-bundle.zip` assets to a prerelease. SHA-256 covers the archive, each file and the web manifest. GitHub Actions artifacts are temporary build transport, not release storage.

Run when ready (roughly fortnightly); ordinary commits run CI, not firmware publishing. A tag must be new; the workflow does not overwrite assets. If an interrupted release is incomplete, repair or remove that draft through the maintainer's normal process before retrying. Pages rejects partial releases.

Build directories are not public URL names. The [build-action v7 entrypoint](https://github.com/esphome/build-action/blob/v7/entrypoint.py) emits a lower-case variant directory, e.g. `r60abd1-esp32c3`, optionally nested inside `firmware-r60abd1-esp32c3` after artifact download. The packager accepts these and legacy `r60abd1-ESP32-C3` layouts, normalizes the published directory to `r60abd1-ESP32-C3/`, and preserves binary filenames within the manifest. Declared factory/OTA MD5 and SHA-256 hashes must match the files; ambiguous duplicate manifests fail validation.

## Promote Beta

Test Alpha on the exact radar/board: supply and wiring, USB flash, Wi-Fi, HA entities, card installation, calibration, live walk-test, restart persistence. Record hardware and results.

Run **Publish** with `beta`, a new `v1.2.0-beta.1` tag, `source_alpha=v1.2.0-alpha.1`, `hardware_tested=true`, and nonempty `test_evidence`. Major/minor/patch must match. No rebuild occurs: the ZIP, binaries and manifest retain exactly the tested Alpha bytes. Beta is a tested release designation; **the device and OTA manifest continue reporting the Alpha binary version**. The page shows both values. This avoids endless OTA update prompts caused by advertising a version not embedded in the device.

Do not promote a version merely because the website builds. This workflow does not perform hardware acceptance or create a medical/safety certification.

## Pages and OTA migration

**Publish GitHub Pages** builds the site independently and enumerates published release assets, validating the complete bundle before staging:

- `releases.json`: explicit Alpha/Beta history and compatibility metadata; no nightly/dev masquerading as Beta.
- `firmware/<tag>/<model>-ESP32-C3/`: immutable versioned files.
- `<model>-ESP32-C3/manifest.json`: existing device OTA alias; only the newest published Beta replaces it. Alpha never advances the stable alias.
- `models.json`: legacy OTA alias inventory only, no longer the frontend's selectable firmware list.

Before deployment, the workflow downloads existing `models.json` and its referenced firmware from the current GitHub Pages URL. This preserves unclassified legacy firmware, including non-storefront models, without listing it for new DIY users. An absent index (HTTP 404) is treated as a new site; other network, path, manifest or artifact errors fail deployment, leaving the current site untouched. If Pages has been moved to a different base URL, update the assembly input before the first deployment. Take a backup of the live OTA paths before migration and verify them after deployment.

To roll back a release, do not silently mutate an immutable tag. Remove the bad release from publication under maintainer control, redeploy Pages, and check the stable alias and older device behavior. Erasing or downgrading devices is a separate, explicit hardware action.

## Comparison evidence (checked 2026-10-12)

The table compares official components/examples, not all possible custom ESPHome code:

- Presence/distance and tuning entities: [official LD2410](https://esphome.io/components/sensor/ld2410/), local `components/ld2410/` and `tests/common/ld2410.yaml`.
- Position and native rectangular zones: [official LD2450](https://esphome.io/components/sensor/ld2450/), local `components/ld2450/`. Both support model-specific native zones; do not label official ESPHome as lacking them.
- Installation transforms and room polygon filtering: `components/r60abd1/r60abd1_transform.h`, `components/r60abd1/r60abd1.cpp` and other model cores. These are project enhancements beyond those official example configurations. Range-only models use distance gates, not planar polygons.
- Interactive calibration/live UI comes from [MMWave Card](https://github.com/zomco/mmwave-card), not the radar hardware itself. Official example entity cards are not equivalent to this room-calibration UI.

Keep the table concise. Detailed per-model capabilities belong to the selected model guide, not a model column. The card expects **local raw coordinates in cm**; binding already-transformed room coordinates applies the transform twice.

## Asset provenance

For browser regression checks, build the app, run `python test/serve-fixtures.py` from `static/`, and open `http://127.0.0.1:5175/mmwave-component/?scenario=mixed`. Scenarios: `mixed`, `alpha`, `corrupt`, `error`, `empty`. The loopback-only QA server displays a warning and deliberately serves no flashable binaries. Never connect hardware. This also exercises deployment under a GitHub Pages subpath.

The accepted images were generated with the built-in image tool from repository references. Original outputs are 1254×1254 RGBA; CSS scales them without changing pin coordinates. No native-resolution claim of 1024×1024 is made.

- `device-artwork/esp32-c3-supermini.png`: concept/reference layout; source `static/esp32c3/front.png`, `back.png`, `pinout.png`, datasheet pp. 2–3. No same-board physical photo or manufacturing revision is established. Colored pins apply only to this reference layout.
- `device-artwork/radar-placeholder.png`: generic placeholder, **not R60ABD1 antenna-face artwork**. The manual p. 5 and available JPGs do not establish a verified frontal antenna view.

Full prompts and acceptance evidence are maintained in the development workspace under `docs/prompts/mmwave-*-artwork.md` and `docs/reviews/evidence/web-flasher-artwork/`.
