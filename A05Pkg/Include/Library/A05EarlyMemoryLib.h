#ifndef A05_EARLY_MEMORY_LIB_H
#define A05_EARLY_MEMORY_LIB_H

#include <Base.h>

typedef struct {
  UINT64 Base;
  UINT64 Size;
} A05_MEMORY_RANGE;

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

#endif
