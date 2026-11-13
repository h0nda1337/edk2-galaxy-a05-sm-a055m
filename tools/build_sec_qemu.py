"""Build the QEMU integration of the A05 SEC memory selector against pinned EDK II."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edk2", type=Path, required=True, help="Full, clean upstream checkout with initialized submodules.")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--workspace", type=Path, default=ROOT / "build" / "sec-qemu")
    args = parser.parse_args()
    edk2 = args.edk2.resolve(strict=True)
    lock = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))["edk2"]

    def git(*command):
        return subprocess.check_output(["git", "-C", edk2, *command], text=True).strip()

    if git("rev-parse", "HEAD") != lock["commit"] or git("remote", "get-url", "origin") != lock["url"]:
        parser.error("The EDK II checkout must match sources.lock.json.")
    if git("status", "--porcelain", "--untracked-files=no"):
        parser.error("Use an unmodified EDK II checkout.")
    if args.jobs < 1:
        parser.error("--jobs must be positive.")

    # Generate a disposable workspace overlay. Resolve imports against upstream
    # with PACKAGES_PATH; the build does not edit tracked upstream files.
    workspace = args.workspace.resolve()
    prepi = workspace / "ArmVirtPkg" / "PrePi"
    prepi.mkdir(parents=True, exist_ok=True)
    upstream = edk2 / "ArmVirtPkg"

    def rewrite(text, original, replacement):
        if text.count(original) != 1:
            raise ValueError(f"Expected exactly one upstream occurrence of {original!r}")
        return text.replace(original, replacement)

    for source in (upstream / "PrePi").iterdir():
        if source.is_file():
            shutil.copyfile(source, prepi / source.name)
    entry = prepi / "ModuleEntryPoint.S"
    original = entry.read_text(encoding="utf-8")
    begin = original.index("// Check if we can install the stack")
    end = original.index("_GetStackBase:", begin)
    entry_text = original[:begin] + """  // Reuse the temporary stack inside the loaded firmware while reading the DTB.
  mov   x0, x28
  LDR_LIT(x1, PcdGet64 (PcdFdBaseAddress))
  MOV32 (w2, FixedPcdGet32 (PcdFdSize))
  MOV32 (w3, FixedPcdGet32 (PcdSystemMemoryUefiRegionSize))
  bl    ASM_PFX(A05FindEarlyMemoryBase)
  cbz   x0, _NeverReturn
  mov   x21, x0
  MOV32 (w4, FixedPcdGet32 (PcdSystemMemoryUefiRegionSize))
  add   x1, x21, x4

""" + original[end:]
    # Bound the copy so it cannot overwrite the temporary stack below the FV.
    entry_text = rewrite(
        entry_text, "  bl    CopyFdt\n", "  bl    A05CopyQemuFdt\n  cbz   w0, _NeverReturn\n",
    )
    entry.write_text(entry_text, encoding="utf-8")
    shutil.copyfile(ROOT / "tests" / "SecMemoryQemu.c", prepi / "SecMemoryQemu.c")
    inf = prepi / "ArmVirtPrePiUniCoreRelocatable.inf"
    content = inf.read_text(encoding="utf-8")
    content = rewrite(content, "  FdtParser.c\n", "  FdtParser.c\n  SecMemoryQemu.c\n")
    content = rewrite(content, "[Packages]\n", "[Packages]\n  A05Pkg/A05Pkg.dec\n")
    content = rewrite(content, "[LibraryClasses]\n", "[LibraryClasses]\n  A05EarlyMemoryLib\n")
    inf.write_text(content, encoding="utf-8")

    main_source = prepi / "PrePi.c"
    content = rewrite(
        main_source.read_text(encoding="utf-8"),
        "  SerialPortInitialize ();\n",
        "  SerialPortInitialize ();\n"
        '  DEBUG ((DEBUG_INFO, "A05 SEC pool base: 0x%Lx\\n", (UINT64)UefiMemoryBase));\n',
    )
    main_source.write_text(content, encoding="utf-8")

    # Keep the same package-relative paths for the FDF and its local includes.
    for source in upstream.iterdir():
        if source.is_file():
            shutil.copyfile(source, workspace / "ArmVirtPkg" / source.name)
        elif source.name != "PrePi":
            link = workspace / "ArmVirtPkg" / source.name
            if not link.exists():
                link.symlink_to(source, target_is_directory=True)
    dsc = workspace / "ArmVirtPkg" / "ArmVirtQemuKernel.dsc"
    content = rewrite(dsc.read_text(encoding="utf-8"), "[LibraryClasses.common]\n",
                      "[LibraryClasses.common]\n"
                      "  A05EarlyMemoryLib|A05Pkg/Library/A05EarlyMemoryLib/A05EarlyMemoryLib.inf\n")
    dsc.write_text(content, encoding="utf-8")

    fdf = workspace / "ArmVirtPkg" / "ArmVirtQemuKernel.fdf"
    content = fdf.read_text(encoding="utf-8")
    for old, new in (
        ("0x1f8000", "0x180000"),
        ("0x2f8000", "0x280000"),
        ("0x00000000|0x00008000", "0x00000000|0x00080000"),
        ("0x00008000|$(FVMAIN_COMPACT_SIZE)", "0x00080000|$(FVMAIN_COMPACT_SIZE)"),
        ("0xff, 0x1f, 0x00, 0x14,", "0xff, 0xff, 0x01, 0x14,"),
        ("b 0x8000", "b 0x80000"),
        ("round it up to 32 KB", "round it up to 512 KiB"),
    ):
        content = rewrite(content, old, new)
    fdf.write_text(content, encoding="utf-8")

    env = os.environ.copy()
    env["WORKSPACE"] = str(workspace)
    env["EDK_TOOLS_PATH"] = str(edk2 / "BaseTools")
    env["PACKAGES_PATH"] = os.pathsep.join((str(edk2), str(ROOT)))
    env.setdefault("GCC_AARCH64_PREFIX", "aarch64-linux-gnu-")
    subprocess.run(
        ["bash", "-ec", 'setup="$1/edksetup.sh"; jobs="$2"; set --; source "$setup"; '
         'exec build -p ArmVirtPkg/ArmVirtQemuKernel.dsc -a AARCH64 -t GCC -b DEBUG -n "$jobs"',
         "build-sec-qemu", edk2, str(args.jobs)],
        cwd=workspace, env=env, check=True,
    )
    print(workspace / "Build/ArmVirtQemuKernel-AArch64/DEBUG_GCC/FV/QEMU_EFI.fd")


if __name__ == "__main__":
    main()
