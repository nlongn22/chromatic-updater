# chromatic-updater

Reverse-engineering notes and small host-side tools for ModRetro Chromatic MRUpdater / Cart Clinic behavior.

This starts with a deliberately narrow, read-only probe for traditional Game Boy / Game Boy Color cartridges:

```bash
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --dump-header ~/Downloads/gb_header.bin
```

The probe only sends Cart Clinic `Loopback`, `DetectCart`, and `ReadCartByte` commands. It does not write cartridge bus registers, SRAM, or flash.

For staged diagnostics:

```bash
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --timeout 5 --probe loopback
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --timeout 5 --probe detect --skip-loopback
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --timeout 5 --skip-loopback --skip-detect --dump-header ~/Downloads/gb_header.bin
```

Keep each command on one shell line, or use a trailing `\` for line continuation.

If the read commands time out with empty replies, load the Cart Clinic FPGA SRAM image first:

```bash
python3 tools/cartclinic_enter_mode.py
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --timeout 5 --dump-header ~/Downloads/gb_header.bin
```

`cartclinic_enter_mode.py` mirrors MRUpdater's setup step and writes only FPGA SRAM with `openFPGALoader --write-sram --skip-reset`. It does not write cartridge data, FPGA flash, or MCU flash.

To back up traditional GB/GBC battery-backed save RAM after Cart Clinic mode is loaded:

```bash
python3 tools/cartclinic_backup_save.py --port /dev/cu.usbmodemXXXX
```

The save backup tool defaults to `~/Downloads/<title>.sav` and supports common MBC1, MBC2, MBC3, and MBC5 cartridges. It sends MBC register writes to enable and bank external RAM, but does not write save RAM contents, erase flash, restore saves, or modify cartridge ROM.

To leave temporary Cart Clinic FPGA SRAM mode:

```bash
python3 tools/cartclinic_exit_mode.py
```

See `docs/setup.md` for setup/run instructions and `docs/cart_clinic_reverse_engineering.md` for the extracted protocol notes.
