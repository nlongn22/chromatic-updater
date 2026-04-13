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
