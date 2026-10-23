# sblive-sbeinit-external-midi

A patch for Creative's **SB Live! / Audigy DOS driver (SBEINIT 5.00)**. It sends the music that DOS games write to the
emulated MPU-401 at port 330h out of the card's **real MIDI port**, the gameport MIDI out, instead of playing it on
the EMU10K1's built-in wavetable. With it, a Roland Sound Canvas, a Yamaha MU-series module or any other external
General MIDI synth plays the music of games that only know "General MIDI / MPU-401 at 330".

## The problem

The SB Live! has a hardware MIDI UART at *card I/O base + 18h* (data) and *+ 19h* (command/status). On a real
MPU-401 adapter those would be 330h and 331h. With a gameport MIDI adapter (for example the TexElec "SB MIDI &
Joystick" adapter), this UART drives an external synth.

In pure DOS:

- `SBEINIT` emulates an MPU-401 at 330h, but always plays what it gets on the internal wavetable synth. It has no
  option to route it to the UART.
- Its SB-MIDI emulation at 220h sends nothing to the gameport either.
- Only programs that accept a free-form port (DOSMid: `dosmid /mpu=d418`) can reach the UART directly. Games only
  offer 300h to 330h.

## The fix

`SBECORE.BIN`, the resident core that SBEINIT loads, dispatches its port traps through a table at file offset 1C54h
(330h read, 330h write, 331h read, 331h write). The patch rewrites two of the handlers in place:

- **Write to 330h (data):** wait until the UART's output-busy bit (status bit 6) clears, with a poll limit, then
  write the byte to *base + 18h*.
- **Write to 331h (command):** forward the byte to *base + 19h*, then continue in Creative's original command
  emulation. A game that sends `FFh` (reset) or `3Fh` (UART mode) still gets its `FEh` acknowledge from the
  emulated port, as before.

The handlers run inside the driver's trap with `CL` = the byte written, `ESI` = the card structure and
`word [ESI+0Ch]` = the card's I/O base, so the patch follows the card if the PCI slot (and thus the base) changes.
The new code occupies 282h to 2C5h, the space of the old 330h write handler, and the 331h handler at 34Ch gets a
jump to it. Reads of 330h/331h are left to the emulation.

| File | Size | MD5 |
|---|---|---|
| `SBECORE.BIN` from SBEINIT 5.00 (Audigy DOS driver, also used for the SB Live!) | 272064 | `3d6c0fcd883bfcd89a89053abcac31bd` |
| after the patch | 272064 | `6d0d97dbbaa41becde3f47ef8db42164` |

## Usage

Keep an unpatched driver for the internal synth, and make a patched copy for external MIDI:

```
xcopy D:\DOS\SBLIVE D:\DOS\SBLIVEX /s
python3 patch_sbecore.py SBLIVEX/SBECORE.BIN        # patches in place, keeps SBECORE.BIN.bak
```

Then load the driver from the copy, for example from a boot-menu entry in `AUTOEXEC.BAT`:

```
SET CTSYN=D:\DOS\SBLIVEX
D:\DOS\SBLIVEX\SBEINIT.COM
```

`CTSYN.INI` stays as it was (`MPUPort=330`). In the games, choose *General MIDI* / *Roland Sound Canvas* /
*MPU-401* at port 330h. Sound effects still go through the Sound Blaster emulation as usual.

The script checks the size, the dispatch table and the exact handler bytes, and refuses any other build. Running
it again on a patched file changes nothing.

## Tested

- Real hardware: SB Live! SB0060 (I/O base D400h), TexElec SB MIDI adapter on the gameport, Roland SC-8850 and
  Yamaha MU1000. Core 2 Extreme X6800, DOS 7.1, JemmEx 5.87 with the `SB` option and EMS.
- **Music on the external module, effects through the SB16 emulation:**
  - Duke Nukem 3D Atomic, Blood, Rise of the Triad (Apogee Sound System);
  - DOOM, DOOM II, Heretic, Hexen, Hexen: Deathkings;
  - Descent, with the separate HMI driver fix: <https://github.com/xphileby/hmi-sos-mpu401-fix>;
  - DOSMid with `/mpu=330`.

## Notes

- If your setup cannot load SBEINIT, the same idea exists for SBEMU: <https://github.com/crazii/SBEMU/pull/217>.
- Creative's files are not included here. Use the driver you already have.
