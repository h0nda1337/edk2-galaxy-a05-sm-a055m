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

## Validación

- Las cuatro sondas pasaron en QEMU virt. AAVMF cargó `A05Bringup.efi` como `EFI/BOOT/BOOTAA64.EFI` en QEMU AARCH64 e imprimió `A05 UEFI bring-up: application entry reached.`
- `python tools/inventory_adb.py` reproduce el inventario de solo lectura en `config/SM-A055M-adb.json`. Android reportó `mt6768`, SoC `MT6769V/CZ` y estado `unlocked`. Los nombres de nodos orientan la investigación de GIC, temporizador, PSCI, UART, eMMC y framebuffer. Sus propiedades de hardware siguen pendientes porque Android denegó la lectura del DTB y de los nodos consultados.
- Quedan por confirmar el mapa de RAM y sus reservas, el estado de CPU al entrar y un canal de diagnóstico físico. La prueba AAVMF usa el firmware de QEMU.

Para examinar un DTB local con device-tree-compiler instalado, ejecutar `python3 tools/inspect_dtb.py archivo.dtb`. El inspector informa regiones de memoria, reservas del encabezado FDT, nodos de memoria reservada y propiedades de GIC, PSCI, UART y MMC. Las reservas dinámicas aparecen con dirección pendiente. El mapa UEFI debe usar el DTB que entrega el cargador, con sus ajustes y overlays aplicados.

## Entrada AARCH64 y memoria inicial

La configuración del kernel de fábrica, leída de `/proc/config.gz` en el SM-A055M TCE con `A055MUBUGDZB2`, confirma ARM64 con páginas de 4 KiB y `CONFIG_KEXEC` y `CONFIG_KEXEC_FILE` deshabilitados. Los dos UART visibles por ADB se enlazan al controlador `mt6577-uart`.

La entrada candidata usa el protocolo de arranque de Linux AARCH64, que pasa el DTB en `x0`. La referencia oficial `ArmVirtQemuKernel` llegó a DXE y BDS en QEMU mediante ese protocolo. Para repetir la compilación, usar un checkout completo de EDK II en la revisión fijada y GCC cruzado para AARCH64.

```sh
git submodule update --init
make -C BaseTools
. edksetup.sh
export GCC_AARCH64_PREFIX=aarch64-linux-gnu-
build -p ArmVirtPkg/ArmVirtQemuKernel.dsc -a AARCH64 -t GCC -b DEBUG
qemu-system-aarch64 -machine virt,virtualization=on -cpu cortex-a53 -m 1024 \
  -nographic -kernel Build/ArmVirtQemuKernel-AArch64/DEBUG_GCC/FV/QEMU_EFI.fd
```

`A05EarlyMemoryLib` selecciona una región alineada dentro de un banco de RAM. Lee los bancos, las reservas del encabezado y los nodos `reserved-memory` del DTB que recibe del cargador. También excluye la imagen cargada, el DTB y el initrd. La prueba de host cubre reservas solapadas, direcciones por encima de 4 GiB, rangos desbordados y falta de espacio. La lectura del DTB se verificó con un árbol sintético que contiene dos bancos, reservas y un initrd.

Para compilar la integración de SEC en Linux con la misma revisión de EDK II y BaseTools ya compilado:

```sh
python3 tools/build_sec_qemu.py --edk2 /ruta/al/checkout/edk2
qemu-system-aarch64 -machine virt,virtualization=on -cpu cortex-a53 -m 1024 \
  -nographic -kernel build/sec-qemu/Build/ArmVirtQemuKernel-AArch64/DEBUG_GCC/FV/QEMU_EFI.fd
```

SEC entrega a DXE descriptores HOB separados para RAM disponible y reservada. La prueba con 1 GiB de RAM y `/memreserve/ 0x7f000000 0x01000000` eligió `0x7b000000` para los 64 MiB de SEC. DXE inicializó memoria en `0x7b001000` y llegó a BDS sin solapar la reserva en las asignaciones registradas. Para repetir la prueba con QEMU y `dtc` instalados, ejecutar `python3 tests/check_sec_qemu_reservations.py RUTA_AL_FD`.

La prueba construye el mapa de traducción MMU con los HOB de RAM disponible y agrega la imagen de firmware y la ventana MMIO de QEMU. Las reservas ajenas a la imagen quedan fuera de ese mapa. La prueba de integración añade nodos sintéticos con los nombres del GIC y UART del A05 y comprueba que SEC incorpora sus rangos como memoria de dispositivo antes de llegar a BDS. Los tamaños sintéticos sirven para probar la integración con EDK II.

`A05PlatformMmioLib` lee las direcciones y tamaños de `reg` y redondea los límites a páginas de 4 KiB. Android expone los nodos raíz `gic500@0c000000`, `serial@11002000` y `serial@11003000`. El lector usa los compatibles de GICv3 y MediaTek UART de los bindings de Linux. Falta verificar los compatibles y las propiedades `reg` reales con el DTB de Samsung y probar el firmware de la placa. [GICv3](https://www.kernel.org/doc/Documentation/devicetree/bindings/interrupt-controller/arm,gic-v3.yaml) · [UART MediaTek](https://www.kernel.org/doc/Documentation/devicetree/bindings/serial/mediatek,uart.yaml)
