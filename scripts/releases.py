"""Versioned firmware bundles, Alpha promotion and Pages assembly (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"^v?\d+\.\d+\.\d+-(alpha|beta)\.\d+$")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        raise ValueError(f"Unsafe asset path: {value!r}")
    if value.startswith("/") or any(part in ("..", ".", "") for part in value.split("/")):
        raise ValueError(f"Unsafe asset path: {value!r}")
    return value


def channel(version):
    match = VERSION.fullmatch(version)
    if not match:
        raise ValueError("Use vX.Y.Z-alpha.N or vX.Y.Z-beta.N")
    return match[1]


def catalog(root=ROOT):
    data = read(root / "static/device-catalog.json")
    status = (root / "README.md").read_text(encoding="utf-8")
    models = []
    for radar in data["radars"]:
        if radar["status"] != "Completed":
            continue
        row = rf"(?mi)^\|\s*{re.escape(radar['name'])}\s*\|[^\n]*\|\s*Completed\s*\|\s*$"
        if not re.search(row, status):
            raise ValueError(f"{radar['name']} is not Completed in README.md")
        if radar["dimension"] not in ("1D", "2D") or radar["chipFamily"] != "ESP32-C3":
            raise ValueError("Unsupported dimension or chip")
        config = root / safe_path(radar["config"])
        if not config.is_file():
            raise ValueError(f"Missing configuration: {config}")
        core = (root / f"tests/common/{radar['id']}.yaml").read_text(encoding="utf-8")
        if not re.search(r"(?m)^\s+tx_pin:\s+GPIO21\b", core) or not re.search(r"(?m)^\s+rx_pin:\s+GPIO20\b", core):
            raise ValueError("ESP32-C3 UART must be TX21/RX20")
        models.append(radar)
    if not models:
        raise ValueError("No Completed models")
    for board in data["boards"]:
        if board["chipFamily"] != "ESP32-C3" or board["uart"] != {"tx": 21, "rx": 20}:
            raise ValueError("Invalid board UART/chip")
    return models, data["boards"]


def stamp(config, version):
    if channel(version) != "alpha":
        raise ValueError("Only Alpha builds; Beta promotes tested bytes")
    path = ROOT / safe_path(config)
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(r'(?m)^(\s*version:\s*)[\"\']?dev[\"\']?(\s*(?:#.*)?)$', lambda m: f'{m[1]}"{version}"{m[2]}', text)
    if count != 1:
        raise ValueError("Expected exactly one version: dev placeholder")
    path.write_text(text, encoding="utf-8")


def metadata(version, commit, esphome):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("A full source commit is required")
    return {"schemaVersion": 1, "id": version, "version": version, "channel": channel(version),
            "binaryVersion": version, "sourceCommit": commit, "esphomeVersion": esphome,
            "publishedAt": datetime.now(timezone.utc).isoformat(), "firmware": [], "files": {}}


def referenced_files(manifest):
    files = set()
    for build in manifest.get("builds", []):
        for part in build.get("parts", []):
            if not isinstance(part.get("offset"), int) or part["offset"] < 0:
                raise ValueError("Invalid flash offset")
            files.add(safe_path(part["path"]))
        ota = build.get("ota")
        if ota:
            files.add(safe_path(ota["path"]))
    return files


def checked_manifest_files(manifest, read_asset):
    """Check the hashes declared by build-action, not just our bundle hashes."""
    files = {name: read_asset(name) for name in referenced_files(manifest)}
    if not files or any(not data for data in files.values()):
        raise ValueError("Missing or empty firmware artifacts")
    for build in manifest.get("builds", []):
        entries = list(build.get("parts", []))
        if build.get("ota"):
            entries.append(build["ota"])
        for entry in entries:
            data = files[entry["path"]]
            for algorithm, length in (("md5", 32), ("sha256", 64)):
                if algorithm in entry:
                    expected = entry[algorithm]
                    if not isinstance(expected, str) or not re.fullmatch(rf"[a-f0-9]{{{length}}}", expected):
                        raise ValueError(f"Invalid {algorithm} checksum: {entry['path']}")
                    if hashlib.new(algorithm, data).hexdigest() != expected:
                        raise ValueError(f"{algorithm} checksum mismatch: {entry['path']}")
    return files


def find_build_manifest(build_dir, radar_id):
    # build-action v7 uses the lower-case variant (esp32c3), not chipFamily
    # (ESP32-C3). Accept both layouts, plus download-artifact's outer prefix.
    names = {f"{radar_id}-esp32c3", f"{radar_id}-esp32-c3"}
    candidates = [path for path in Path(build_dir).rglob("manifest.json")
                  if path.parent.name.lower().removeprefix("firmware-") in names]
    if len(candidates) != 1:
        raise ValueError(f"Expected one manifest for {radar_id}, found {candidates}")
    return candidates[0]


def package(build_dir, output, version, commit, esphome):
    if channel(version) != "alpha" or not re.fullmatch(r"\d+\.\d+\.\d+", esphome):
        raise ValueError("Alpha needs a pinned numeric ESPHome version")
    models, boards = catalog()
    meta = metadata(version, commit, esphome)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output / "firmware-bundle.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for radar in models:
            folder = f"{radar['id']}-ESP32-C3"
            manifest_path = find_build_manifest(build_dir, radar["id"])
            manifest = read(manifest_path)
            if manifest.get("version") != version or len(manifest.get("builds", [])) != 1 or manifest["builds"][0].get("chipFamily") != "ESP32-C3":
                raise ValueError("Build version/chip mismatch")
            if not manifest["builds"][0].get("parts") or not manifest["builds"][0].get("ota"):
                raise ValueError("Both factory and OTA artifacts are required")
            files = checked_manifest_files(manifest, lambda rel: (manifest_path.parent / rel).read_bytes())
            files["manifest.json"] = manifest_path.read_bytes()
            for rel, content in sorted(files.items()):
                key = f"{folder}/{rel}"
                meta["files"][key] = sha(content)
                bundle.writestr(key, content)
            meta["firmware"].append({"radarId": radar["id"], "chipFamily": "ESP32-C3",
                "boardIds": [b["id"] for b in boards if b["chipFamily"] == radar["chipFamily"]],
                "manifest": f"firmware/{version}/{folder}/manifest.json",
                "manifestSha256": meta["files"][f"{folder}/manifest.json"]})
    meta["bundleSha256"] = sha((output / "firmware-bundle.zip").read_bytes())
    write(output / "release.json", meta)
    validate_bundle(meta, output / "firmware-bundle.zip")


def validate_bundle(meta, bundle_path):
    if meta.get("schemaVersion") != 1 or channel(meta["version"]) != meta["channel"] or meta["id"] != meta["version"]:
        raise ValueError("Invalid release metadata")
    if not re.fullmatch(r"[a-f0-9]{40}", meta["sourceCommit"]):
        raise ValueError("Invalid source commit")
    if channel(meta["binaryVersion"]) != "alpha":
        raise ValueError("Only Alpha binaries may be built or promoted")
    if meta["channel"] == "alpha" and meta["binaryVersion"] != meta["version"]:
        raise ValueError("Alpha binary version mismatch")
    if meta["channel"] == "beta" and (meta.get("promotedFrom") != meta["binaryVersion"] or not meta.get("hardwareTestEvidence", "").strip()):
        raise ValueError("Beta requires a tested Alpha provenance")
    datetime.fromisoformat(meta["publishedAt"].replace("Z", "+00:00"))
    if sha(Path(bundle_path).read_bytes()) != meta["bundleSha256"]:
        raise ValueError("Bundle checksum mismatch")
    with zipfile.ZipFile(bundle_path) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)) or set(names) != set(meta["files"]):
            raise ValueError("Unexpected / duplicate bundle files")
        for name in names:
            safe_path(name)
            if sha(bundle.read(name)) != meta["files"][name]:
                raise ValueError(f"Checksum mismatch: {name}")
        if not meta["firmware"]:
            raise ValueError("Empty firmware release")
        seen = set()
        for target in meta["firmware"]:
            folder = f"{target['radarId']}-ESP32-C3"
            safe_path(folder)
            if target["radarId"] in seen or target["chipFamily"] != "ESP32-C3" or not target["boardIds"]:
                raise ValueError("Invalid firmware target")
            seen.add(target["radarId"])
            key = f"{folder}/manifest.json"
            if target["manifest"] != f"firmware/{meta['version']}/{key}" or target["manifestSha256"] != meta["files"][key]:
                raise ValueError("Manifest path/checksum mismatch")
            manifest = json.loads(bundle.read(key))
            if manifest["version"] != meta["binaryVersion"] or len(manifest.get("builds", [])) != 1 or manifest["builds"][0]["chipFamily"] != "ESP32-C3":
                raise ValueError("Manifest version/chip mismatch")
            if not manifest["builds"][0].get("parts") or not manifest["builds"][0].get("ota"):
                raise ValueError("Factory and OTA required")
            for rel in referenced_files(manifest):
                if f"{folder}/{rel}" not in names:
                    raise ValueError("Missing firmware part")
            checked_manifest_files(manifest, lambda rel: bundle.read(f"{folder}/{rel}"))
    return meta


def promote(source, output, version, evidence):
    source, output = Path(source), Path(output)
    meta = read(source / "release.json")
    validate_bundle(meta, source / "firmware-bundle.zip")
    if meta["channel"] != "alpha" or channel(version) != "beta" or not evidence.strip():
        raise ValueError("Beta requires a tested Alpha and hardware test evidence")
    if version.split("-beta.")[0] != meta["version"].split("-alpha.")[0]:
        raise ValueError("Promote within the same X.Y.Z version")
    old = meta["version"]
    meta.update(id=version, version=version, channel="beta", promotedFrom=old,
                hardwareTestEvidence=evidence, publishedAt=datetime.now(timezone.utc).isoformat())
    for target in meta["firmware"]:
        target["manifest"] = target["manifest"].replace(f"firmware/{old}/", f"firmware/{version}/", 1)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / "firmware-bundle.zip", output / "firmware-bundle.zip")
    write(output / "release.json", meta)
    validate_bundle(meta, output / "firmware-bundle.zip")


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True, encoding="utf-8")


def download_release(repo, tag, directory):
    if not VERSION.fullmatch(tag):
        raise ValueError("Invalid tag")
    Path(directory).mkdir(parents=True, exist_ok=True)
    gh("release", "download", tag, "--repo", repo, "--pattern", "release.json", "--pattern", "firmware-bundle.zip", "--dir", str(directory))
    meta = validate_bundle(read(Path(directory) / "release.json"), Path(directory) / "firmware-bundle.zip")
    if meta["version"] != tag:
        raise ValueError("Release tag mismatch")
    return meta


def preserve_legacy(base, output):
    """Retain existing OTA paths; never present unclassified firmware as Beta."""
    if not base:
        return
    if urlparse(base).scheme != "https":
        raise ValueError("Previous Pages URL must use HTTPS")
    base = base.rstrip("/") + "/"

    def fetch(path):
        url = urljoin(base, path)
        if not url.startswith(base):
            raise ValueError("Legacy path escaped Pages base")
        with urlopen(url, timeout=30) as response:
            return response.read()

    try:
        models = json.loads(fetch("models.json"))
    except HTTPError as error:
        if error.code == 404:
            return
        raise
    if not isinstance(models, list):
        raise ValueError("Invalid legacy models index")
    for model in models:
        path = safe_path(model["manifest"])
        manifest_bytes = fetch(path)
        manifest = json.loads(manifest_bytes)
        folder = str(PurePosixPath(path).parent)
        files = checked_manifest_files(manifest, lambda rel: fetch(f"{folder}/{rel}"))
        for rel, content in files.items():
            dest = Path(output) / folder / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        dest = Path(output) / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(manifest_bytes)
    write(Path(output) / "models.json", models)


def assemble(repo, output, previous):
    models, _ = catalog()
    eligible = {m["id"] for m in models}
    output = Path(output)
    preserve_legacy(previous, output)
    releases = []
    with tempfile.TemporaryDirectory() as temp:
        page = 1
        while True:
            batch = json.loads(gh("api", f"repos/{repo}/releases?per_page=100&page={page}"))
            for release in batch:
                if release["draft"]:
                    continue
                assets = {a["name"] for a in release["assets"]}
                if not ({"release.json", "firmware-bundle.zip"} & assets):
                    continue  # Older releases remain outside the new channel index.
                if not {"release.json", "firmware-bundle.zip"} <= assets:
                    raise ValueError("Incomplete release assets")
                tag = release["tag_name"]
                meta = download_release(repo, tag, Path(temp) / tag)
                meta["publishedAt"] = release["published_at"]
                with zipfile.ZipFile(Path(temp) / tag / "firmware-bundle.zip") as bundle:
                    bundle.extractall(output / "firmware" / tag)  # validated safe paths above
                meta["firmware"] = [f for f in meta["firmware"] if f["radarId"] in eligible]
                if meta["firmware"]:
                    releases.append(meta)
            if len(batch) < 100:
                break
            page += 1
    releases.sort(key=lambda r: (r["publishedAt"], r["version"]), reverse=True)
    assigned = set()
    for release in releases:
        if release["channel"] != "beta":
            continue
        for target in release["firmware"]:
            model = target["radarId"]
            if model in assigned:
                continue
            assigned.add(model)
            folder = f"{model}-ESP32-C3"
            shutil.copytree(output / "firmware" / release["version"] / folder, output / folder, dirs_exist_ok=True)
    # Keep a models.json inventory of ALL OTA aliases so later deploys can preserve them.
    legacy = read(output / "models.json") if (output / "models.json").exists() else []
    by_path = {m["manifest"]: m for m in legacy}
    for model in assigned:
        path = f"{model}-ESP32-C3/manifest.json"
        by_path[path] = {"id": f"{model}-ESP32-C3", "manifest": path}
    write(output / "models.json", list(by_path.values()))
    write(output / "releases.json", {"schemaVersion": 1, "releases": releases})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog")
    p = sub.add_parser("stamp"); p.add_argument("config"); p.add_argument("version")
    p = sub.add_parser("package")
    for name in ("build_dir", "output", "version", "commit", "esphome"):
        p.add_argument(name)
    p = sub.add_parser("promote")
    for name in ("source", "output", "version", "evidence"):
        p.add_argument(name)
    p = sub.add_parser("download")
    for name in ("repo", "tag", "directory"):
        p.add_argument(name)
    p = sub.add_parser("assemble")
    for name in ("repo", "output", "previous"):
        p.add_argument(name)
    args = vars(parser.parse_args()); command = args.pop("command")
    if command == "catalog":
        print(json.dumps([r["config"] for r in catalog()[0]]))
    else:
        {"stamp": stamp, "package": package, "promote": promote, "download": download_release, "assemble": assemble}[command](**args)


if __name__ == "__main__":
    main()
