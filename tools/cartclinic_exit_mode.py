#!/usr/bin/env python3
"""
Reset the Chromatic FPGA to leave temporary Cart Clinic SRAM mode.

This wraps MRUpdater's bundled openFPGALoader:

  openFPGALoader --cable gwu2x --reset

It does not write cartridge data, FPGA flash, or MCU flash.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from cartclinic_enter_mode import DEFAULT_CABLE, find_openfpgaloader


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openfpgaloader", help="Path to MRUpdater's openFPGALoader binary")
    parser.add_argument("--cable", default=DEFAULT_CABLE)
    args = parser.parse_args()

    openfpgaloader = args.openfpgaloader or find_openfpgaloader()
    if not openfpgaloader:
        print("Could not find openFPGALoader. Pass --openfpgaloader /path/to/openFPGALoader", file=sys.stderr)
        return 2

    cmd = [openfpgaloader, "--cable", args.cable, "--reset"]
    print("Running:", " ".join(str(Path(part)) if "/" in part else part for part in cmd))
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        print(f"openFPGALoader reset failed with exit code {result.returncode}", file=sys.stderr)
        return result.returncode

    print("Chromatic FPGA reset complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
