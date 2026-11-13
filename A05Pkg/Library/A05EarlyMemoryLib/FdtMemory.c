#include <Library/A05EarlyMemoryLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/FdtLib.h>

#define A05_MAX_DTB_SIZE      (2U * 1024U * 1024U)

STATIC
UINT64
ReadCells (
  IN CONST UINT32  *Cells,
  IN INT32         Count
  )
{
  UINT64  Value;

  Value = Fdt32ToCpu (Cells[0]);
  if (Count == 2) {
    Value = (Value << 32) | Fdt32ToCpu (Cells[1]);
  }

  return Value;
}

STATIC
RETURN_STATUS
ReadRanges (
  IN CONST VOID          *Fdt,
  IN INT32               Parent,
  IN INT32               Node,
  IN OUT A05_MEMORY_RANGE *Ranges,
  IN OUT UINTN           *Count,
  IN UINTN               Capacity
  )
{
  CONST UINT32  *Cells;
  INT32         AddressCells;
  INT32         SizeCells;
  INT32         Length;
  INT32         TupleBytes;
  UINT64        Size;

  Cells = FdtGetProp (Fdt, Node, "reg", &Length);
  if (Cells == NULL) {
    return (Length == -FDT_ERR_NOTFOUND) ? RETURN_NOT_FOUND : RETURN_COMPROMISED_DATA;
  }

  AddressCells = FdtAddressCells (Fdt, Parent);
  SizeCells    = FdtSizeCells (Fdt, Parent);
  if ((AddressCells < 1) || (AddressCells > 2) || (SizeCells < 1) || (SizeCells > 2)) {
    return RETURN_UNSUPPORTED;
  }

  TupleBytes = (AddressCells + SizeCells) * sizeof (UINT32);
  if ((Length == 0) || ((Length % TupleBytes) != 0)) {
    return RETURN_COMPROMISED_DATA;
  }

  for (; Length > 0; Length -= TupleBytes, Cells += AddressCells + SizeCells) {
    Size = ReadCells (Cells + AddressCells, SizeCells);
    if (Size == 0) {
      continue;
    }

    if (*Count >= Capacity) {
      return RETURN_OUT_OF_RESOURCES;
    }

    Ranges[*Count].Base = ReadCells (Cells, AddressCells);
    Ranges[*Count].Size = Size;
    (*Count)++;
  }

  return RETURN_SUCCESS;
}

STATIC
BOOLEAN
NodeIsEnabled (
  IN CONST VOID  *Fdt,
  IN INT32       Node
  )
{
  CONST CHAR8  *Status;
  INT32        Length;

  Status = FdtGetProp (Fdt, Node, "status", &Length);
  if (Status == NULL) {
    return Length == -FDT_ERR_NOTFOUND;
  }

  return ((Length == sizeof ("okay")) && (CompareMem (Status, "okay", sizeof ("okay")) == 0)) ||
         ((Length == sizeof ("ok")) && (CompareMem (Status, "ok", sizeof ("ok")) == 0));
}

STATIC
RETURN_STATUS
ReadInitrd (
  IN CONST VOID          *Fdt,
  OUT A05_MEMORY_RANGE  *Range
  )
{
  CONST UINT32  *Start;
  CONST UINT32  *End;
  INT32         Node;
  INT32         StartBytes;
  INT32         EndBytes;
  UINT64        EndAddress;

  Node = FdtPathOffset (Fdt, "/chosen");
  if (Node < 0) {
    return (Node == -FDT_ERR_NOTFOUND) ? RETURN_NOT_FOUND : RETURN_COMPROMISED_DATA;
  }

  Start = FdtGetProp (Fdt, Node, "linux,initrd-start", &StartBytes);
  End   = FdtGetProp (Fdt, Node, "linux,initrd-end", &EndBytes);
  if ((Start == NULL) && (End == NULL) &&
      (StartBytes == -FDT_ERR_NOTFOUND) && (EndBytes == -FDT_ERR_NOTFOUND)) {
    return RETURN_NOT_FOUND;
  }

  if ((Start == NULL) || (End == NULL) ||
      ((StartBytes != 4) && (StartBytes != 8)) ||
      ((EndBytes != 4) && (EndBytes != 8))) {
    return RETURN_COMPROMISED_DATA;
  }

  Range->Base = ReadCells (Start, StartBytes / 4);
  EndAddress  = ReadCells (End, EndBytes / 4);
  if (EndAddress <= Range->Base) {
    return RETURN_COMPROMISED_DATA;
  }

  Range->Size = EndAddress - Range->Base;
  return RETURN_SUCCESS;
}

RETURN_STATUS
EFIAPI
A05ReadMemoryLayout (
  IN CONST VOID              *Fdt,
  IN CONST A05_MEMORY_RANGE  *Image,
  OUT A05_MEMORY_LAYOUT      *Layout
  )
{
  A05_MEMORY_RANGE  *Banks;
  A05_MEMORY_RANGE  *Excluded;
  UINTN             BankCount;
  UINTN             ExcludedCount;
  INT32             Node;
  INT32             Reserved;
  INT32             Length;
  INTN              Index;
  INTN              Entries;
  CONST CHAR8       *Type;
  RETURN_STATUS     Status;

  if ((Fdt == NULL) || (Image == NULL) || (Layout == NULL)) {
    return RETURN_INVALID_PARAMETER;
  }

  if ((FdtCheckHeader (Fdt) != 0) || (FdtTotalSize (Fdt) > A05_MAX_DTB_SIZE)) {
    return RETURN_COMPROMISED_DATA;
  }

  Banks     = Layout->Banks;
  Excluded  = Layout->Excluded;
  BankCount = 0;
  for (Node = FdtFirstSubnode (Fdt, 0); Node >= 0; Node = FdtNextSubnode (Fdt, Node)) {
    Type = FdtGetProp (Fdt, Node, "device_type", &Length);
    if ((Type == NULL) || (Length != sizeof ("memory")) ||
        (CompareMem (Type, "memory", sizeof ("memory")) != 0) || !NodeIsEnabled (Fdt, Node)) {
      continue;
    }

    Status = ReadRanges (Fdt, 0, Node, Banks, &BankCount, A05_MAX_RAM_BANKS);
    if (RETURN_ERROR (Status)) {
      return Status;
    }
  }

  if ((Node != -FDT_ERR_NOTFOUND) || (BankCount == 0)) {
    return RETURN_COMPROMISED_DATA;
  }

  Excluded[0] = *Image;
  Excluded[1].Base = (UINTN)Fdt;
  Excluded[1].Size = FdtTotalSize (Fdt);
  ExcludedCount = 2;
  Entries = FdtGetNumberOfReserveMapEntries (Fdt);
  if ((Entries < 0) || (Entries > A05_MAX_EXCLUSIONS - 3)) {
    return RETURN_COMPROMISED_DATA;
  }

  for (Index = 0; Index < Entries; Index++) {
    if (FdtGetReserveMapEntry (Fdt, Index, &Excluded[ExcludedCount].Base,
                              &Excluded[ExcludedCount].Size) != 0) {
      return RETURN_COMPROMISED_DATA;
    }

    if (Excluded[ExcludedCount].Size != 0) {
      ExcludedCount++;
    }
  }

  Reserved = FdtPathOffset (Fdt, "/reserved-memory");
  if (Reserved >= 0) {
    if ((FdtGetProp (Fdt, Reserved, "ranges", &Length) == NULL) || (Length != 0)) {
      return RETURN_UNSUPPORTED;
    }

    for (Node = FdtFirstSubnode (Fdt, Reserved); Node >= 0; Node = FdtNextSubnode (Fdt, Node)) {
      if (!NodeIsEnabled (Fdt, Node)) {
        continue;
      }

      Status = ReadRanges (Fdt, Reserved, Node, Excluded, &ExcludedCount, A05_MAX_EXCLUSIONS - 1);
      if ((Status == RETURN_NOT_FOUND) &&
          (FdtGetProp (Fdt, Node, "reusable", NULL) != NULL) &&
          (FdtGetProp (Fdt, Node, "size", NULL) != NULL) &&
          (FdtGetProp (Fdt, Node, "no-map", NULL) == NULL)) {
        continue;
      }

      if (RETURN_ERROR (Status)) {
        return Status;
      }
    }

    if (Node != -FDT_ERR_NOTFOUND) {
      return RETURN_COMPROMISED_DATA;
    }
  } else if (Reserved != -FDT_ERR_NOTFOUND) {
    return RETURN_COMPROMISED_DATA;
  }

  Status = ReadInitrd (Fdt, &Excluded[ExcludedCount]);
  if (Status == RETURN_SUCCESS) {
    ExcludedCount++;
  } else if (Status != RETURN_NOT_FOUND) {
    return Status;
  }

  Layout->BankCount     = BankCount;
  Layout->ExcludedCount = ExcludedCount;
  return RETURN_SUCCESS;
}

RETURN_STATUS
EFIAPI
A05SelectEarlyMemoryFromFdt (
  IN CONST VOID              *Fdt,
  IN CONST A05_MEMORY_RANGE  *Image,
  IN UINT64                   Size,
  OUT A05_MEMORY_RANGE       *Selected
  )
{
  A05_MEMORY_LAYOUT  Layout;
  RETURN_STATUS      Status;

  Status = A05ReadMemoryLayout (Fdt, Image, &Layout);
  if (RETURN_ERROR (Status)) {
    return Status;
  }

  return A05SelectEarlyMemory (Layout.Banks, Layout.BankCount, Layout.Excluded,
                               Layout.ExcludedCount, Size, Selected);
}
