"""Read an allowlisted hardware inventory from the connected SM-A055M."""
import argparse
import json
import subprocess

PROPERTIES = {
    "model": "ro.product.model",
    "device": "ro.product.device",
    "platform": "ro.board.platform",
    "soc_model": "ro.soc.model",
    "android": "ro.build.version.release",
    "firmware": "ro.build.version.incremental",
    "vbmeta_device_state": "ro.boot.vbmeta.device_state",
    "verified_boot_state": "ro.boot.verifiedbootstate",
    "flash_locked": "ro.boot.flash.locked",
}

NODES = (
    "memory", "reserved-memory", "gic500@0c000000", "timer", "psci",
    "serial@11002000", "serial@11003000", "mmc@11230000", "mmc@11240000",
    "reserved-memory/mblock-16-framebuffer",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="Select a device when multiple devices are connected.")
    args = parser.parse_args()
    adb = ["adb", "-s", args.serial] if args.serial else ["adb"]

    def shell(command, *arguments):
        return subprocess.run(
            [*adb, "shell", command, *arguments],
            capture_output=True, text=True, timeout=10,
        )

    properties = {}
    for name, prop in PROPERTIES.items():
        result = shell("getprop", prop)
        result.check_returncode()
        properties[name] = result.stdout.strip()
        if name == "model" and properties[name] != "SM-A055M":
            parser.error("ADB target must be an SM-A055M.")

    arch = shell("uname", "-m")
    arch.check_returncode()
    nodes = [name for name in NODES
             if shell("test", "-d", "/proc/device-tree/" + name).returncode == 0]
    partitions = [name for name in ("boot", "vendor_boot", "dtbo")
                  if shell("test", "-L", "/dev/block/by-name/" + name).returncode == 0]
    print(json.dumps({
        **properties,
        "kernel_architecture": arch.stdout.strip(),
        "visible_device_tree_nodes": nodes,
        "visible_partition_links": partitions,
        "live_fdt_readable": shell("head -c 1 /sys/firmware/fdt >/dev/null").returncode == 0,
    }, indent=2))


if __name__ == "__main__":
    main()
