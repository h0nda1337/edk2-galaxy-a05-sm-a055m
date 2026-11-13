"""Split concatenated flattened trees from the DTB section of a vendor boot image."""

import argparse
import hashlib
import json
from pathlib import Path
import struct

FDT_MAGIC = 0xD00DFEED
FDT_HEADER_SIZE = 40


def split_dtb_section(data):
    offset = 0
    while offset < len(data):
        if data[offset] == 0:
            # Some vendor bundles align each tree with zero padding.
            offset += 1
            continue
        if len(data) - offset < FDT_HEADER_SIZE:
            raise ValueError(f"Truncated FDT header at {offset:#x}")
        magic, size, struct_offset, strings_offset, reserve_offset, version, compatible, _, strings_size, struct_size = (
            struct.unpack_from(">10I", data, offset)
        )
        if magic != FDT_MAGIC:
            raise ValueError(f"Unexpected FDT magic at {offset:#x}")
        if not FDT_HEADER_SIZE <= size <= len(data) - offset:
            raise ValueError(f"Invalid FDT length at {offset:#x}")
        if version < 17 or compatible > 17:
            raise ValueError(f"Unsupported FDT version at {offset:#x}")
        if reserve_offset % 8 or not FDT_HEADER_SIZE <= reserve_offset <= size - 16:
            raise ValueError(f"Invalid FDT reserve map at {offset:#x}")
        if (struct_offset % 4 or not FDT_HEADER_SIZE <= struct_offset <= size - struct_size
                or not FDT_HEADER_SIZE <= strings_offset <= size - strings_size):
            raise ValueError(f"Invalid FDT section bounds at {offset:#x}")
        yield offset, data[offset:offset + size]
        offset += size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("section", type=Path, help="DTB section extracted by AOSP unpack_bootimg.py")
    parser.add_argument("destination", type=Path, help="New directory for the individual trees")
    args = parser.parse_args()
    trees = list(split_dtb_section(args.section.read_bytes()))
    if not trees:
        parser.error("The DTB section contains no trees.")
    args.destination.mkdir()
    manifest = []
    for index, (offset, tree) in enumerate(trees):
        path = args.destination / f"board-{index:03}.dtb"
        with path.open("xb") as stream:
            stream.write(tree)
        manifest.append({"file": path.name, "offset": offset, "bytes": len(tree),
                         "sha256": hashlib.sha256(tree).hexdigest()})
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
