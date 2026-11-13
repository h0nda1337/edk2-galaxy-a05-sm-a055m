#include <PiPei.h>
#include <Library/A05EarlyMemoryLib.h>
#include <Library/A05PlatformMmioLib.h>
#include <Library/ArmMmuLib.h>
#include <Library/DebugLib.h>
#include <Library/HobLib.h>
#include <Library/MemoryAllocationLib.h>

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

EFI_STATUS
EFIAPI
A05ConfigureQemuMmu (
  IN CONST VOID  *Fdt,
  IN UINT64  ImageBase,
  IN UINT32  ImageSize,
  IN UINT64  FvBase,
  IN UINT32  FvSize,
  IN BOOLEAN UseQemuMmio
  )
{
  EFI_PEI_HOB_POINTERS          Hob;
  ARM_MEMORY_REGION_DESCRIPTOR  *Map;
  UINTN                         Count;
  UINTN                         Index;
  UINTN                         Device;
  A05_PLATFORM_MMIO             Mmio;
  EFI_STATUS                    Status;

  Status = A05ReadPlatformMmio (Fdt, &Mmio);
  if ((Status == EFI_NOT_FOUND) && UseQemuMmio) {
    Mmio.GicCount = 0;
    Mmio.UartPresent[0] = FALSE;
    Mmio.UartPresent[1] = FALSE;
  } else if (EFI_ERROR (Status)) {
    return Status;
  }

  if (!UseQemuMmio && (!Mmio.UartPresent[0] || (Mmio.Uart[0].Base != 0x11002000))) {
    return EFI_UNSUPPORTED;
  }

  Count = 0;
  for (Hob.Raw = GetHobList (); !END_OF_HOB_LIST (Hob); Hob.Raw = GET_NEXT_HOB (Hob)) {
    if ((GET_HOB_TYPE (Hob) == EFI_HOB_TYPE_RESOURCE_DESCRIPTOR) &&
        (Hob.ResourceDescriptor->ResourceType == EFI_RESOURCE_SYSTEM_MEMORY)) {
      Count++;
    }
  }

  // Reuse the system RAM HOBs so firmware reservations stay out of the map.
  // Three additional entries cover the image, its read-only FV and QEMU MMIO.
  Map = AllocateZeroPool ((Count + 4 + Mmio.GicCount + ARRAY_SIZE (Mmio.Uart)) * sizeof (*Map));
  if (Map == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }

  Index = 0;
  for (Hob.Raw = GetHobList (); !END_OF_HOB_LIST (Hob); Hob.Raw = GET_NEXT_HOB (Hob)) {
    if ((GET_HOB_TYPE (Hob) == EFI_HOB_TYPE_RESOURCE_DESCRIPTOR) &&
        (Hob.ResourceDescriptor->ResourceType == EFI_RESOURCE_SYSTEM_MEMORY)) {
      Map[Index].PhysicalBase = Hob.ResourceDescriptor->PhysicalStart;
      Map[Index].VirtualBase  = Map[Index].PhysicalBase;
      Map[Index].Length       = Hob.ResourceDescriptor->ResourceLength;
      Map[Index].Attributes   = ARM_MEMORY_REGION_ATTRIBUTE_WRITE_BACK;
      Index++;
    }
  }

  if (UseQemuMmio) {
    Map[Index++] = (ARM_MEMORY_REGION_DESCRIPTOR) {
      0x08000000, 0x08000000, 0x08000000, ARM_MEMORY_REGION_ATTRIBUTE_DEVICE
    };
  }
  for (Device = 0; Device < Mmio.GicCount; Device++) {
    Map[Index++] = (ARM_MEMORY_REGION_DESCRIPTOR) {
      Mmio.Gic[Device].Base, Mmio.Gic[Device].Base, Mmio.Gic[Device].Size,
      ARM_MEMORY_REGION_ATTRIBUTE_DEVICE
    };
  }

  for (Device = 0; Device < ARRAY_SIZE (Mmio.Uart); Device++) {
    if (Mmio.UartPresent[Device]) {
      Map[Index++] = (ARM_MEMORY_REGION_DESCRIPTOR) {
        Mmio.Uart[Device].Base, Mmio.Uart[Device].Base, Mmio.Uart[Device].Size,
        ARM_MEMORY_REGION_ATTRIBUTE_DEVICE
      };
    }
  }

  // Reject DT apertures that would change the attributes of actual DRAM.
  for (Device = Count + (UseQemuMmio ? 1 : 0); Device < Index; Device++) {
    UINT64 Base = Map[Device].PhysicalBase;
    UINT64 End  = Base + Map[Device].Length;
    if (End > ImageBase && Base < ImageBase + ImageSize) {
      return EFI_COMPROMISED_DATA;
    }

    for (Hob.Raw = GetHobList (); !END_OF_HOB_LIST (Hob); Hob.Raw = GET_NEXT_HOB (Hob)) {
      if ((GET_HOB_TYPE (Hob) == EFI_HOB_TYPE_RESOURCE_DESCRIPTOR) &&
          (Base < Hob.ResourceDescriptor->PhysicalStart + Hob.ResourceDescriptor->ResourceLength) &&
          (Hob.ResourceDescriptor->PhysicalStart < End) &&
          ((Hob.ResourceDescriptor->ResourceType == EFI_RESOURCE_SYSTEM_MEMORY) ||
           (Hob.ResourceDescriptor->ResourceType == EFI_RESOURCE_MEMORY_RESERVED))) {
        return EFI_COMPROMISED_DATA;
      }
    }

    DEBUG ((DEBUG_INFO, "A05 SEC device mapping: 0x%Lx size 0x%Lx\n", Base, Map[Device].Length));
  }
  Map[Index++] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    ImageBase, ImageBase, ImageSize, ARM_MEMORY_REGION_ATTRIBUTE_WRITE_BACK
  };
  Map[Index] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    FvBase, FvBase, FvSize, ARM_MEMORY_REGION_ATTRIBUTE_WRITE_BACK_RO
  };

  return ArmConfigureMmu (Map, NULL, NULL);
}
