#ifndef A05_EARLY_MEMORY_LIB_H
#define A05_EARLY_MEMORY_LIB_H

#include <Base.h>

typedef struct {
  UINT64 Base;
  UINT64 Size;
} A05_MEMORY_RANGE;

#define A05_MAX_RAM_BANKS   16
#define A05_MAX_EXCLUSIONS  128

typedef struct {
  A05_MEMORY_RANGE  Banks[A05_MAX_RAM_BANKS];
  A05_MEMORY_RANGE  Excluded[A05_MAX_EXCLUSIONS];
  UINTN             BankCount;
  UINTN             ExcludedCount;
} A05_MEMORY_LAYOUT;

RETURN_STATUS
EFIAPI
A05ReadMemoryLayout (
  IN CONST VOID              *Fdt,
  IN CONST A05_MEMORY_RANGE  *Image,
  OUT A05_MEMORY_LAYOUT      *Layout
  );

/**
  Select the highest page-aligned range that fits entirely in one RAM bank.
  Excluded ranges include the loaded firmware, DTB, initrd, and static
  reservations. The caller must resolve dynamic reservations separately.
  The selected range is returned without accessing the described memory.
**/
RETURN_STATUS
EFIAPI
A05SelectEarlyMemory (
  IN CONST A05_MEMORY_RANGE  *Banks,
  IN UINTN                   BankCount,
  IN CONST A05_MEMORY_RANGE  *Excluded OPTIONAL,
  IN UINTN                   ExcludedCount,
  IN UINT64                  Size,
  OUT A05_MEMORY_RANGE       *Selected
  );

/**
  Select scratch RAM from the DTB passed in the Linux AARCH64 handoff.
  The loader must have made the DTB readable at its physical address.
  Dynamic reusable pools can be allocated later by the OS.
**/
RETURN_STATUS
EFIAPI
A05SelectEarlyMemoryFromFdt (
  IN CONST VOID              *Fdt,
  IN CONST A05_MEMORY_RANGE  *Image,
  IN UINT64                   Size,
  OUT A05_MEMORY_RANGE       *Selected
  );

#endif
