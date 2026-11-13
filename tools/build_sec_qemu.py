"""Build the A05 SEC integration or its QEMU validation image against pinned EDK II."""

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
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--phone", action="store_true", help="Build the Galaxy A05 SEC-to-DXE diagnostic image.")
    parser.add_argument("--phone-uart", action="store_true",
                        help="Use UART0 when its clock and pinmux are known to be ready.")
    args = parser.parse_args()
    if args.phone_uart and not args.phone:
        parser.error("--phone-uart requires --phone.")
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
    variant = "sec-phone-uart" if args.phone_uart else "sec-phone" if args.phone else "sec-qemu"
    workspace = (args.workspace or ROOT / "build" / variant).resolve()
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
    shutil.copyfile(ROOT / "tests" / "MemoryHobsQemu.c", prepi / "MemoryHobsQemu.c")
    inf = prepi / "ArmVirtPrePiUniCoreRelocatable.inf"
    content = inf.read_text(encoding="utf-8")
    content = rewrite(content, "  FdtParser.c\n", "  FdtParser.c\n  SecMemoryQemu.c\n  MemoryHobsQemu.c\n")
    content = rewrite(content, "[Packages]\n", "[Packages]\n  A05Pkg/A05Pkg.dec\n  UefiCpuPkg/UefiCpuPkg.dec\n")
    content = rewrite(content, "[LibraryClasses]\n",
                      "[LibraryClasses]\n  A05EarlyMemoryLib\n  A05PlatformMmioLib\n  ArmMmuLib\n")
    content = rewrite(content, "[Guids]\n", "[Guids]\n  gA05DiagnosticFramebufferGuid\n")
    inf.write_text(content, encoding="utf-8")

    main_source = prepi / "PrePi.c"
    content = rewrite(
        main_source.read_text(encoding="utf-8"), '#include "PrePi.h"\n',
        '#include "PrePi.h"\n\n'
        "EFI_STATUS EFIAPI A05BuildMemoryHobs (CONST VOID *Fdt, UINT64 ImageBase, UINT32 ImageSize);\n"
        "EFI_STATUS EFIAPI A05ConfigureQemuMmu (CONST VOID *Fdt, UINT64 ImageBase, UINT32 ImageSize, UINT64 FvBase, UINT32 FvSize, BOOLEAN UseQemuMmio, BOOLEAN UsePhoneUart);\n"
        "VOID BuildMemoryTypeInformationHob (VOID);\n",
    )
    content = rewrite(
        content,
        "  Status = MemoryPeim (UefiMemoryBase, FixedPcdGet32 (PcdSystemMemoryUefiRegionSize));\n"
        "  ASSERT_EFI_ERROR (Status);\n",
        "  Status = A05BuildMemoryHobs ((CONST VOID *)(UINTN)PcdGet64 (PcdDeviceTreeInitialBaseAddress),\n"
        "                              PcdGet64 (PcdFdBaseAddress), PcdGet32 (PcdFdSize));\n"
        "  if (EFI_ERROR (Status)) {\n"
        "    CpuDeadLoop ();\n"
        "  }\n"
        "  Status = A05ConfigureQemuMmu ((CONST VOID *)(UINTN)PcdGet64 (PcdDeviceTreeInitialBaseAddress),\n"
        "                               PcdGet64 (PcdFdBaseAddress), PcdGet32 (PcdFdSize),\n"
        "                               PcdGet64 (PcdFvBaseAddress), PcdGet32 (PcdFvSize), "
        + ("FALSE" if args.phone else "TRUE") + ", "
        + ("TRUE" if args.phone_uart else "FALSE") + ");\n"
        "  if (EFI_ERROR (Status)) {\n"
        "    CpuDeadLoop ();\n"
        "  }\n"
        "  if (FeaturePcdGet (PcdPrePiProduceMemoryTypeInformationHob)) {\n"
        "    BuildMemoryTypeInformationHob ();\n"
        "  }\n",
    )
    content = rewrite(
        content,
        "  SerialPortInitialize ();\n",
        "  SerialPortInitialize ();\n"
        '  DEBUG ((DEBUG_INFO, "A05 SEC pool base: 0x%Lx\\n", (UINT64)UefiMemoryBase));\n',
    )
    if args.phone:
        content = rewrite(content, "  Status = PlatformPeim ();\n  ASSERT_EFI_ERROR (Status);\n",
                          "  BuildFvHob (PcdGet64 (PcdFvBaseAddress), PcdGet32 (PcdFvSize));\n")
        if args.phone_uart:
            content = rewrite(content, "  SerialPortInitialize ();\n",
                              "  SerialPortInitialize ();\n"
                              '  SerialPortWrite ((UINT8 *)"A05 EDK II SEC reached\\r\\n",\n'
                              '                   sizeof ("A05 EDK II SEC reached\\r\\n") - 1);\n')
        content = rewrite(content, "  ASSERT_EFI_ERROR (Status);\n}\n",
                          "  if (EFI_ERROR (Status)) {\n    CpuDeadLoop ();\n  }\n}\n")
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
                      "  A05EarlyMemoryLib|A05Pkg/Library/A05EarlyMemoryLib/A05EarlyMemoryLib.inf\n"
                      "  A05PlatformMmioLib|A05Pkg/Library/A05PlatformMmioLib/A05PlatformMmioLib.inf\n")
    if args.phone:
        serial_lib = ("A05Pkg/Library/A05SerialPortLib/A05SerialPortLib.inf" if args.phone_uart
                      else "MdePkg/Library/BaseSerialPortLibNull/BaseSerialPortLibNull.inf")
        shared_dsc = workspace / "ArmVirtPkg" / "A05Phone.dsc.inc"
        shared = (upstream / "ArmVirt.dsc.inc").read_text(encoding="utf-8")
        content = rewrite(content, "!include ArmVirtPkg/ArmVirt.dsc.inc",
                          "!include ArmVirtPkg/A05Phone.dsc.inc")
        shared = rewrite(shared, "  DebugLib|ArmVirtPkg/Library/DebugLibFdtPL011Uart/DebugLibFdtPL011UartRam.inf",
                         "  DebugLib|MdePkg/Library/BaseDebugLibNull/BaseDebugLibNull.inf")
        shared = rewrite(shared, "  SerialPortLib|ArmVirtPkg/Library/FdtPL011SerialPortLib/FdtPL011SerialPortLib.inf",
                         "  SerialPortLib|MdePkg/Library/BaseSerialPortLibNull/BaseSerialPortLibNull.inf")
        core = "  MdeModulePkg/Core/Dxe/DxeMain.inf"
        # The core runs the diagnostic constructor before driver dispatch.
        shared = rewrite(shared, core + " {\n    <LibraryClasses>\n",
                          core + " {\n"
                          "    <LibraryClasses>\n"
                          "      DebugLib|MdePkg/Library/BaseDebugLibNull/BaseDebugLibNull.inf\n"
                          f"      SerialPortLib|{serial_lib}\n"
                          "      NULL|A05Pkg/Drivers/A05Dxe/A05Dxe.inf\n")
        shared_dsc.write_text(shared, encoding="utf-8")
        content = rewrite(content, "  ArmVirtPkg/PrePi/ArmVirtPrePiUniCoreRelocatable.inf {\n"
                                   "    <LibraryClasses>\n",
                          "  ArmVirtPkg/PrePi/ArmVirtPrePiUniCoreRelocatable.inf {\n"
                          "    <LibraryClasses>\n"
                          f"      SerialPortLib|{serial_lib}\n"
                          "      DebugLib|MdePkg/Library/BaseDebugLibNull/BaseDebugLibNull.inf\n")
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
    if args.phone:
        content = rewrite(content, "[FD.QEMU_EFI]", "[FD.GALAXY_A05]")
        fv_main = workspace / "ArmVirtPkg" / "ArmVirtQemuFvMain.fdf.inc"
        headers = fv_main.read_text(encoding="utf-8").split("  INF ", 1)[0]
        fv_main.write_text(
            headers + "  INF MdeModulePkg/Core/Dxe/DxeMain.inf\n"
                      "  INF MdeModulePkg/Universal/PCD/Dxe/Pcd.inf\n"
                      "  INF ArmPkg/Drivers/CpuDxe/CpuDxe.inf\n"
                      "  INF MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf\n",
            encoding="utf-8",
        )
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
    image = "GALAXY_A05.fd" if args.phone else "QEMU_EFI.fd"
    print(workspace / "Build/ArmVirtQemuKernel-AArch64/DEBUG_GCC/FV" / image)


if __name__ == "__main__":
    main()
