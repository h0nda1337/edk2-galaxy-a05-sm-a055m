/* Own bring-up report ABI. No board addresses or vendor implementation code. */
#ifndef A05_PROBE_H
#define A05_PROBE_H

#define A05_PROBE_MAGIC       0x50353041U /* bytes A05P */
#define A05_PROBE_VERSION     1U
#define A05_PROBE_SIZE        64U

/* Little endian, 8-byte aligned. Caller supplies a writable 64-byte buffer.
 * RegisterStatus is CPSR on AArch32, CurrentEL on AArch64.
 * AuxiliaryStatus is zero on AArch32, DAIF on AArch64.
 * Completed is written last. No MMIO is touched by either probe.
 */
typedef struct {
  unsigned int Magic;
  unsigned int Version;
  unsigned int ArchitectureBits;
  unsigned int Completed;
  unsigned long long RegisterStatus;
  unsigned long long EntryPc;
  unsigned long long EntrySp;
  unsigned long long ReturnAddress;
  unsigned long long AuxiliaryStatus;
  unsigned long long RecordSize;
} A05_PROBE_REPORT;

#endif
