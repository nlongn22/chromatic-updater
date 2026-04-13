# Setup Guide

This guide is for running the host-side Cart Clinic tools without repeating the reverse-engineering scratch work.

## Requirements

- macOS
- Python 3
- MRUpdater installed or mounted from the DMG
- A ModRetro Chromatic connected over USB
- A GB/GBC cartridge inserted

You do not need the temporary PyInstaller extraction directories, converted DMG images, or old files in `/tmp`.

## 1. Make MRUpdater Available

Use either option:

- Install MRUpdater to `/Applications/MRUpdater.app`
- Mount `MRUpdater.dmg` so `/Volumes/MRUpdater/MRUpdater.app` exists

The tools use MRUpdater's bundled `openFPGALoader` binary to load Cart Clinic mode into the Chromatic FPGA SRAM.

## 2. Cache Cart Clinic Firmware

Open MRUpdater once and go to the Cart Clinic tab. This lets MRUpdater download/cache the Cart Clinic firmware package.

After the tab has loaded, quit MRUpdater before running these tools.

The helper searches for the cached firmware zip automatically. If auto-detection fails, pass it explicitly:

```bash
python3 tools/cartclinic_enter_mode.py --firmware-zip /path/to/v1.1.zip
```

You can also pass an already-extracted FPGA SRAM image:

```bash
python3 tools/cartclinic_enter_mode.py --firmware /path/to/cart_clinic_250412.fs
```

## 3. Check USB Devices

The correctly connected Chromatic exposes both:

- `Chromatic - Player 01`
- `GWU2X`

The serial port usually looks like:

```bash
ls /dev/cu.usbmodem* /dev/tty.usbmodem*
```

Example:

```text
/dev/cu.usbmodem0123456783
/dev/tty.usbmodem0123456783
```

Use the `/dev/cu.usbmodem...` path in commands below.

## 4. Enter Cart Clinic Mode

Load the temporary Cart Clinic FPGA image into SRAM:

```bash
python3 tools/cartclinic_enter_mode.py
```

This mirrors MRUpdater's setup step:

```text
openFPGALoader --cable gwu2x --write-sram --skip-reset cart_clinic_*.fs
```

It writes FPGA SRAM only. It does not write cartridge data, FPGA flash, or MCU flash.

## 5. Read Cartridge Header

```bash
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --timeout 5 --dump-header ~/Downloads/gb_header.bin
```

Expected signs of success:

```text
Loopback: ok
DetectCart: inserted=True removed=False
header_checksum: 0x.. (ok)
```

## 6. Back Up Save RAM

After Cart Clinic mode is loaded:

```bash
python3 tools/cartclinic_backup_save.py --port /dev/cu.usbmodemXXXX
```

By default, the backup is written to:

```text
~/Downloads/<cart_title>.sav
```

The save backup tool supports common MBC1, MBC2, MBC3, and MBC5 GB/GBC cartridges. It sends MBC control-register writes to enable and bank external RAM, but it does not write save RAM contents, erase flash, restore saves, or modify cartridge ROM.

## 7. Exit Cart Clinic Mode

When you are done reading or backing up saves, reset the FPGA:

```bash
python3 tools/cartclinic_exit_mode.py
```

This wraps:

```text
openFPGALoader --cable gwu2x --reset
```

Cart Clinic was loaded into FPGA SRAM, so it is temporary. Resetting the FPGA, power-cycling, or unplugging after commands complete clears it. Do not unplug while `cartclinic_enter_mode.py` is loading SRAM or while a read/backup command is actively running.

## Troubleshooting

If every serial command times out with an empty reply, Cart Clinic mode is probably not loaded. Run `cartclinic_enter_mode.py` again.

If `cartclinic_enter_mode.py` reports no cable or no USB devices, replug the Chromatic and confirm `GWU2X` appears in USB devices.

If MRUpdater is open while these tools run, it may hold or consume the same serial/device endpoints. Quit MRUpdater after it has cached the Cart Clinic firmware.
