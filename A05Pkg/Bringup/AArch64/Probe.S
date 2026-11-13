/* Own AArch64 probe. ABI: x0=report, x1=capacity. Returns 0 or -1.
 * Requires EL1 or above: CurrentEL and DAIF are architectural register reads.
 * Only caller-saved x0-x5/x9-x12 and flags are clobbered; no stack is used.
 */
.arch armv8-a
.section .text.probe, "ax", %progbits
.balign 4
.global A05Probe64
.type A05Probe64, %function
A05Probe64:
    mrs     x9, CurrentEL
    mrs     x10, DAIF
    mov     x11, sp
    adr     x12, A05Probe64
    cbz     x0, .Linvalid
    cmp     x1, #64
    b.lo    .Linvalid
    tst     x0, #7
    b.ne    .Linvalid
    str     wzr, [x0, #12]
    movz    w2, #0x3041
    movk    w2, #0x5035, lsl #16
    str     w2, [x0, #0]
    mov     w2, #1
    str     w2, [x0, #4]
    mov     w2, #64
    str     w2, [x0, #8]
    str     x9, [x0, #16]
    str     x12, [x0, #24]
    str     x11, [x0, #32]
    str     x30, [x0, #40]
    str     x10, [x0, #48]
    mov     x2, #64
    str     x2, [x0, #56]
    dmb     sy
    mov     w2, #1
    str     w2, [x0, #12]
    dmb     sy
    mov     x0, #0
    ret
.Linvalid:
    mov     x0, #-1
    ret
.size A05Probe64, .-A05Probe64
