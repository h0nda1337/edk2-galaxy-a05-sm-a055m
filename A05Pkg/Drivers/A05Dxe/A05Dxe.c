#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/SerialPortLib.h>

EFI_STATUS
EFIAPI
A05DxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  STATIC UINT8  Message[] = "A05 EDK II DXE reached\r\n";

  (VOID)ImageHandle;
  (VOID)SystemTable;
  // No-op signature for instruction tracing on machines without the UART.
  __asm__ __volatile__ ("movz xzr, #0xa05d\n\tmovk xzr, #0xd0e0, lsl #16");
  SerialPortWrite (Message, sizeof (Message) - 1);
  // The diagnostic volume intentionally has no BDS architectural protocol.
  CpuDeadLoop ();
  return EFI_SUCCESS;
}
