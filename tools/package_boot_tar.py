"""Put one Galaxy A05 Android boot v4 image in an Odin AP tar."""

import argparse
import hashlib
import io
from pathlib import Path
import struct
import tarfile

from package_boot_v4 import BOOT_MAGIC, HEADER_SIZE, PAGE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.suffix.lower() != ".tar":
        parser.error("--output must end in .tar")
    image = args.boot.read_bytes()
    if len(image) < PAGE or image[:8] != BOOT_MAGIC:
        parser.error("--boot is not an Android boot image")
    kernel_size, ramdisk_size, _, header_size = struct.unpack_from("<4I", image, 8)
    version, = struct.unpack_from("<I", image, 40)
    signature_size, = struct.unpack_from("<I", image, 1580)
    if (
        (version, header_size, ramdisk_size, signature_size) != (4, HEADER_SIZE, 0, 0)
        or not 64 <= kernel_size <= len(image) - PAGE
        or image[PAGE:PAGE + 2] != b"\x1f\x8b"
    ):
        parser.error("--boot must match the SM-A055M boot v4 layout with a gzip kernel")

    member = tarfile.TarInfo("boot.img")
    member.size = len(image)
    with tarfile.open(args.output, "x", format=tarfile.USTAR_FORMAT) as archive:
        archive.addfile(member, io.BytesIO(image))
    print(f"{args.output}: boot.img, {len(image)} bytes, SHA-256 {hashlib.sha256(image).hexdigest()}")


if __name__ == "__main__":
    main()
