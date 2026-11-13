"""Build own probes and an EFI application; run probes on QEMU virt only."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT/'build'
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def run(command, cwd=ROOT, timeout=45):
    result = subprocess.run(list(map(str, command)), cwd=cwd, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=timeout, creationflags=FLAGS)
    if result.returncode:
        raise RuntimeError('Command failed: '+str(command[0])+'\n'+result.stderr.decode('utf-8', errors='replace'))
    return result


def executable(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError('Required host tool missing: '+name)
    return path


def read_report(data):
    if len(data) != 64:
        raise ValueError('Probe report is not 64 bytes')
    values = struct.unpack('<IIIIQQQQQQ', data)
    keys = ('magic', 'version', 'architecture_bits', 'completed', 'register_status',
            'entry_pc', 'entry_sp', 'return_address', 'auxiliary_status', 'record_size')
    report = dict(zip(keys, values))
    if report['magic'] != 0x50353041 or report['version'] != 1 or report['completed'] != 1 or report['record_size'] != 64:
        raise ValueError('Invalid or unfinished probe report')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--edk2', type=Path, required=True)
    parser.add_argument('--wsl-elf-linker', metavar='DISTRO', help='Use upstream ELF ld.lld from this WSL distribution.')
    args = parser.parse_args()
    edk2 = args.edk2.resolve()
    lock = json.loads((ROOT/'sources.lock.json').read_text(encoding='utf-8'))['edk2']
    commit = run(['git', '-C', edk2, 'rev-parse', 'HEAD']).stdout.decode().strip()
    remote = run(['git', '-C', edk2, 'remote', 'get-url', 'origin']).stdout.decode().strip()
    if commit != lock['commit'] or remote != lock['url']:
        raise ValueError('EDK2 checkout does not match the official source lock')
    if run(['git', '-C', edk2, 'status', '--porcelain', '--untracked-files=no']).stdout.strip():
        raise ValueError('EDK2 has local modifications')
    BUILD.mkdir(exist_ok=True)
    clang, linker, objcopy, objdump = map(executable, ('clang', 'ld.lld', 'llvm-objcopy', 'llvm-objdump'))

    def link_elf(arguments):
        if args.wsl_elf_linker:
            converted = []
            for argument in arguments:
                value = str(argument)
                if re.match(r'^[A-Za-z]:[/\\]', value):
                    value = '/mnt/'+value[0].lower()+'/'+value[3:].replace('\\', '/')
                converted.append(value)
            return run([executable('wsl'), '-d', args.wsl_elf_linker, '--', 'ld.lld', *converted])
        return run([linker, *arguments])
    targets = [(32, 'armv7a-none-eabi', 'cortex-a15'), (64, 'aarch64-none-elf', 'cortex-a53')]
    probe_files = []
    for bits, target, cpu in targets:
        source = ROOT/f'A05Pkg/Bringup/AArch{bits}/Probe.S'
        obj = BUILD/f'probe{bits}.o'
        run([clang, '--target='+target, '-mcpu='+cpu, '-ffreestanding', '-c', source, '-o', obj])
        elf, binary = BUILD/f'probe{bits}.elf', BUILD/f'probe{bits}-function.bin'
        link_elf(['--build-id=none', '-Ttext=0', '--entry=A05Probe'+str(bits), '-o', elf, obj])
        run([objcopy, '-O', 'binary', '--only-section=.text', elf, binary])
        disassembly = run([objdump, '-d', obj]).stdout.decode('utf-8')
        (BUILD/f'probe{bits}.dis.txt').write_text(disassembly, encoding='utf-8')
        if re.search(r'\t(?:msr|mcr|smc|hvc|svc|hlt)\s', disassembly):
            raise ValueError('Probe contains a forbidden state-changing or trapping instruction')
        harness = BUILD/f'harness{bits}.o'
        run([clang, '--target='+target, '-mcpu='+cpu, '-c', ROOT/f'tests/Harness{bits}.S', '-o', harness])
        link_elf(['--build-id=none', '-T', ROOT/'tests/qemu.ld', '-o', BUILD/f'harness{bits}.elf', harness, obj])
        probe_files.append({'bits': bits, 'bytes': binary.stat().st_size,
                            'sha256': hashlib.sha256(binary.read_bytes()).hexdigest()})
    # The EFI application uses only the official EDK2 ABI headers, without CRT.
    coff = BUILD/'A05Bringup.obj'
    run([clang, '--target=aarch64-pc-windows-msvc', '-ffreestanding', '-fshort-wchar', '-fno-stack-protector',
         '-Wall', '-Wextra', '-Werror', '-I'+str(edk2/'MdePkg/Include'),
         '-I'+str(edk2/'MdePkg/Include/AArch64'), '-c', ROOT/'A05Pkg/Applications/Bringup/Bringup.c', '-o', coff])
    app = BUILD/'A05Bringup.efi'
    run([executable('lld-link'), '/machine:arm64', '/subsystem:efi_application', '/entry:UefiMain',
         '/nodefaultlib', '/timestamp:0', '/out:'+str(app), coff])
    pe = app.read_bytes()
    offset = struct.unpack_from('<I', pe, 0x3c)[0]
    assert pe[offset:offset+4] == b'PE\0\0'
    machine = struct.unpack_from('<H', pe, offset+4)[0]
    optional = offset+24
    assert machine == 0xaa64 and struct.unpack_from('<H', pe, optional)[0] == 0x20b
    assert struct.unpack_from('<H', pe, optional+68)[0] == 10
    assert struct.unpack_from('<II', pe, optional+112+8) == (0, 0), 'Unexpected imports'
    cases = [('a32-svc', 32, 'virt,secure=off,virtualization=off', 'cortex-a15', 0x13),
             ('a64-el1', 64, 'virt,secure=off,virtualization=off', 'cortex-a53', 4),
             ('a64-el2', 64, 'virt,secure=off,virtualization=on', 'cortex-a53', 8),
             ('a64-el3', 64, 'virt,secure=on,virtualization=on', 'cortex-a53', 12)]
    results = []
    for name, bits, machine, cpu, expected_status in cases:
        directory = BUILD/name
        directory.mkdir(exist_ok=True)
        report_file = directory/'report.bin'
        if report_file.exists():
            report_file.unlink()
        qemu = executable('qemu-system-arm' if bits == 32 else 'qemu-system-aarch64')
        result = run([qemu, '-machine', machine, '-cpu', cpu, '-accel', 'tcg,thread=single',
                      '-m', '128M', '-smp', '1', '-display', 'none', '-serial', 'none', '-monitor', 'none',
                      '-semihosting-config', 'enable=on,target=native',
                      '-device', 'loader,file='+str((BUILD/f'harness{bits}.elf').resolve()).replace('\\', '/')+',cpu-num=0'], cwd=directory, timeout=20)
        output = result.stdout+result.stderr
        (directory/'qemu-output.txt').write_bytes(output)
        if ('A05_PROBE'+str(bits)+'_OK').encode() not in output:
            raise ValueError('QEMU did not confirm the probe: '+name)
        report = read_report(report_file.read_bytes())
        assert report['architecture_bits'] == bits and report['entry_sp'] == 0x40400000
        if bits == 32:
            assert report['register_status'] & 0x1f == expected_status
        else:
            assert report['register_status'] == expected_status
        results.append({'case': name, 'passed': True, 'report': report,
                        'return_abi_and_callee_saved_preserved': True,
                        'invalid_buffers_rejected_without_writes': True})
    report = {'milestone': 'own probes executed on QEMU virt; own EFI application compiled',
              'edk2_commit': commit, 'edk2_modified': False, 'own_probe_binaries': probe_files,
              'uefi_application': {'path': 'build/A05Bringup.efi', 'machine': 'AARCH64',
                                    'subsystem': 'EFI_APPLICATION', 'imports': 0,
                                    'executed_in_uefi': False},
              'qemu_cases': results, 'phone_access': False, 'phone_partitions_written': False,
              'bootshim_used': False, 'external_platform_code_used': False,
              'uefi_firmware_rom_built': False, 'hardware_boot_proven': False}
    (BUILD/'validation.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
