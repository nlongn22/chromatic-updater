#!/usr/bin/env python3
"""
Load MRUpdater's Cart Clinic FPGA image into Chromatic SRAM.

This mirrors the MRUpdater setup step before it opens the Cart Clinic serial
session:

  openFPGALoader --cable gwu2x --write-sram --skip-reset cart_clinic_*.fs

It writes FPGA SRAM only. It does not write FPGA flash, MCU flash, cartridge
ROM/SRAM, or save data. The loaded mode is temporary and is reset by power
cycling or resetting the FPGA.
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


DEFAULT_CABLE = "gwu2x"
DEFAULT_WAIT_S = 5.0


def first_existing(paths: list[str]) -> str | None:
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def find_openfpgaloader() -> str | None:
    return first_existing(
        [
            "/Volumes/MRUpdater/MRUpdater.app/Contents/Frameworks/lib/openFPGALoader/openFPGALoader",
            "/Applications/MRUpdater.app/Contents/Frameworks/lib/openFPGALoader/openFPGALoader",
        ]
    )


def find_cartclinic_zip() -> str | None:
    temp_roots = [tempfile.gettempdir()]
    if os.environ.get("TMPDIR"):
        temp_roots.append(os.environ["TMPDIR"])

    candidates: list[str] = []
    for temp_root in dict.fromkeys(temp_roots):
        candidates.extend(glob.glob(os.path.join(temp_root, "firmware/chromatic/cartclinic/*.zip")))

    if not candidates:
        candidates = glob.glob(
            "/var/folders/*/*/T/firmware/chromatic/cartclinic/*.zip",
            recursive=False,
        )
    if not candidates:
        candidates = glob.glob("/tmp/firmware/chromatic/cartclinic/*.zip")
    return sorted(candidates)[-1] if candidates else None


def extract_fs_from_zip(zip_path: str, output_dir: str) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        fs_names = [name for name in zf.namelist() if name.lower().endswith(".fs")]
        if len(fs_names) != 1:
            raise ValueError(f"Expected exactly one .fs file in {zip_path}, found {fs_names}")
        name = fs_names[0]
        output_path = os.path.abspath(os.path.join(output_dir, os.path.basename(name)))
        with zf.open(name) as src, open(output_path, "wb") as dst:
            dst.write(src.read())
        return output_path


def resolve_firmware(args: argparse.Namespace, temp_dir: str) -> str:
    if args.firmware:
        return args.firmware

    zip_path = args.firmware_zip or find_cartclinic_zip()
    if not zip_path:
        raise FileNotFoundError(
            "No Cart Clinic firmware zip found. Pass --firmware /path/cart_clinic_*.fs "
            "or --firmware-zip /path/v1.1.zip."
        )

    print(f"Using Cart Clinic firmware zip: {zip_path}")
    return extract_fs_from_zip(zip_path, temp_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openfpgaloader", help="Path to MRUpdater's openFPGALoader binary")
    parser.add_argument("--firmware", help="Path to extracted Cart Clinic .fs file")
    parser.add_argument("--firmware-zip", help="Path to Cart Clinic firmware zip, e.g. v1.1.zip")
    parser.add_argument("--cable", default=DEFAULT_CABLE)
    parser.add_argument("--wait", type=float, default=DEFAULT_WAIT_S, help="Seconds to wait after SRAM load")
    args = parser.parse_args()

    openfpgaloader = args.openfpgaloader or find_openfpgaloader()
    if not openfpgaloader:
        print("Could not find openFPGALoader. Pass --openfpgaloader /path/to/openFPGALoader", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as temp_dir:
        firmware = resolve_firmware(args, temp_dir)
        if not os.path.exists(firmware):
            print(f"Firmware file does not exist: {firmware}", file=sys.stderr)
            return 2

        cmd = [openfpgaloader, "--cable", args.cable, "--write-sram", "--skip-reset", firmware]
        print("Running:", " ".join(str(Path(part)) if "/" in part else part for part in cmd))
        result = subprocess.run(cmd, text=True)
        if result.returncode != 0:
            print(f"openFPGALoader failed with exit code {result.returncode}", file=sys.stderr)
            return result.returncode

        print(f"Waiting {args.wait:g}s for Cart Clinic mode...")
        time.sleep(args.wait)

    print("Cart Clinic SRAM load complete. Run cartclinic_read_header.py next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
