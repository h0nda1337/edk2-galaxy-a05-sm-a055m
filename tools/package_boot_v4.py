"""Package a gzip-compressed AARCH64 firmware in the A05 stock boot v4 layout."""

import argparse
import gzip
import hashlib
from pathlib import Path
import struct

PAGE = 4096
AARCH64_IMAGE_MAGIC = b"ARM\x64"
BOOT_MAGIC = b"ANDROID!"
HEADER_SIZE = 1584


def build_image(stock, firmware):
    if len(stock) < PAGE or stock[:8] != BOOT_MAGIC:
        raise ValueError("Expected a stock Android boot image.")
    kernel_size, ramdisk_size, _, header_size = struct.unpack_from("<4I", stock, 8)
    version, = struct.unpack_from("<I", stock, 40)
    signature_size, = struct.unpack_from("<I", stock, 1580)
    if (version, header_size, ramdisk_size, signature_size) != (4, HEADER_SIZE, 0, 0):
        raise ValueError("Expected SM-A055M boot v4 with empty ramdisk and signature fields.")
    if not 64 <= kernel_size <= len(stock) - PAGE or stock[PAGE:PAGE + 2] != b"\x1f\x8b":
        raise ValueError("Expected a gzip kernel in the stock boot image.")
    if len(firmware) < 64 or firmware[56:60] != AARCH64_IMAGE_MAGIC:
        raise ValueError("Firmware must have a Linux AARCH64 Image header.")
    offset, image_size, flags = struct.unpack_from("<3Q", firmware, 8)
    if offset not in (0, 0x80000) or image_size != len(firmware) or flags & 1:
        raise ValueError("Unexpected AARCH64 firmware placement, length or endianness.")

    payload = gzip.compress(firmware, compresslevel=9, mtime=0)
    header = bytearray(stock[:PAGE])
    struct.pack_into("<I", header, 8, len(payload))
    image = header + payload + bytes((-len(payload)) % PAGE)
    if len(image) > len(stock):
        raise ValueError("The result exceeds the size of the stock boot image.")
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-boot", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    image = build_image(args.stock_boot.read_bytes(), args.firmware.read_bytes())
    with args.output.open("xb") as file:
        file.write(image)
    print(f"Unsigned boot v4 image, {len(image)} bytes, SHA-256 {hashlib.sha256(image).hexdigest()}")


if __name__ == "__main__":
    main()
