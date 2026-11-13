#include <Base.h>
#include <Library/IoLib.h>
#include <Library/SerialPortLib.h>

// The loader owns clocks, pinmux and baud rate. Only transmit using its setup.
#define UART_BASE      0x11002000
#define UART_LCR       (UART_BASE + 0x0C)
#define UART_LSR       (UART_BASE + 0x14)
#define UART_TX        UART_BASE
#define UART_TIMEOUT   100000U

RETURN_STATUS EFIAPI SerialPortInitialize (VOID)
{
  return RETURN_SUCCESS;
}

UINTN EFIAPI SerialPortWrite (IN UINT8 *Buffer, IN UINTN NumberOfBytes)
{
  UINTN  Index;
  UINTN  Timeout;

  if ((MmioRead32 (UART_LCR) & BIT7) != 0) {
    return 0;
  }

  for (Index = 0; Index < NumberOfBytes; Index++) {
    for (Timeout = 0; Timeout < UART_TIMEOUT; Timeout++) {
      if ((MmioRead32 (UART_LSR) & BIT5) != 0) {
        break;
      }
    }

    if (Timeout == UART_TIMEOUT) {
      break;
    }

    MmioWrite32 (UART_TX, Buffer[Index]);
  }

  return Index;
}

UINTN EFIAPI SerialPortRead (OUT UINT8 *Buffer, IN UINTN NumberOfBytes)
{
  (VOID)Buffer;
  (VOID)NumberOfBytes;
  return 0;
}

BOOLEAN EFIAPI SerialPortPoll (VOID)
{
  return FALSE;
}

RETURN_STATUS EFIAPI SerialPortSetControl (IN UINT32 Control)
{
  (VOID)Control;
  return RETURN_UNSUPPORTED;
}

RETURN_STATUS EFIAPI SerialPortGetControl (OUT UINT32 *Control)
{
  (VOID)Control;
  return RETURN_UNSUPPORTED;
}

RETURN_STATUS EFIAPI SerialPortSetAttributes (
  IN OUT UINT64 *BaudRate, IN OUT UINT32 *ReceiveFifoDepth,
  IN OUT UINT32 *Timeout, IN OUT EFI_PARITY_TYPE *Parity,
  IN OUT UINT8 *DataBits, IN OUT EFI_STOP_BITS_TYPE *StopBits
  )
{
  (VOID)BaudRate;
  (VOID)ReceiveFifoDepth;
  (VOID)Timeout;
  (VOID)Parity;
  (VOID)DataBits;
  (VOID)StopBits;
  return RETURN_UNSUPPORTED;
}
