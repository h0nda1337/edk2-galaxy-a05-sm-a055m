#include <Library/A05EarlyMemoryLib.h>

#define A05_PAGE_MASK  4095ULL

STATIC
BOOLEAN
RangeIsValid (
  IN CONST A05_MEMORY_RANGE  *Range
  )
{
  return (Range->Size != 0) && (Range->Base <= MAX_UINT64 - Range->Size);
}

RETURN_STATUS
EFIAPI
A05SelectEarlyMemory (
  IN CONST A05_MEMORY_RANGE  *Banks,
  IN UINTN                   BankCount,
  IN CONST A05_MEMORY_RANGE  *Excluded OPTIONAL,
  IN UINTN                   ExcludedCount,
  IN UINT64                  Size,
  OUT A05_MEMORY_RANGE       *Selected
  )
{
  UINTN    Bank;
  UINTN    Index;
  UINT64   End;
  UINT64   Start;
  UINT64   NextEnd;
  UINT64   BestBase;
  BOOLEAN  Found;

  if ((Banks == NULL) || (BankCount == 0) || (Selected == NULL) ||
      ((Excluded == NULL) && (ExcludedCount != 0)) ||
      (Size == 0) || ((Size & A05_PAGE_MASK) != 0)) {
    return RETURN_INVALID_PARAMETER;
  }

  for (Index = 0; Index < ExcludedCount; Index++) {
    if (!RangeIsValid (&Excluded[Index])) {
      return RETURN_COMPROMISED_DATA;
    }
  }

  Found    = FALSE;
  BestBase = 0;
  for (Bank = 0; Bank < BankCount; Bank++) {
    if (!RangeIsValid (&Banks[Bank])) {
      return RETURN_COMPROMISED_DATA;
    }

    End = (Banks[Bank].Base + Banks[Bank].Size) & ~A05_PAGE_MASK;
    while ((End >= Banks[Bank].Base) && (End - Banks[Bank].Base >= Size)) {
      Start   = End - Size;
      NextEnd = End;
      for (Index = 0; Index < ExcludedCount; Index++) {
        if ((Excluded[Index].Base < NextEnd) &&
            (Start < Excluded[Index].Base + Excluded[Index].Size)) {
          NextEnd = Excluded[Index].Base & ~A05_PAGE_MASK;
        }
      }

      if (NextEnd == End) {
        if (!Found || (Start > BestBase)) {
          Found    = TRUE;
          BestBase = Start;
        }

        break;
      }

      End = NextEnd;
    }
  }

  if (!Found) {
    return RETURN_OUT_OF_RESOURCES;
  }

  Selected->Base = BestBase;
  Selected->Size = Size;
  return RETURN_SUCCESS;
}
