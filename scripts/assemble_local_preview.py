#!/usr/bin/env python3
"""Copy the production page and point it at the local candidate.

This does not write static/public/releases.json, deploy Pages, or upload a
release. The copied page shows a banner and will not select the candidate
until someone chooses it and confirms it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "v0.0.0-local.20261105"
BANNER = (
    '<div style="background:#fef3c7;color:#78350f;padding:10px 16px;text-align:center;font:600 14px sans-serif">'
    "本地候选、未发布 · Local candidate, unpublished. Not an Alpha, Beta, or GitHub release."
    "</div>"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    summary = json.loads((evidence / "artifact-summary.json").read_text(encoding="utf-8"))
    if summary["version"] != VERSION:
        raise SystemExit("error: artifact version is not the local candidate")
    dist = args.dist.resolve()
    index = dist / "index.html"
    if not index.is_file():
        raise SystemExit("error: production build is missing; run npm run build in static/")
    public_index = ROOT / "static/public/releases.json"
    if json.loads(public_index.read_text(encoding="utf-8")) != {"schemaVersion": 1, "releases": []}:
        raise SystemExit("error: public release index is no longer empty")
    site = evidence / "preview"
    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(dist, site)
    firmware_src = evidence / "firmware" / VERSION / "r60abd1-ESP32-C3"
    firmware_dest = site / "firmware" / VERSION / "r60abd1-ESP32-C3"
    firmware_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(firmware_src, firmware_dest)
    manifest = firmware_dest / "manifest.json"
    manifest_hash = sha256(manifest)
    if manifest_hash != summary["manifestSha256"]:
        raise SystemExit("error: manifest hash does not match the build summary")
    if sha256(firmware_dest / "r60abd1.factory.bin") != summary["factorySha256"]:
        raise SystemExit("error: factory hash does not match the build summary")
    if sha256(firmware_dest / "r60abd1.ota.bin") != summary["otaSha256"]:
        raise SystemExit("error: ota hash does not match the build summary")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if len(head) != 40:
        raise SystemExit("error: HEAD is not a commit")
    release = {
        "schemaVersion": 1,
        "releases": [{
            "id": VERSION,
            "version": VERSION,
            "binaryVersion": VERSION,
            "channel": "local",
            "sourceCommit": head,
            "publishedAt": "2026-11-05T01:25:00Z",
            "firmware": [{
                "radarId": "r60abd1",
                "chipFamily": "ESP32-C3",
                "boardIds": ["esp32-c3-supermini"],
                "manifest": f"firmware/{VERSION}/r60abd1-ESP32-C3/manifest.json",
                "manifestSha256": manifest_hash,
            }],
        }],
    }
    (site / "releases.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    html = index.read_text(encoding="utf-8")
    if "<body>" not in html:
        raise SystemExit("error: production page has no body tag to mark")
    (site / "index.html").write_text(html.replace("<body>", "<body>" + BANNER, 1), encoding="utf-8")
    if json.loads(public_index.read_text(encoding="utf-8"))["releases"]:
        raise SystemExit("error: assembling the preview changed the public index")
    print(f"preview ready: {site}")
    print(f"sourceCommit is HEAD only: {head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
