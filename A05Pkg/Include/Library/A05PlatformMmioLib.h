#ifndef A05_PLATFORM_MMIO_LIB_H
#define A05_PLATFORM_MMIO_LIB_H

#include <Library/A05EarlyMemoryLib.h>

#define A05_MAX_GIC_RANGES  16

typedef struct {
  A05_MEMORY_RANGE  Gic[A05_MAX_GIC_RANGES];
  UINTN             GicCount;
  A05_MEMORY_RANGE  Uart[2];
  BOOLEAN           UartPresent[2];
} A05_PLATFORM_MMIO;

/**
  Read the root-level MT6768 interrupt controller and UART register ranges.
  Return page-aligned physical apertures for use in the SEC translation map.
  No MMIO is accessed.
**/
RETURN_STATUS
EFIAPI
A05ReadPlatformMmio (
  IN CONST VOID         *Fdt,
  OUT A05_PLATFORM_MMIO *Mmio
  );

#endif
