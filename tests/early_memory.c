#include <Library/A05EarlyMemoryLib.h>

int main (void)
{
  CONST A05_MEMORY_RANGE Banks[] = {
    { 0x40000000, 0x04000000 },
    { 0x100000000ULL, 0x08000000 },
  };
  CONST A05_MEMORY_RANGE Reserved[] = {
    { 0x106000000ULL, 0x01000000 },
    { 0x106800000ULL, 0x01800000 },
    { 0x105FFF123ULL, 0x1000 },
  };
  CONST A05_MEMORY_RANGE Bad[] = { { MAX_UINT64 - 2, 4 } };
  A05_MEMORY_RANGE Out = { 0, 0 };

  if (A05SelectEarlyMemory (Banks, 2, Reserved, 3, 0x02000000, &Out) != RETURN_SUCCESS ||
      Out.Base != 0x103FFF000ULL || Out.Size != 0x02000000) {
    return 1;
  }

  if (A05SelectEarlyMemory (Banks, 2, Reserved, 3, 0x08000000, &Out) != RETURN_OUT_OF_RESOURCES ||
      Out.Base != 0x103FFF000ULL) {
    return 2;
  }

  if (A05SelectEarlyMemory (Banks, 2, Bad, 1, 0x1000, &Out) != RETURN_COMPROMISED_DATA) {
    return 3;
  }

  if (A05SelectEarlyMemory (Banks, 2, NULL, 0, 0x08000000, &Out) != RETURN_SUCCESS ||
      Out.Base != 0x100000000ULL) {
    return 4;
  }

  return 0;
}
