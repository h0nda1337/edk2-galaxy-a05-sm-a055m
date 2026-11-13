"""Verify that EDK II dispatches the A05 diagnostic DXE driver in QEMU."""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

MARKER = re.compile(
    r"^0x[0-9a-f]+:\s+d2940bbf\b[^\n]*\n"
    r"0x[0-9a-f]+:\s+f2ba1c3f\b", re.I | re.M,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("dtb", type=Path, help="Factory base DTB with its overlay applied")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory) / "qemu.trace"
        qemu = [
            "qemu-system-aarch64", "-machine", "virt,virtualization=on",
            "-cpu", "cortex-a53", "-m", "1024", "-display", "none", "-serial", "none",
            "-kernel", str(args.firmware.resolve(strict=True)),
            "-dtb", str(args.dtb.resolve(strict=True)),
            "-d", "int,in_asm", "-D", str(trace),
        ]
        try:
            subprocess.run(qemu, check=True, timeout=15)
        except subprocess.TimeoutExpired:
            pass  # The diagnostic intentionally parks after its UART marker.
        log = trace.read_text(encoding="utf-8")
    marker = MARKER.search(log)
    if marker is None or "Taking exception" in log:
        raise SystemExit("The QEMU trace did not reach the DXE diagnostic without exceptions.")
    print("The Galaxy A05 DXE diagnostic executed in QEMU with the factory DTB.")


if __name__ == "__main__":
    main()
