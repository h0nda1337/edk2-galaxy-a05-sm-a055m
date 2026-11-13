# Galaxy A05 SM-A055M EDK II UEFI

Port experimental de EDK II para el Samsung Galaxy A05 SM-A055M (a05m). El firmware objetivo es AARCH64. El arranque del teléfono está pendiente.

## Compilar y probar el código de diagnóstico

Requiere Git, Python 3, LLVM (clang, ld.lld, lld-link, llvm-objcopy y llvm-objdump) y QEMU para ARM y AArch64.

```sh
python tools/fetch_edk2.py
python tools/build_lab.py --edk2 vendor/edk2
```

Si el enlazador ELF de Windows falla, se puede usar `--wsl-elf-linker Debian` con LLVM instalado en esa distribución. El script compila las sondas propias y ejecuta cuatro casos en QEMU virt (AArch32 SVC y AArch64 EL1, EL2 y EL3). También genera `build/A05Bringup.efi`, una aplicación que se puede ejecutar desde un entorno UEFI AARCH64 existente.

## Fuentes

- [TianoCore EDK II](https://github.com/tianocore/edk2), revisión fijada en `sources.lock.json`.
- Código propio del proyecto en `A05Pkg`, `tools` y `tests`. El proyecto se desarrolla sin BootShim. La procedencia de los drivers se documentará al incorporarlos.
- [Samsung Open Source Release Center](https://opensource.samsung.com/), fuente prevista para contrastar la descripción de la placa con el firmware de fábrica.

El siguiente hito es confirmar el contrato de entrada y la memoria disponible para implementar SEC y el traspaso a DXE. El perfil actual mantiene indeterminados los parámetros de carga del teléfono.
