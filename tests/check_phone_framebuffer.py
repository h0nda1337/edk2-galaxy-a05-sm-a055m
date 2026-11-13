"""Check the DXE marker writes against a synthetic loader framebuffer in QEMU."""

import argparse
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time

BASE = 0x50000000
END = 0x100000
CANARY = 0x13579bdf
TIMEOUT = 15
RESERVATION = "/reserved-memory/mblock-16-framebuffer"


def make_fixture(source, output):
    shutil.copyfile(source, output)
    subprocess.run(["fdtput", "-p", "-c", output, RESERVATION], check=True)
    # The A05's runtime tree also exposes this placeholder with only a name.
    movable_pool = "/reserved-memory/zone-movable-cma-memory"
    subprocess.run(["fdtput", "-p", "-c", output, movable_pool], check=True)
    subprocess.run(["fdtput", "-t", "s", output, movable_pool, "name",
                    "zone-movable-cma-memory"], check=True)
    props = [
        (RESERVATION, "reg", "0", f"{BASE:x}", "0", "400000"),
        ("/chosen", "atag,videolfb-fb_base_h", "0"),
        ("/chosen", "atag,videolfb-fb_base_l", f"{BASE:x}"),
        ("/chosen", "atag,videolfb-vramSize", "400000"),
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
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory) / "framebuffer.dtb"
        endpoint = Path(directory) / "qmp"
        make_fixture(args.dtb, fixture)
        with subprocess.Popen([
            "qemu-system-aarch64", "-machine", "virt,virtualization=on",
            "-cpu", "cortex-a53", "-m", "1024", "-display", "none", "-serial", "none",
            "-monitor", "none", "-qmp", f"unix:{endpoint},server=on,wait=off",
            "-kernel", str(args.firmware.resolve(strict=True)), "-dtb", str(fixture),
            "-device", f"loader,addr={BASE + END - 4:#x},data={CANARY:#x},data-len=4",
            "-device", f"loader,addr={BASE + END:#x},data={CANARY:#x},data-len=4",
        ]) as qemu:
            try:
                check_pixels(qemu, endpoint)
            finally:
                qemu.terminate()
    print("QEMU verified the DXE stripes and the guard word immediately after the one-MiB pattern.")


if __name__ == "__main__":
    main()
