/* Own QEMU-only harness. These RAM addresses are NOT A05 load addresses. */
.syntax unified
.arch armv7-a
.arm
.section .text.start, "ax", %progbits
.global _start
_start:
    ldr sp, =0x40400000
    mov r4, #4
    mov r5, #5
    mov r6, #6
    mov r7, #7
    mov r8, #8
    mov r9, #9
    mov r10, #10
    mov r11, #11
    ldr r0, =report
    mov r1, #64
    bl A05Probe32
.Lreturned:
    cmp r0, #0
    bne fail
    ldr r2, =report
    ldr r0, [r2, #24]
    ldr r1, =A05Probe32
    cmp r0, r1
    bne fail
    ldr r0, [r2, #40]
    adr r1, .Lreturned
    cmp r0, r1
    bne fail
    ldr r0, [r2, #32]
    ldr r1, =0x40400000
    cmp r0, r1
    bne fail
    ldr r3, =shadow
    mov r1, #16
.Lcopy:
    ldr r0, [r2], #4
    str r0, [r3], #4
    subs r1, r1, #1
    bne .Lcopy
    mov r0, #0
    mov r1, #64
    bl A05Probe32
    cmn r0, #1
    bne fail
    ldr r0, =report
    mov r1, #63
    bl A05Probe32
    cmn r0, #1
    bne fail
    ldr r0, =report
    add r0, r0, #1
    mov r1, #64
    bl A05Probe32
    cmn r0, #1
    bne fail
    ldr r2, =report
    ldr r3, =shadow
    mov r1, #16
.Lcompare:
    ldr r0, [r2], #4
    ldr r12, [r3], #4
    cmp r0, r12
    bne fail
    subs r1, r1, #1
    bne .Lcompare
    cmp r4, #4
    bne fail
    cmp r5, #5
    bne fail
    cmp r6, #6
    bne fail
    cmp r7, #7
    bne fail
    cmp r8, #8
    bne fail
    cmp r9, #9
    bne fail
    cmp r10, #10
    bne fail
    cmp r11, #11
    bne fail
    mov r0, sp
    ldr r1, =0x40400000
    cmp r0, r1
    bne fail
    mov r0, #1
    ldr r1, =open_parameters
    svc #0x123456
    cmp r0, #0
    blt fail
    ldr r1, =write_parameters
    str r0, [r1]
    mov r0, #5
    svc #0x123456
    cmp r0, #0
    bne fail
    mov r0, #2
    ldr r1, =write_parameters
    svc #0x123456
    mov r0, #4
    ldr r1, =success_message
    svc #0x123456
    mov r0, #32
    ldr r1, =exit_success
    svc #0x123456
    b .
fail:
    mov r0, #4
    ldr r1, =failure_message
    svc #0x123456
    mov r0, #32
    ldr r1, =exit_failure
    svc #0x123456
    b .
.ltorg
.section .rodata
filename: .asciz "report.bin"
success_message: .asciz "A05_PROBE32_OK\n"
failure_message: .asciz "A05_PROBE32_FAIL\n"
.balign 4
open_parameters: .word filename, 5, 10
exit_success: .word 0x20026, 0
exit_failure: .word 0x20026, 1
.section .data
.balign 4
write_parameters: .word 0, report, 64
.section .bss
.balign 8
report: .space 64
shadow: .space 64
