"""Check the DXE marker writes against a synthetic loader framebuffer in QEMU."""

import argparse
import json
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import time

BASE = 0x75e50000
SIZE = 0xfb0000
END = 0x100000
CANARY = 0x13579bdf
TIMEOUT = 15
KERNEL_ADDRESS = 0x40080000
DTB_ADDRESS = 0x4bc80000
DTB_RESERVATION = "/reserved-memory/mblock-24-dtb_addr_mrdump"
INITRD_ADDRESS = 0x47c80000
INITRD_SIZE = 12436757
TEST_ENTRY_ADDRESS = 0x40800000
RESERVATION = "/reserved-memory/mblock-16-framebuffer"
# Nonempty usable ranges reported by LK in the A055MUBUGDZB2 stock boot log.
RAM_RANGES = (
    (0x40000000, 0xbc80000), (0x4bd00000, 0x380000),
    (0x4c280000, 0x180000), (0x4ca00000, 0x400000),
    (0x4ce60000, 0x1a0000), (0x4d100000, 0xf00000),
    (0x4e000000, 0x20000000), (0x6f600000, 0xa00000),
    (0x70910000, 0x4530000), (0x74e50000, 0x1000000),
    (0x7ea41000, 0xbf000), (0x80000000, 0x1f900000),
    (0x9ff00000, 0xf0000), (0xa0000000, 0x2000000),
    (0xb2000000, 0x4b00000), (0xb6b00000, 0x9400000),
    (0xbff40000, 0x30000), (0xbfff0000, 0xf000),
    (0xc0000000, 0x3fc00000), (0xffc00000, 0x403ff000),
)


def make_fixture(source, output):
    shutil.copyfile(source, output)
    subprocess.run(["fdtput", "-p", "-c", output, RESERVATION, DTB_RESERVATION], check=True)
    # The A05's runtime tree also exposes this placeholder with only a name.
    movable_pool = "/reserved-memory/zone-movable-cma-memory"
    subprocess.run(["fdtput", "-p", "-c", output, movable_pool], check=True)
    subprocess.run(["fdtput", "-t", "s", output, movable_pool, "name",
                    "zone-movable-cma-memory"], check=True)
    ram_cells = [f"{value:x}" for address, size in RAM_RANGES
                 for value in (address >> 32, address & 0xffffffff, size >> 32, size & 0xffffffff)]
    props = [
        ("/memory", "reg", *ram_cells),
        (DTB_RESERVATION, "reg", "0", f"{DTB_ADDRESS:x}", "0", "80000"),
        (RESERVATION, "reg", "0", f"{BASE:x}", "0", f"{SIZE:x}"),
        (RESERVATION, "no-map"),
        ("/chosen", "linux,initrd-start", f"{INITRD_ADDRESS:x}"),
        ("/chosen", "linux,initrd-end", f"{INITRD_ADDRESS + INITRD_SIZE:x}"),
        ("/chosen", "atag,videolfb-fb_base_h", "0"),
        ("/chosen", "atag,videolfb-fb_base_l", f"{BASE:x}"),
        ("/chosen", "atag,videolfb-vramSize", f"{SIZE:x}"),
        ("/chosen", "atag,videolfb-islcm_inited", "1"),
    ]
    for prop in props:
        subprocess.run(["fdtput", "-t", "x", output, *prop], check=True)


def check_pixels(qemu, endpoint):
    deadline = time.monotonic() + TIMEOUT
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        while True:
            try:
                client.connect(str(endpoint))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if qemu.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("QEMU did not open its monitor") from None
                time.sleep(0.05)
        client.settimeout(2)
        with client.makefile("rwb") as stream:
            json.loads(stream.readline())

            def command(name, args=None):
                request = {"execute": name}
                if args is not None:
                    request["arguments"] = args
                stream.write(json.dumps(request).encode() + b"\n")
                stream.flush()
                while True:
                    result = json.loads(stream.readline())
                    if "return" in result:
                        return result["return"]
                    if "error" in result:
                        raise RuntimeError(result["error"])

            def read_word(offset):
                info = command("human-monitor-command", {"command-line": f"xp /1wx {BASE + offset:#x}"})
                word = re.search(r":\s*(0x[0-9a-f]+)", info, re.I)
                if word is None:
                    raise RuntimeError(f"QEMU could not read framebuffer memory: {info}")
                return int(word[1], 16)

            command("qmp_capabilities")
            while read_word(0xe0000) != 0xffffffff or read_word(END - 4) != 0:
                if time.monotonic() >= deadline:
                    raise RuntimeError("The DXE marker did not reach the last band")
                time.sleep(0.10)
            command("stop")
            for offset, expected in (
                (0, 0xffffffff), (0xfffc, 0xffffffff), (0x10000, 0),
                (0x1fffc, 0), (0x20000, 0xffffffff), (END, CANARY),
            ):
                actual = read_word(offset)
                if actual != expected:
                    raise RuntimeError(f"Framebuffer word at +{offset:#x}: {actual:#x}, expected {expected:#x}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("dtb", type=Path, help="Factory base DTB with its overlay applied")
    parser.add_argument("--disable-uart", action="store_true",
                        help="Mark UART0 disabled in the test device tree.")
    args = parser.parse_args()
    firmware = args.firmware.resolve(strict=True)
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory) / "framebuffer.dtb"
        make_fixture(args.dtb, fixture)
        if args.disable_uart:
            subprocess.run(["fdtput", "-t", "s", fixture, "/serial@11002000",
                            "status", "disabled"], check=True)
        entry = Path(directory) / "qemu-entry.bin"
        # Set the Linux handoff registers, then branch to the FD. This code
        # runs only in QEMU and is independent of the packaged image.
        entry.write_bytes(struct.pack(
            "<5I",
            0xd2a00000 | ((DTB_ADDRESS >> 16) << 5),  # movz x0, #0x4bc8, lsl #16
            0xaa1f03e1,  # mov x1, xzr
            0xaa1f03e2,  # mov x2, xzr
            0xaa1f03e3,  # mov x3, xzr
            0x14000000 | (((KERNEL_ADDRESS - TEST_ENTRY_ADDRESS - 16) // 4) & 0x03ffffff),
        ))
        for level, virtualization in ((1, "off"), (2, "on")):
            endpoint = Path(directory) / f"qmp-el{level}"
            with subprocess.Popen([
                "qemu-system-aarch64", "-machine", f"virt,virtualization={virtualization}",
                "-cpu", "cortex-a53", "-m", "4096", "-display", "none", "-serial", "none",
                "-monitor", "none", "-qmp", f"unix:{endpoint},server=on,wait=off",
                "-kernel", str(firmware), "-dtb", str(fixture),
                "-device", f"loader,file={fixture},addr={DTB_ADDRESS:#x},force-raw=on",
                "-device", f"loader,file={entry},addr={TEST_ENTRY_ADDRESS:#x},force-raw=on,cpu-num=0",
                "-device", f"loader,addr={BASE + END - 4:#x},data={CANARY:#x},data-len=4",
                "-device", f"loader,addr={BASE + END:#x},data={CANARY:#x},data-len=4",
            ]) as qemu:
                try:
                    check_pixels(qemu, endpoint)
                finally:
                    qemu.terminate()
            print(f"QEMU EL{level}: verified DXE stripes and the guard word after the one-MiB pattern.")


if __name__ == "__main__":
    main()
