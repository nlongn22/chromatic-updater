# chromatic-updater

Reverse-engineering notes and small host-side tools for ModRetro Chromatic MRUpdater / Cart Clinic behavior.

This starts with a deliberately narrow, read-only probe for traditional Game Boy / Game Boy Color cartridges:

```bash
python3 tools/cartclinic_read_header.py --port /dev/cu.usbmodemXXXX --dump-header /tmp/gb_header.bin
```

The probe only sends Cart Clinic `Loopback`, `DetectCart`, and `ReadCartByte` commands. It does not write cartridge bus registers, SRAM, or flash.

See `docs/cart_clinic_reverse_engineering.md` for the extracted protocol notes.
