"""Fetch only the official EDK2 checkout pinned by this project; no phone I/O."""
from pathlib import Path
import argparse
import json
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def git(*arguments):
    return subprocess.check_output(['git', *map(str, arguments)], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=ROOT/'vendor/edk2')
    args = parser.parse_args()
    target = args.destination.resolve()
    lock = json.loads((ROOT/'sources.lock.json').read_text(encoding='utf-8'))['edk2']
    if lock['url'] != 'https://github.com/tianocore/edk2.git':
        raise ValueError('Only official TianoCore EDK2 is permitted here.')
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        git('clone', '--depth', '1', '--filter=blob:none', '--sparse', '--branch', lock['tag'], lock['url'], target)
        git('-C', target, 'sparse-checkout', 'set', 'MdePkg', 'MdeModulePkg', 'ArmPlatformPkg', 'ArmVirtPkg', 'BaseTools')
    if git('-C', target, 'rev-parse', 'HEAD') != lock['commit']:
        raise ValueError('EDK2 commit differs from the pinned revision.')
    if git('-C', target, 'remote', 'get-url', 'origin') != lock['url']:
        raise ValueError('EDK2 origin is not the allowed upstream.')
    if git('-C', target, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('The official EDK2 checkout has local modifications.')
    print('Official EDK2 verified: '+lock['tag']+' / '+lock['commit'])


if __name__ == '__main__':
    main()
