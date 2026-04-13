# chromatic-updater

Reverse-engineering notes and small host-side tools for ModRetro Chromatic MRUpdater / Cart Clinic behavior.

This starts with a deliberately narrow, read-only probe for traditional Game Boy / Game Boy Color cartridges:

```bash
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --dump-header /tmp/gb_header.bin
```

The probe only sends Cart Clinic `Loopback`, `DetectCart`, and `ReadCartByte` commands. It does not write cartridge bus registers, SRAM, or flash.

For staged diagnostics:

```bash
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --timeout 5 --probe loopback
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --timeout 5 --probe detect --skip-loopback
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --timeout 5 --skip-loopback --skip-detect --dump-header /tmp/gb_header.bin
```

Keep each command on one shell line, or use a trailing `\` for line continuation.

If the read commands time out with empty replies, load the Cart Clinic FPGA SRAM image first:

```bash
python3 tools/cartclinic_enter_mode.py
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --timeout 5 --dump-header /tmp/gb_header.bin
```

`cartclinic_enter_mode.py` mirrors MRUpdater's setup step and writes only FPGA SRAM with `openFPGALoader --write-sram --skip-reset`. It does not write cartridge data, FPGA flash, or MCU flash.

See `docs/cart_clinic_reverse_engineering.md` for the extracted protocol notes.
