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

El código de la placa ya llega a DXE en QEMU. El siguiente hito es verificar en el teléfono el contrato de entrada del cargador de Samsung y observar una marca de diagnóstico.

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

`A05PlatformMmioLib` lee las direcciones y tamaños de `reg` y redondea los límites a páginas de 4 KiB. En el DTB de fábrica, el nodo raíz `/interrupt-controller` (`arm,gic-v3`) describe el distribuidor en `0x0C000000` (256 KiB) y los redistribuidores en `0x0C040000` (2 MiB). Los dos UART describen 4 KiB cada uno en `0x11002000` y `0x11003000`. El lector se verificó con ese árbol. [Binding GICv3](https://www.kernel.org/doc/Documentation/devicetree/bindings/interrupt-controller/arm,gic-v3.yaml)

## Imágenes de fábrica

Con Python 3.11 o posterior y `lz4`, `python tools/extract_stock_ap.py AP_FIRMWARE.tar.md5 local/stock` extrae `boot.img`, `vendor_boot.img`, `dtbo.img` y las demás imágenes de arranque presentes. También acepta el ZIP que contiene el AP. El script comprueba los formatos y guarda los tamaños y SHA-256 en `manifest.json`. Mantener estos archivos en almacenamiento local. Usar `unpack_bootimg.py` de AOSP para extraer el DTB de `vendor_boot.img`. [Herramienta oficial de AOSP](https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/main/unpack_bootimg.py)

Si `vendor_boot` contiene varios árboles concatenados, `python tools/split_vendor_dtbs.py local/unpacked/dtb local/stock-dtbs` extrae cada árbol e informa su desplazamiento y SHA-256. Inspeccionar cada candidato con `inspect_dtb.py`. La selección del árbol y sus overlays depende de la variante de placa y del cargador de Samsung.

El SM-A055M TCE consultado con ADB reportó `ro.boot.dtb_idx=0` y `ro.boot.dtbo_idx=0`. En el paquete de fábrica `A055MUBUGDZB2`, el DTB de `vendor_boot` y el DTBO están en tablas Android de versión 0 con una entrada cada una. Ejecutar el desempaquetador de `vendor_boot` desde Linux para que pueda crear los enlaces simbólicos del ramdisk.

```sh
python3 mkdtboimg.py dump local/unpacked/dtb --dtb local/base --decompress
python3 mkdtboimg.py dump local/stock/dtbo.img --dtb local/overlay --decompress
fdtoverlay -i local/base.0 -o local/board.dtb local/overlay.0
```

El árbol reconstruido tiene SHA-256 `1d516a1d2e887fa6a72bf44f1fab9fa4d317964cc8b67287fd431f628bc3885e`. El lector aplaza las solicitudes dinámicas conocidas de los controladores Android de esta placa cuando solo declaran un tamaño. Las reservas estáticas de esos nodos se respetan cuando el cargador proporciona `reg`, igual que las demás reservas estáticas y las del encabezado FDT. Una solicitud dinámica desconocida sin dirección detiene la selección de RAM. La geometría final se debe comprobar en el DTB de ejecución. `boot.img` tiene encabezado v4 con kernel gzip y ramdisk vacío. `vendor_boot.img` tiene encabezado v4 y declara `0x40080000` como dirección del kernel. [Herramienta DTBO de AOSP](https://android.googlesource.com/platform/system/libufdt/+/refs/heads/main/utils/src/mkdtboimg.py)

En un arranque de fábrica de `A055MUBUGDZB2`, el registro `SYSTEM_LAST_KMSG` de Android conservó la dirección de salto a Linux AARCH64 (`0x40080000`) y una reserva de framebuffer de `0xfb0000` bytes en `0x75e50000`. Se puede localizar el registro con `adb shell dumpsys dropbox` y consultarlo con `adb shell dumpsys dropbox --print NOMBRE_DEL_REGISTRO`. El árbol visible con ADB también contiene `/reserved-memory/mblock-16-framebuffer/reg` y un nodo `zone-movable-cma-memory` que solo expone su nombre. SEC omite ese nodo cuando carece de propiedades de reserva. La prueba en QEMU reproduce esa forma del árbol. Estas direcciones provienen de un arranque de Android y el diagnóstico sigue leyendo el DTB que recibe en cada arranque.

`tools/package_boot_v4.py --stock-boot local/stock/boot.img --firmware RUTA_AL_FD --output local/boot-lab.img` genera un contenedor de laboratorio v4 sin firmar. Conserva los metadatos del encabezado de fábrica y coloca el firmware comprimido con gzip en la sección del kernel. La prueba usó el `boot.img` original de TCE y un FD de ArmVirt. AOSP desempaquetó el resultado y el FD se recuperó byte por byte. La aceptación del contenedor por el cargador de Samsung y el arranque físico siguen pendientes. [Formato de arranque de AOSP](https://source.android.com/docs/core/architecture/bootloader/boot-image-header)

## Compilación de diagnóstico para la placa

`python3 tools/build_sec_qemu.py --phone --edk2 /ruta/al/checkout/edk2` genera `GALAXY_A05.fd` con SEC, DXE Core y una marca de diagnóstico en UART0. SEC construye el mapa MMIO a partir del DTB del cargador. El transmisor usa la configuración de UART heredada del cargador. Esta compilación está enfocada en el traspaso a DXE y todavía carece del conjunto de controladores y protocolos necesarios para BDS.

Para verificar el traspaso con el DTB de fábrica reconstruido, ejecutar `python3 tests/check_phone_dxe_trace.py RUTA_AL_FD local/board.dtb`. La prueba comprueba la firma de instrucciones del constructor DXE en la traza de QEMU. El diagnóstico emite una marca por UART en SEC y otra en DXE antes de detenerse. Queda pendiente observar esas marcas en el teléfono.

DXE también escribe franjas blancas y negras en el primer MiB del framebuffer heredado si el cargador declara el panel inicializado y la dirección y el tamaño concuerdan con su reserva `no-map` del DTB. La reserva puede estar fuera de los rangos de RAM utilizable. Para comprobar las escrituras con un framebuffer sintético, ejecutar en Linux `python3 tests/check_phone_framebuffer.py RUTA_AL_FD local/board.dtb` con QEMU y `fdtput`. La prueba usa los 20 rangos de RAM no vacíos del registro de LK y examina el patrón en RAM con el monitor de QEMU. Arranca desde EL1 y EL2, los dos niveles de entrada permitidos por el protocolo AARCH64 de Linux. La visibilidad del patrón depende del estado del panel durante el arranque físico. [Protocolo de arranque AARCH64](https://docs.kernel.org/arch/arm64/booting.html)

## Preparar la prueba física y la restauración

Antes de cambiar `boot`, confirmar con ADB el modelo `SM-A055M`, el estado `unlocked` y la versión instalada con `adb shell getprop ro.build.PDA`. Extraer el `boot.img` original del AP correspondiente a esa versión y preparar ambos paquetes antes de entrar a Download Mode:

```sh
python tools/package_boot_v4.py --stock-boot local/stock/boot.img --firmware RUTA_AL_FD --output local/boot-lab.img
python tools/package_boot_tar.py --boot local/boot-lab.img --output local/AP-lab-boot.tar
python tools/package_boot_tar.py --boot local/stock/boot.img --output local/AP-stock-boot.tar
```

Cada TAR contiene solo `boot.img`. Usar exclusivamente la ranura AP, con el resto de ranuras vacías y sin reparticionar ni borrar el almacenamiento. Confirmar que se puede regresar a Download Mode mediante los botones antes de instalar la imagen de diagnóstico. Para restaurar, cargar el TAR original del mismo modo y verificar con ADB que Android termine de arrancar (`sys.boot_completed=1`) y reporte la versión esperada. El SHA-256 del `boot.img` original de la unidad de prueba TCE (`A055MUBUGDZB2`) es `40b8e6d688dcaaf1414ff9777e89cbfb2f19241d79be56970cd4246ad9be84d4`. Mantener los archivos de fábrica y los TAR fuera del repositorio.

Registrar por separado el resultado de la escritura, lo observado en el teléfono y el arranque de Android tras la restauración. Un resultado exitoso de la herramienta de flasheo solo confirma la escritura. La ausencia de franjas tampoco descarta el arranque del firmware si el cargador no deja el panel inicializado.
