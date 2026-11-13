#include <PiPei.h>
#include <Library/A05EarlyMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/HobLib.h>

#define RAM_ATTRIBUTES  (EFI_RESOURCE_ATTRIBUTE_PRESENT | EFI_RESOURCE_ATTRIBUTE_INITIALIZED | \
                         EFI_RESOURCE_ATTRIBUTE_WRITE_BACK_CACHEABLE | EFI_RESOURCE_ATTRIBUTE_TESTED)

EFI_STATUS
EFIAPI
A05BuildMemoryHobs (
  IN CONST VOID  *Fdt,
  IN UINT64      ImageBase,
  IN UINT32      ImageSize
  )
{
  A05_MEMORY_LAYOUT  Layout;
  A05_MEMORY_RANGE   Image;
  EFI_STATUS         Status;
  UINTN              Bank;
  UINTN              Index;
  UINT64             Cursor;
  UINT64             End;
  UINT64             Next;
  UINT64             Low;
  UINT64             High;
  BOOLEAN            Reserved;

  Image.Base = ImageBase;
  Image.Size = ImageSize;
  Status = A05ReadMemoryLayout (Fdt, &Image, &Layout);
  if (EFI_ERROR (Status)) {
    return Status;
  }

  for (Index = 0; Index < Layout.ExcludedCount; Index++) {
    Low  = Layout.Excluded[Index].Base;
    High = Layout.Excluded[Index].Size;
    if ((High == 0) || (Low > MAX_UINT64 - High) ||
        (Low + High > MAX_UINT64 - EFI_PAGE_MASK)) {
      return EFI_COMPROMISED_DATA;
    }

    Layout.Excluded[Index].Base = Low & ~((UINT64)EFI_PAGE_MASK);
    Layout.Excluded[Index].Size = ALIGN_VALUE (Low + High, EFI_PAGE_SIZE) -
                                  Layout.Excluded[Index].Base;
  }

  for (Bank = 0; Bank < Layout.BankCount; Bank++) {
    Low  = Layout.Banks[Bank].Base;
    High = Layout.Banks[Bank].Size;
    if (((Low | High) & EFI_PAGE_MASK) != 0 || (Low > MAX_UINT64 - High)) {
      return EFI_COMPROMISED_DATA;
    }

    End = Low + High;
    for (Index = 0; Index < Bank; Index++) {
      if ((Layout.Banks[Index].Base < End) &&
          (Low < Layout.Banks[Index].Base + Layout.Banks[Index].Size)) {
        return EFI_COMPROMISED_DATA;
      }
    }
  }

  for (Bank = 0; Bank < Layout.BankCount; Bank++) {
    Cursor = Layout.Banks[Bank].Base;
    End    = Cursor + Layout.Banks[Bank].Size;
    while (Cursor < End) {
      // Each boundary ends a span of pages with the same reservation status.
      Next     = End;
      Reserved = FALSE;
      for (Index = 0; Index < Layout.ExcludedCount; Index++) {
        Low  = Layout.Excluded[Index].Base;
        High = Low + Layout.Excluded[Index].Size;
        if ((Low <= Cursor) && (Cursor < High)) {
          Reserved = TRUE;
          Next     = MIN (Next, High);
        } else if (Low > Cursor) {
          Next = MIN (Next, Low);
        }
      }

      if (Reserved) {
        BuildResourceDescriptorHob (
          EFI_RESOURCE_MEMORY_RESERVED,
          EFI_RESOURCE_ATTRIBUTE_PRESENT | EFI_RESOURCE_ATTRIBUTE_INITIALIZED,
          Cursor,
          Next - Cursor
          );
        DEBUG ((DEBUG_INFO, "A05 reserved RAM HOB: 0x%Lx size 0x%Lx\n", Cursor, Next - Cursor));
      } else {
        BuildResourceDescriptorHob (EFI_RESOURCE_SYSTEM_MEMORY, RAM_ATTRIBUTES, Cursor, Next - Cursor);
      }

      Cursor = Next;
    }
  }

  return EFI_SUCCESS;
}
