#!/usr/bin/env python3
"""Check whether the local machine is ready to run the Cart Clinic tools."""

from __future__ import annotations

import argparse
import glob
import os
import subprocess

from cartclinic_enter_mode import DEFAULT_CABLE, find_cartclinic_zip, find_openfpgaloader
from cartclinic_read_header import find_default_port


def exists_label(path: str | None) -> str:
    return path if path else "not found"


def usb_summary() -> tuple[bool, bool]:
    try:
        result = subprocess.run(
            ["ioreg", "-p", "IOUSB", "-l", "-w", "0"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False, False

    output = result.stdout
    return "Chromatic - Player" in output, "GWU2X" in output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    openfpgaloader = find_openfpgaloader()
    firmware_zip = find_cartclinic_zip()
    serial_port = find_default_port()
    modem_ports = sorted(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/tty.usbmodem*"))
    has_chromatic_usb, has_gwu2x_usb = usb_summary()

    print("Cart Clinic Doctor")
    print(f"  openFPGALoader: {exists_label(openfpgaloader)}")
    print(f"  Cart Clinic firmware zip: {exists_label(firmware_zip)}")
    print(f"  default serial port: {exists_label(serial_port)}")
    print(f"  usbmodem ports: {', '.join(modem_ports) if modem_ports else 'not found'}")
    print(f"  USB Chromatic endpoint: {'found' if has_chromatic_usb else 'not found'}")
    print(f"  USB GWU2X endpoint: {'found' if has_gwu2x_usb else 'not found'}")
    print(f"  openFPGALoader cable name: {DEFAULT_CABLE}")

    ok = bool(openfpgaloader and firmware_zip and serial_port and has_chromatic_usb and has_gwu2x_usb)
    if ok:
        print("\nReady. Next:")
        print("  python3 tools/cartclinic_enter_mode.py")
        print(f"  python3 tools/cartclinic_backup_save.py --port {serial_port}")
        print("  python3 tools/cartclinic_exit_mode.py")
        return 0

    print("\nNot ready yet.")
    if not openfpgaloader:
        print("- Install MRUpdater to /Applications or mount MRUpdater.dmg.")
    if not firmware_zip:
        print("- Open MRUpdater's Cart Clinic tab once so it downloads/caches Cart Clinic firmware.")
    if not serial_port or not has_chromatic_usb or not has_gwu2x_usb:
        print("- Connect the Chromatic over USB and confirm both Chromatic and GWU2X endpoints appear.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
