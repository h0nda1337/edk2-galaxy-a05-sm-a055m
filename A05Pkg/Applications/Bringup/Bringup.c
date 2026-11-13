/* Own UEFI bring-up application using only official EDK2 interface headers.
 * This is an application for an existing UEFI environment, not an A05 ROM.
 */
#include <Uefi.h>

EFI_STATUS
EFIAPI
UefiMain (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  (VOID)ImageHandle;
  if ((SystemTable == NULL) || (SystemTable->ConOut == NULL) ||
      (SystemTable->ConOut->OutputString == NULL)) {
    return EFI_INVALID_PARAMETER;
  }

  return SystemTable->ConOut->OutputString (
                               SystemTable->ConOut,
                               L"A05 UEFI bring-up: application entry reached.\r\n"
                               L"Board initialization and hardware handoff remain unverified.\r\n"
                               );
}
