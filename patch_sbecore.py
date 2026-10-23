#!/usr/bin/env python3
"""Route the SB Live! DOS driver's emulated MPU-401 (port 330) to the card's real MIDI out instead of its wavetable.

Creative's DOS driver for the SB Live! / Audigy (SBEINIT 5.00) emulates an MPU-401 at 330h/331h and plays whatever
the game sends on the EMU10K1's internal synth. The card also has a real MPU-401-style UART at I/O base + 18h/19h
(the MIDI out on the gameport, e.g. through a "SB MIDI" adapter to a Sound Canvas or an MU-series module), but
SBEINIT offers no option to use it. This patch rewrites two port-trap handlers in SBECORE.BIN:

  * data port 330h write -> wait until the UART can accept a byte, write it to base+18h (MUDATA), return;
  * command port 331h write -> forward the byte to base+19h (MUCMD), then run Creative's original command
    emulation, so games still get their 0FEh ACK after a reset (0FFh) and UART-mode (3Fh) command.

The handlers run inside the driver's port trap with CL = the byte written, ESI = card structure,
word [ESI+0Ch] = card I/O base; they leave through the driver's common exit at 1A4h.

Usage:  python3 patch_sbecore.py SBECORE.BIN [OUTPUT]     (default: patch in place, keeping SBECORE.BIN.bak)
"""
import shutil
import struct
import sys

SIZE = 272064
HANDLERS = (0x252, 0x282, 0x33d, 0x34c)   # port-trap dispatch table at 1C54h: 330 read, 330 write, 331 read, 331 write
EXIT, CMD_ORIG, CMD_EMUL = 0x1a4, 0x353, 0x388


def rel32(at: int, target: int, length: int = 5) -> bytes:
    return struct.pack('<i', target - (at + length))


def wait_ready() -> bytes:
    # DX = base+19h; spin while MUSTAT bit 6 (output busy) is set, at most 20000h polls
    return bytes.fromhex('668b560c' '80c219' 'bb00000200' 'ec' 'a840' '7403' '4b' '75f8')


def build() -> tuple[bytes, int, bytes]:
    data = wait_ready() + bytes.fromhex('feca' '8ac1' 'ee')          # dec dl -> base+18h ; mov al,cl ; out dx,al
    data += b'\xe9' + rel32(0x282 + len(data), EXIT)
    cmd_at = 0x282 + len(data)
    cmd = wait_ready() + bytes.fromhex('8ac1' 'ee' '80f9ff')          # mov al,cl ; out dx,al ; cmp cl,0FFh
    cmd += b'\x0f\x84' + rel32(cmd_at + len(cmd), CMD_ORIG, 6)       # reset -> Creative's reset/ACK path
    cmd += b'\xe9' + rel32(cmd_at + len(cmd), CMD_EMUL)               # other commands -> original emulation
    assert cmd_at + len(cmd) <= 0x33d
    return data, cmd_at, cmd


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) == 3 else src
    d = bytearray(open(src, 'rb').read())
    if len(d) != SIZE or struct.unpack_from('<4I', d, 0x1c54) != HANDLERS:
        raise SystemExit(f'{src}: not SBECORE.BIN from SBEINIT 5.00 ({SIZE} bytes)')
    data, cmd_at, cmd = build()
    hook = b'\xe9' + rel32(0x34c, cmd_at) + b'\x90\x90'
    if d[0x282:cmd_at + len(cmd)] == data + cmd and d[0x34c:0x353] == hook:
        print('already patched'); return
    if d[0x34c:0x353] != bytes.fromhex('80f9ff7402eb35'):
        raise SystemExit('unexpected code in the 331h write handler')
    d[0x282:cmd_at + len(cmd)] = data + cmd
    d[0x34c:0x353] = hook
    if dst == src:
        shutil.copyfile(src, src + '.bak')
    open(dst, 'wb').write(d)
    print(f'330h data handler at 282h-{cmd_at:x}h, 331h command handler at {cmd_at:x}h-{cmd_at + len(cmd):x}h; written {dst}')


if __name__ == '__main__':
    main()
