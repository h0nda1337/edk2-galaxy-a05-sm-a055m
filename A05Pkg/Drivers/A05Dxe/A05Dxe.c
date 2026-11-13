#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/HobLib.h>
#include <Library/A05EarlyMemoryLib.h>
#include <Library/SerialPortLib.h>

extern EFI_GUID gA05DiagnosticFramebufferGuid;

EFI_STATUS
EFIAPI
A05DxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  STATIC UINT8  Message[] = "A05 EDK II DXE driver dispatched\r\n";
  VOID                         *Hob;
  CONST A05_MEMORY_RANGE        *Range;
  volatile UINT32              *Pixel;
  UINTN                         Index;

  (VOID)ImageHandle;
  (VOID)SystemTable;
  // No-op signature for instruction tracing on machines without the UART.
  __asm__ __volatile__ ("movz xzr, #0xa05d\n\tmovk xzr, #0xd0e1, lsl #16");
  Hob = GetFirstGuidHob (&gA05DiagnosticFramebufferGuid);
  if ((Hob != NULL) && (GET_GUID_HOB_DATA_SIZE (Hob) == sizeof (A05_MEMORY_RANGE))) {
    Range = GET_GUID_HOB_DATA (Hob);
    Pixel = (volatile UINT32 *)(UINTN)Range->Base;
    // Alternating grayscale bands remain visible across common pixel formats.
    for (Index = 0; Index < SIZE_1MB / sizeof (*Pixel); Index++) {
      Pixel[Index] = ((Index & BIT14) == 0) ? MAX_UINT32 : 0;
    }
    MemoryFence ();
  }
  SerialPortWrite (Message, sizeof (Message) - 1);
  // The diagnostic volume intentionally has no BDS architectural protocol.
  CpuDeadLoop ();
  return EFI_SUCCESS;
}
