/* QEMU virt fixture only. Never use these addresses on the A05. */
ENTRY(_start)
SECTIONS
{
  . = 0x40200000;
  .text : { *(.text.start) *(.text.probe) *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) }
  .bss (NOLOAD) : { *(.bss*) *(COMMON) }
  /DISCARD/ : { *(.comment) *(.note*) }
}
