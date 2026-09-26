#!/usr/bin/env python3
"""Download the EPFL edge-AI cough dataset and keep only the IMU and labels.

Source: Zenodo record 7562332, public_dataset.zip, CC-BY 4.0.
Orlandic et al., IEEE EMBC 2023, doi:10.1109/EMBC40787.2023.10340413.

The download is checked against the size and MD5 that Zenodo publishes for the
file. After extraction every file except imu.csv and ground_truth.json is
deleted: the audio is never used here. The data lives in data/external/epfl/,
which is gitignored. It is not re-hosted in this repository.
"""
from __future__ import annotations
import argparse, hashlib, json, shutil, sys, urllib.request, zipfile
from pathlib import Path

RECORD_API = "https://zenodo.org/api/records/7562332"
FILENAME = "public_dataset.zip"
KEEP = {"imu.csv", "ground_truth.json"}
CHUNK = 1 << 20


def zenodo_file_info() -> tuple[str, int, str]:
    with urllib.request.urlopen(RECORD_API, timeout=60) as r:
        record = json.load(r)
    for f in record["files"]:
        if f["key"] == FILENAME:
            algo, digest = f["checksum"].split(":", 1)
            assert algo == "md5", f["checksum"]
            return f["links"]["self"], int(f["size"]), digest
    raise RuntimeError(f"{FILENAME} not listed in {RECORD_API}")


def download(url: str, dest: Path, size: int, md5: str) -> None:
    part = dest.with_suffix(".part")
    h = hashlib.md5()
    done = 0
    with urllib.request.urlopen(url, timeout=60) as r, open(part, "wb") as out:
        while chunk := r.read(CHUNK):
            out.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if done % (100 * CHUNK) < CHUNK:
                print(f"  {done / 1e6:7.0f} / {size / 1e6:.0f} MB", flush=True)
    if done != size:
        raise RuntimeError(f"incomplete download: {done} of {size} bytes")
    if h.hexdigest() != md5:
        raise RuntimeError(f"MD5 mismatch: got {h.hexdigest()}, expected {md5}")
    part.rename(dest)


def tree_size(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/external/epfl", type=Path)
    ap.add_argument("--keep-zip", action="store_true", help="do not delete the ZIP afterwards")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    zip_path = args.out / FILENAME
    extract_dir = args.out / "extracted"

    url, size, md5 = zenodo_file_info()
    if zip_path.exists() and zip_path.stat().st_size == size:
        print(f"{zip_path} already present")
    else:
        print(f"downloading {url} ({size / 1e6:.0f} MB)")
        try:
            download(url, zip_path, size, md5)
        except Exception as e:  # one retry, then give up with the URL
            print(f"download failed: {e}; retrying once")
            download(url, zip_path, size, md5)
    print(f"verified: {size} bytes, md5 {md5}")

    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_dir)
    before = tree_size(extract_dir)

    removed: dict[str, int] = {}
    for p in sorted(extract_dir.rglob("*")):
        if p.is_file() and p.name not in KEEP:
            removed[p.suffix or p.name] = removed.get(p.suffix or p.name, 0) + 1
            p.unlink()
    for p in sorted(extract_dir.rglob("*"), key=lambda q: len(q.parts), reverse=True):
        if p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    after = tree_size(extract_dir)

    if not args.keep_zip:
        zip_path.unlink()
    print(f"extracted size {before / 1e6:.1f} MB, after removing non-IMU files {after / 1e6:.1f} MB")
    print(f"removed files by type: {removed}")
    print(f"data in {extract_dir}")


if __name__ == "__main__":
    sys.exit(main())
