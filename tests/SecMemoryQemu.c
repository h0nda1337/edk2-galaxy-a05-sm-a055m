#include <Library/A05EarlyMemoryLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/FdtLib.h>

BOOLEAN
EFIAPI
A05CopyQemuFdt (
  OUT VOID       *Destination,
  IN OUT VOID    *Source
  )
{
  if ((FdtCheckHeader (Source) != 0) || (FdtTotalSize (Source) > 2 * 1024 * 1024)) {
    return FALSE;
  }

  if ((FdtPack (Source) != 0) || (FdtTotalSize (Source) > 0x78000)) {
    return FALSE;
  }

  CopyMem (Destination, Source, FdtTotalSize (Source));
  return TRUE;
}

UINT64
EFIAPI
A05FindEarlyMemoryBase (
  IN CONST VOID  *Fdt,
  IN UINT64      ImageBase,
  IN UINT32      ImageSize,
  IN UINT32      Size
  )
{
  A05_MEMORY_RANGE  Image;
  A05_MEMORY_RANGE  Selected;
  RETURN_STATUS     Status;

  Image.Base = ImageBase;
  Image.Size = ImageSize;
  Status = A05SelectEarlyMemoryFromFdt (Fdt, &Image, Size, &Selected);
  if (RETURN_ERROR (Status)) {
    return 0;
  }

  return Selected.Base;
}
