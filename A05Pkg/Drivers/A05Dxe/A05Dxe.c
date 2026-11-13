#include <Uefi.h>
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
  SerialPortWrite (Message, sizeof (Message) - 1);
  return EFI_SUCCESS;
}
