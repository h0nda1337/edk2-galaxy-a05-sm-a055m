/* Own QEMU-only harness. These RAM addresses are NOT A05 load addresses. */
.arch armv8-a
.section .text.start, "ax", %progbits
.global _start
_start:
    ldr x0, =0x40400000
    mov sp, x0
    mov x19, #19
    mov x20, #20
    mov x21, #21
    mov x22, #22
    mov x23, #23
    mov x24, #24
    mov x25, #25
    mov x26, #26
    mov x27, #27
    mov x28, #28
    mov x29, #29
    ldr x0, =report
    mov x1, #64
    bl A05Probe64
.Lreturned:
    cbnz x0, fail
    ldr x2, =report
    ldr x0, [x2, #24]
    ldr x1, =A05Probe64
    cmp x0, x1
    b.ne fail
    ldr x0, [x2, #40]
    adr x1, .Lreturned
    cmp x0, x1
    b.ne fail
    ldr x0, [x2, #32]
    ldr x1, =0x40400000
    cmp x0, x1
    b.ne fail
    ldr x3, =shadow
    mov x1, #8
.Lcopy:
    ldr x0, [x2], #8
    str x0, [x3], #8
    subs x1, x1, #1
    b.ne .Lcopy
    mov x0, #0
    mov x1, #64
    bl A05Probe64
    cmn x0, #1
    b.ne fail
    ldr x0, =report
    mov x1, #63
    bl A05Probe64
    cmn x0, #1
    b.ne fail
    ldr x0, =report
    add x0, x0, #1
    mov x1, #64
    bl A05Probe64
    cmn x0, #1
    b.ne fail
    ldr x2, =report
    ldr x3, =shadow
    mov x1, #8
.Lcompare:
    ldr x0, [x2], #8
    ldr x9, [x3], #8
    cmp x0, x9
    b.ne fail
    subs x1, x1, #1
    b.ne .Lcompare
    cmp x19, #19
    b.ne fail
    cmp x20, #20
    b.ne fail
    cmp x21, #21
    b.ne fail
    cmp x22, #22
    b.ne fail
    cmp x23, #23
    b.ne fail
    cmp x24, #24
    b.ne fail
    cmp x25, #25
    b.ne fail
    cmp x26, #26
    b.ne fail
    cmp x27, #27
    b.ne fail
    cmp x28, #28
    b.ne fail
    cmp x29, #29
    b.ne fail
    mov x0, sp
    ldr x1, =0x40400000
    cmp x0, x1
    b.ne fail
    mov x0, #1
    ldr x1, =open_parameters
    hlt #0xf000
    tbnz x0, #63, fail
    ldr x1, =write_parameters
    str x0, [x1]
    mov x0, #5
    hlt #0xf000
    cbnz x0, fail
    mov x0, #2
    ldr x1, =write_parameters
    hlt #0xf000
    mov x0, #4
    ldr x1, =success_message
    hlt #0xf000
    mov x0, #32
    ldr x1, =exit_success
    hlt #0xf000
    b .
fail:
    mov x0, #4
    ldr x1, =failure_message
    hlt #0xf000
    mov x0, #32
    ldr x1, =exit_failure
    hlt #0xf000
    b .
.ltorg
.section .rodata
filename: .asciz "report.bin"
success_message: .asciz "A05_PROBE64_OK\n"
failure_message: .asciz "A05_PROBE64_FAIL\n"
.balign 8
open_parameters: .quad filename, 5, 10
exit_success: .quad 0x20026, 0
exit_failure: .quad 0x20026, 1
.section .data
.balign 8
write_parameters: .quad 0, report, 64
.section .bss
.balign 8
report: .space 64
shadow: .space 64
