"""Check that DXE avoids a DTB reservation during a QEMU boot."""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

RESERVED_BASE = 0x7F000000
RESERVED_END = 0x80000000
BOARD_NODES = """
/ {
    gic500@0c000000 {
        compatible = "arm,gic-v3";
        reg = <0 0x0c000000 0 0x10000>, <0 0x0c080000 0 0x80000>;
    };
    serial@11002000 {
        compatible = "mediatek,mt6577-uart";
        reg = <0 0x11002000 0 0x400>;
    };
};
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    args = parser.parse_args()
    firmware = args.firmware.resolve(strict=True)
    qemu = [
        "qemu-system-aarch64", "-cpu", "cortex-a53", "-m", "1024",
        "-nographic", "-kernel", str(firmware),
    ]
    machine = "virt,virtualization=on"
    with tempfile.TemporaryDirectory() as directory:
        original = Path(directory) / "virt.dtb"
        source = Path(directory) / "reserved.dts"
        reserved = Path(directory) / "reserved.dtb"
        subprocess.run([*qemu, "-machine", f"{machine},dumpdtb={original}"], check=True)
        dts = subprocess.check_output(["dtc", "-q", "-I", "dtb", "-O", "dts", original], text=True)
        source.write_text(
            dts.replace("/dts-v1/;", "/dts-v1/;\n/memreserve/ 0x7f000000 0x01000000;", 1)
            + BOARD_NODES,
            encoding="utf-8",
        )
        subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", reserved, source], check=True)
        try:
            boot = subprocess.run(
                [*qemu, "-machine", machine, "-dtb", reserved],
                capture_output=True, timeout=15,
            )
            output = boot.stdout + boot.stderr
        except subprocess.TimeoutExpired as error:
            output = (error.stdout or b"") + (error.stderr or b"")

    log = output.decode("utf-8", errors="replace")
    expected = (
        "A05 reserved RAM HOB: 0x7F000000 size 0x1000000",
        "A05 SEC pool base: 0x7B000000",
        "A05 SEC device mapping: 0xC000000 size 0x10000",
        "A05 SEC device mapping: 0xC080000 size 0x80000",
        "A05 SEC device mapping: 0x11002000 size 0x1000",
        "BdsDxe: Press any key to enter the Boot Manager Menu.",
    )
    match = re.search(r"DxeMain: MemoryBaseAddress=(0x[0-9A-F]+) MemoryLength=(0x[0-9A-F]+)", log, re.I)
    if any(marker not in log for marker in expected) or match is None:
        raise SystemExit(log)
    base, length = (int(field, 16) for field in match.groups())
    if base < RESERVED_END and RESERVED_BASE < base + length:
        raise SystemExit(f"DXE used reserved RAM: {base:#x} + {length:#x}")
    for start, last in re.findall(r"Memory Allocation \S+ (0x[0-9A-F]+) - (0x[0-9A-F]+)", log, re.I):
        if int(start, 16) < RESERVED_END and RESERVED_BASE <= int(last, 16):
            raise SystemExit(f"DXE allocation overlaps reserved RAM: {start} - {last}")

    print(f"SEC and DXE avoided reserved RAM; DXE initialized {base:#x} + {length:#x} and reached BDS.")


if __name__ == "__main__":
    main()
