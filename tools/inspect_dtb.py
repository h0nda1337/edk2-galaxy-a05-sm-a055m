"""Extract memory and boot hardware properties from a local, flattened DTB."""

import argparse
import json
import subprocess
import struct
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dtb", type=Path, help="One flattened device tree, with overlays applied if applicable.")
    args = parser.parse_args()
    dtb = args.dtb.resolve(strict=True)
    data = dtb.read_bytes()
    if len(data) < 40:
        raise ValueError("Truncated FDT header")
    magic, total, _, _, reserve_offset = struct.unpack_from(">5I", data)
    if magic != 0xD00DFEED or total > len(data) or total < 40:
        raise ValueError("Invalid FDT header or total size")
    if reserve_offset < 40 or reserve_offset % 8:
        raise ValueError("Invalid FDT reservation map offset")
    header_reservations = []
    while True:
        if reserve_offset + 16 > total:
            raise ValueError("Unterminated FDT reservation map")
        address, size = struct.unpack_from(">QQ", data, reserve_offset)
        reserve_offset += 16
        if address == 0 and size == 0:
            break
        if address + size > 1 << 64:
            raise ValueError("FDT reservation overflows physical address space")
        header_reservations.append({"base": hex(address), "size": hex(size)})

    def get(*options):
        return subprocess.check_output(
            ["fdtget", *options], text=True, encoding="utf-8",
        ).strip()

    def children(node):
        return get("-l", str(dtb), node).splitlines()

    def properties(node):
        return set(get("-p", str(dtb), node).splitlines())

    def cells(node, key):
        return [int(value, 16) for value in get("-t", "x", str(dtb), node, key).split()]

    def parent_widths(parent):
        names = properties(parent)
        widths = tuple(cells(parent, key)[0] if key in names else default
                       for key, default in (("#address-cells", 2), ("#size-cells", 1)))
        if widths[0] not in (1, 2) or widths[1] not in (1, 2):
            raise ValueError(f"Unsupported reg cell widths at {parent}: {widths}")
        return widths

    def number(words):
        return int.from_bytes(b"".join(word.to_bytes(4, "big") for word in words), "big")

    def regions(node, parent):
        address_width, size_width = parent_widths(parent)
        words = cells(node, "reg")
        stride = address_width + size_width
        if len(words) % stride:
            raise ValueError(f"Incomplete reg tuple at {node}")
        return [{"base": hex(number(words[i:i + address_width])),
                 "size": hex(number(words[i + address_width:i + stride]))}
                for i in range(0, len(words), stride)]

    root_children = children("/")
    memory = {}
    hardware = {}
    for name in root_children:
        node = "/" + name
        if name == "memory" or name.startswith("memory@"):
            memory[node] = regions(node, "/")
        if name in {"timer", "psci"} or name.startswith(("gic", "serial@", "mmc@")):
            names = properties(node)
            hardware[node] = {
                key: get("-t", "s", str(dtb), node, key)
                for key in ("compatible", "method", "status") if key in names
            }
            if "reg" in names:
                hardware[node]["reg"] = regions(node, "/")

    reserved = {}
    if "reserved-memory" in root_children:
        for name in children("/reserved-memory"):
            node = "/reserved-memory/" + name
            names = properties(node)
            reserved[node] = {
                "reg": regions(node, "/reserved-memory") if "reg" in names else None,
                "no_map": "no-map" in names,
            }
            if "size" in names:
                reserved[node]["requested_size"] = hex(number(cells(node, "size")))

    print(json.dumps({
        "header_reservations": header_reservations,
        "memory_nodes": memory,
        "reserved_memory_nodes": reserved,
        "root_hardware_nodes": hardware,
    }, indent=2))


if __name__ == "__main__":
    main()
