# Cart Clinic Reverse-Engineering Notes

Date: 2026-04-13

## Context

The local repository is Chromatic MCU firmware. It exposes an ESP32 console and an MCU-to-FPGA management UART, but it is not the MRUpdater desktop application.

The MRUpdater macOS DMG in `~/Downloads/MRUpdater.dmg` is a PyInstaller app:

- bundle id: `com.modretro.mrupdater`
- bundle version: `v1.7.0`
- PyInstaller Python version: 3.10
- useful embedded modules:
  - `cartclinic.*`
  - `libpyretro.cartclinic.cart_api`
  - `libpyretro.cartclinic.comms.*`
  - `libpyretro.cartclinic.protocol.*`

The DMG could not be mounted in this sandbox, but `hdiutil convert` produced a raw image and the PyInstaller archive was carved from the HFS partition.

## Cart Clinic Serial Setup

MRUpdater creates the Cart Clinic session with:

- port: `chromatic.mcu_port`
- baud: `115200`
- serial timeout: `0.001`
- transport kind: `Serial`

The public MCU README also documents the Chromatic composite USB serial interface and the default ESP32 baud rate as `115200`.

## Basic Wire Protocol

Cart Clinic commands are raw little-endian binary frames over the serial port. There is no CRC in this protocol layer.

Known command ids:

| ID | Name |
| --- | --- |
| `0x01` | `Loopback` |
| `0x02` | `ReadCartByte` |
| `0x03` | `WriteCartByte` |
| `0x04` | `WriteCartFlashByte` |
| `0x05` | `DetectCart` |
| `0x06` | `SetFrameBufferPixel` |
| `0x10` | `SetPSRAMAddress` |
| `0x11` | `WritePSRAMData` |
| `0x12` | `ReadPSRAMData` |
| `0x13` | `StartAudioPlayback` |
| `0x14` | `StopAudioPlayback` |

Replies are routed by the first byte, which is the command id. Most replies have a 3-byte payload, so the full reply length is 4 bytes.

### ReadCartByte

Request:

```text
struct.pack("<BHB", 0x02, addr, 0)
```

Reply:

```text
struct.unpack("<BHB", reply) -> (0x02, addr, data)
```

For bank 0 fixed ROM header reads, this should be enough:

- read `0x0100..0x014F`
- no MBC writes required
- no SRAM enable required

### DetectCart

Request:

```text
struct.pack("<BBBB", 0x05, 0, 0, 0)
```

Reply:

```text
struct.unpack("<BBBB", reply) -> (0x05, status, 0, 0)
```

Status bits:

- bit 0: inserted
- bit 1: removed

### Loopback

Request and reply are identical:

```text
struct.pack("<BBBB", 0x01, b0, b1, b2)
```

## ModRetro Cartridge-Specific Behavior

MRUpdater's higher-level Cart Clinic flow checks for ModRetro flash/FRAM cart behavior and uses write commands for bank switching, flash erase/write, save backup, and save restore.

For traditional Game Boy / Game Boy Color ROM header reads, the first experiment should avoid that path and use only `ReadCartByte`.

## First Experiment

Run:

```bash
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --dump-header /tmp/gb_header.bin
```

Expected successful output:

- loopback succeeds
- detect cart reports `inserted=True`
- title and header fields decode
- Game Boy header checksum reports `ok`

If the script times out, the Chromatic is probably not in Cart Clinic FPGA mode yet. In that case, start MRUpdater's Cart Clinic setup first, or reverse the Cart Clinic firmware loading path next.

## Observed Test Result

With Chromatic visible on macOS as:

- USB product: `Chromatic - Player 01`
- USB vendor: `ModRetro`
- serial port: `/dev/cu.usbmodem0123456783`

Running the first probe after opening MRUpdater's Cart Clinic tab and then quitting MRUpdater produced:

```text
Timeout: Timed out waiting for reply 0x01; tail_hex= tail_ascii=''
```

That means the host opened the visible Chromatic serial port, wrote the `Loopback` frame, and received zero bytes. Current interpretation: the port is likely correct, but the device was not answering the raw Cart Clinic command protocol after MRUpdater closed.

Next diagnostics:

```bash
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodem0123456783 --timeout 5 --probe loopback
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodem0123456783 --timeout 5 --probe detect --skip-loopback
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodem0123456783 --timeout 5 --skip-loopback --skip-detect
```

If all three time out with empty tails, reverse MRUpdater's Cart Clinic setup/firmware-loading path before further read experiments.

## Cart Clinic Mode Setup

MRUpdater does not just open the MCU serial port. Before creating the Cart Clinic serial session, it loads a Cart Clinic FPGA image into Chromatic SRAM:

1. Download Cart Clinic firmware from the ModRetro update bucket.
2. Unzip the package.
3. Run `openFPGALoader --cable gwu2x --write-sram --skip-reset <cart_clinic_*.fs>`.
4. Sleep for 5 seconds.
5. Open the MCU serial port at 115200 baud and create the Cart Clinic session.

Observed local firmware cache:

```text
/var/folders/8w/xtm3b_893493gs6qbc8pn3nm0000gn/T/firmware/chromatic/cartclinic/v1.1.zip
```

That zip contains:

```text
cart_clinic_250412.fs
```

MRUpdater's bundled `openFPGALoader` is at:

```text
/Volumes/MRUpdater/MRUpdater.app/Contents/Frameworks/lib/openFPGALoader/openFPGALoader
```

The host-side setup helper is:

```bash
python3 tools/cartclinic_enter_mode.py
```

After this SRAM load succeeds, rerun the read-only header probe.

Observed failed setup attempt:

```text
openFPGALoader --cable gwu2x --write-sram --skip-reset cart_clinic_250412.fs
empty
write to ram
No USB devices found
JTAG init failed with: No cable found
```

Immediately after this, neither `/dev/cu.usbmodem*` nor the USB `GWU2X`/`Chromatic - Player 01` devices were visible in macOS. Replug or power-cycle the Chromatic before retrying `cartclinic_enter_mode.py`.

Observed successful setup/read attempt after reconnecting correctly:

```text
openFPGALoader --cable gwu2x --write-sram --skip-reset cart_clinic_250412.fs
Load SRAM: 100.00%
Cart Clinic SRAM load complete.
```

Then:

```text
Opening /dev/cu.usbmodem0123456783 at 115200 baud
Loopback: ok
DetectCart: inserted=True removed=False
Header:
  title: 'TETRIS DX'
  cgb_flag: 0x80
  cart_type: 0x03
  rom_size: 0x04
  ram_size: 0x02
  header_checksum: 0x30 (ok)
```

This confirms the safe read-only path works once Cart Clinic FPGA SRAM mode is loaded.
