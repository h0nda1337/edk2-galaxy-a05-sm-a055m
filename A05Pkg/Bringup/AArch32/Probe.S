/* Own AArch32 probe. ABI: r0=report, r1=capacity. Returns 0 or -1.
 * Caller must already provide valid mapped RAM and a valid return address.
 * Only r0-r3/r12 and condition flags are clobbered; no stack is used.
 */
.syntax unified
.arch armv7-a
.arm
.section .text.probe, "ax", %progbits
.balign 4
.global A05Probe32
.type A05Probe32, %function
A05Probe32:
    mrs     r12, cpsr
    cmp     r0, #0
    beq     .Linvalid
    cmp     r1, #64
    blo     .Linvalid
    tst     r0, #7
    bne     .Linvalid
    mov     r3, #0
    str     r3, [r0, #12]
    movw    r2, #0x3041
    movt    r2, #0x5035
    str     r2, [r0, #0]
    mov     r2, #1
    str     r2, [r0, #4]
    mov     r2, #32
    str     r2, [r0, #8]
    str     r12, [r0, #16]
    str     r3, [r0, #20]
    adr     r2, A05Probe32
    str     r2, [r0, #24]
    str     r3, [r0, #28]
    mov     r2, sp
    str     r2, [r0, #32]
    str     r3, [r0, #36]
    str     lr, [r0, #40]
    str     r3, [r0, #44]
    str     r3, [r0, #48]
    str     r3, [r0, #52]
    mov     r2, #64
    str     r2, [r0, #56]
    str     r3, [r0, #60]
    dmb     sy
    mov     r2, #1
    str     r2, [r0, #12]
    dmb     sy
    mov     r0, #0
    bx      lr
.Linvalid:
    mvn     r0, #0
    bx      lr
.size A05Probe32, .-A05Probe32
