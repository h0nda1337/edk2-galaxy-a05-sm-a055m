"""Extract boot images from a local Samsung AP tar or firmware ZIP for analysis."""

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

PARTITIONS = ("boot", "vendor_boot", "dtbo", "recovery", "vbmeta", "vbmeta_system", "init_boot")
MAX_ENTRY_SIZE = 512 * 1024 * 1024
MAGIC = {
    "boot": b"ANDROID!", "vendor_boot": b"VNDRBOOT", "dtbo": b"\xd7\xb7\xab\x1e",
    "recovery": b"ANDROID!", "init_boot": b"ANDROID!",
    "vbmeta": b"AVB0", "vbmeta_system": b"AVB0",
}


@contextmanager
def open_ap(path):
    if not zipfile.is_zipfile(path):
        with path.open("rb") as stream:
            yield stream
        return

    with zipfile.ZipFile(path) as archive:
        candidates = [
            item for item in archive.infolist()
            if PurePosixPath(item.filename).name.startswith("AP_")
            and item.filename.endswith((".tar.md5", ".tar"))
        ]
        if len(candidates) != 1:
            raise ValueError("Expected a single AP tar in the firmware ZIP.")
        with archive.open(candidates[0]) as stream:
            yield stream


def extract_images(package, destination):
    names = {f"{partition}.img": partition for partition in PARTITIONS}
    names.update({f"{partition}.img.lz4": partition for partition in PARTITIONS})
    if destination.exists():
        raise FileExistsError(destination)
    results = {}
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        stage = Path(staging) / "images"
        stage.mkdir()
        with open_ap(package) as stream, tarfile.open(fileobj=stream, mode="r|") as archive:
            for entry in archive:
                basename = PurePosixPath(entry.name).name
                partition = names.get(basename)
                if partition is None:
                    continue
                if partition in results or not entry.isfile() or not 0 < entry.size <= MAX_ENTRY_SIZE:
                    raise ValueError(f"Invalid or duplicate entry: {entry.name}")
                image = stage / f"{partition}.img"
                source = stage / basename
                with archive.extractfile(entry) as reader, source.open("xb") as writer:
                    shutil.copyfileobj(reader, writer)
                if basename.endswith(".lz4"):
                    subprocess.run(["lz4", "-q", "-d", source, image], check=True)
                    source.unlink()
                with image.open("rb") as reader:
                    magic = MAGIC[partition]
                    if reader.read(len(magic)) != magic:
                        raise ValueError(f"Unexpected magic for {partition}")
                    reader.seek(0)
                    digest = hashlib.file_digest(reader, "sha256").hexdigest()
                results[partition] = {"file": image.name, "bytes": image.stat().st_size, "sha256": digest}
        if "boot" not in results or "vendor_boot" not in results or "dtbo" not in results:
            raise ValueError("The AP tar must contain boot, vendor_boot and dtbo images.")
        (stage / "manifest.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        stage.rename(destination)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="AP_*.tar.md5 or ZIP containing a single AP tar")
    parser.add_argument("destination", type=Path, help="New directory for the extracted images")
    args = parser.parse_args()
    result = extract_images(args.package.resolve(strict=True), args.destination.resolve())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
