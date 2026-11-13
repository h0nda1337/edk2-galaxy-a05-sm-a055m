#include <Library/A05PlatformMmioLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/FdtLib.h>

#define PAGE_MASK  0xFFFULL

STATIC
RETURN_STATUS
ReadRootMmio (
  IN CONST VOID         *Fdt,
  IN CONST CHAR8        *Path,
  IN CONST CHAR8        *Compatible,
  OUT A05_MEMORY_RANGE  *Ranges,
  IN UINTN              Capacity,
  OUT UINTN             *Count
  )
{
  INT32         Node;
  INT32         Bytes;
  INT32         AddressCells;
  INT32         SizeCells;
  CONST CHAR8   *Strings;
  CONST UINT32  *Cells;
  UINTN         Index;
  INT32         Cell;
  UINT64        Base;
  UINT64        Size;

  Node = FdtPathOffset (Fdt, Path);
  if (Node < 0) {
    return (Node == -FDT_ERR_NOTFOUND) ? RETURN_NOT_FOUND : RETURN_COMPROMISED_DATA;
  }

  Strings = FdtGetProp (Fdt, Node, "status", &Bytes);
  if (Strings != NULL) {
    if (!((Bytes == sizeof ("okay")) && (CompareMem (Strings, "okay", sizeof ("okay")) == 0)) &&
        !((Bytes == sizeof ("ok")) && (CompareMem (Strings, "ok", sizeof ("ok")) == 0))) {
      return RETURN_NOT_FOUND;
    }
  } else if (Bytes != -FDT_ERR_NOTFOUND) {
    return RETURN_COMPROMISED_DATA;
  }

  Strings = FdtGetProp (Fdt, Node, "compatible", &Bytes);
  if ((Strings == NULL) || (Bytes <= 0) || (FdtStringListContains (Strings, Bytes, Compatible) != 1)) {
    return RETURN_UNSUPPORTED;
  }

  AddressCells = FdtAddressCells (Fdt, 0);
  SizeCells    = FdtSizeCells (Fdt, 0);
  Cells        = FdtGetProp (Fdt, Node, "reg", &Bytes);
  if ((AddressCells < 1) || (AddressCells > 2) || (SizeCells < 1) || (SizeCells > 2) ||
      (Cells == NULL) || (Bytes <= 0) || (Bytes % ((AddressCells + SizeCells) * 4) != 0)) {
    return RETURN_COMPROMISED_DATA;
  }

  *Count = (UINTN)Bytes / ((AddressCells + SizeCells) * 4);
  if (*Count > Capacity) {
    return RETURN_OUT_OF_RESOURCES;
  }

  for (Index = 0; Index < *Count; Index++) {
    Base = 0;
    for (Cell = 0; Cell < AddressCells; Cell++) {
      Base = (Base << 32) | Fdt32ToCpu (*Cells++);
    }

    Size = 0;
    for (Cell = 0; Cell < SizeCells; Cell++) {
      Size = (Size << 32) | Fdt32ToCpu (*Cells++);
    }

    if ((Size == 0) || (Base > MAX_UINT64 - Size) ||
        (Base + Size > MAX_UINT64 - PAGE_MASK)) {
      return RETURN_COMPROMISED_DATA;
    }

    Ranges[Index].Base = Base & ~PAGE_MASK;
    Ranges[Index].Size = ALIGN_VALUE (Base + Size, PAGE_MASK + 1) - Ranges[Index].Base;
  }

  return RETURN_SUCCESS;
}

RETURN_STATUS
EFIAPI
A05ReadPlatformMmio (
  IN CONST VOID         *Fdt,
  OUT A05_PLATFORM_MMIO *Mmio
  )
{
  STATIC CONST CHAR8 *CONST UartPaths[] = { "/serial@11002000", "/serial@11003000" };
  A05_PLATFORM_MMIO         Detected;
  RETURN_STATUS             Status;
  UINTN                     Index;
  UINTN                     Count;

  if ((Fdt == NULL) || (Mmio == NULL)) {
    return RETURN_INVALID_PARAMETER;
  }

  if ((FdtCheckHeader (Fdt) != 0) || (FdtTotalSize (Fdt) > 2U * 1024U * 1024U)) {
    return RETURN_COMPROMISED_DATA;
  }

  ZeroMem (&Detected, sizeof (Detected));
  Status = ReadRootMmio (Fdt, "/interrupt-controller", "arm,gic-v3", Detected.Gic,
                         A05_MAX_GIC_RANGES, &Detected.GicCount);
  if (RETURN_ERROR (Status)) {
    return Status;
  }

  if (Detected.GicCount < 2) {
    return RETURN_COMPROMISED_DATA;
  }

  for (Index = 0; Index < ARRAY_SIZE (UartPaths); Index++) {
    Status = ReadRootMmio (Fdt, UartPaths[Index], "mediatek,mt6577-uart",
                           &Detected.Uart[Index], 1, &Count);
    if (Status == RETURN_NOT_FOUND) {
      continue;
    }

    if (RETURN_ERROR (Status)) {
      return Status;
    }

    Detected.UartPresent[Index] = TRUE;
  }

  CopyMem (Mmio, &Detected, sizeof (Detected));
  return RETURN_SUCCESS;
}
