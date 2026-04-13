#!/usr/bin/env python3
"""
Back up external save RAM from a traditional Game Boy / Game Boy Color cart.

The Chromatic must already be running Cart Clinic FPGA SRAM mode. Run
cartclinic_enter_mode.py first if needed.

This reads battery-backed cartridge RAM. It sends MBC control-register writes
to enable RAM and select RAM banks, but it does not write save RAM contents,
erase flash, restore saves, or modify cartridge ROM.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass

from cartclinic_read_header import (
    SerialPort,
    checksum_ok,
    detect_cart,
    find_default_port,
    loopback,
    parse_header,
    read_cart_byte,
    read_header,
    write_cart_byte,
)


RAM_START = 0xA000
RAM_BANK_SIZE = 0x2000
MBC2_SAVE_SIZE = 512


@dataclass(frozen=True)
class SaveLayout:
    mbc: str
    size: int
    bank_size: int
    banks: int


MBC1_TYPES = {0x01, 0x02, 0x03}
MBC2_TYPES = {0x05, 0x06}
MBC3_TYPES = {0x0F, 0x10, 0x11, 0x12, 0x13}
MBC5_TYPES = {0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E}

RAM_SIZE_BYTES = {
    0x00: 0,
    0x01: 2 * 1024,
    0x02: 8 * 1024,
    0x03: 32 * 1024,
    0x04: 128 * 1024,
    0x05: 64 * 1024,
}


def cart_mbc(cart_type: int) -> str:
    if cart_type in MBC1_TYPES:
        return "MBC1"
    if cart_type in MBC2_TYPES:
        return "MBC2"
    if cart_type in MBC3_TYPES:
        return "MBC3"
    if cart_type in MBC5_TYPES:
        return "MBC5"
    if cart_type == 0x00:
        return "ROM"
    return "unsupported"


def save_layout(cart_type: int, ram_size_code: int, force_size: int | None) -> SaveLayout:
    mbc = cart_mbc(cart_type)
    if mbc == "unsupported":
        raise ValueError(f"Unsupported cartridge type for save backup: 0x{cart_type:02X}")

    if mbc == "MBC2":
        size = force_size or MBC2_SAVE_SIZE
        return SaveLayout(mbc=mbc, size=size, bank_size=size, banks=1)

    size = force_size if force_size is not None else RAM_SIZE_BYTES.get(ram_size_code)
    if size is None:
        raise ValueError(f"Unknown RAM size code: 0x{ram_size_code:02X}")
    if size <= 0:
        raise ValueError("Cartridge header reports no external RAM")

    if size <= RAM_BANK_SIZE:
        return SaveLayout(mbc=mbc, size=size, bank_size=size, banks=1)
    if size % RAM_BANK_SIZE != 0:
        raise ValueError(f"Unsupported non-8KB-banked RAM size: {size}")

    banks = size // RAM_BANK_SIZE
    if mbc == "MBC1" and banks > 4:
        raise ValueError(f"MBC1 supports at most 4 RAM banks, header requested {banks}")
    if mbc == "MBC3" and banks > 4:
        raise ValueError(f"MBC3 supports at most 4 RAM banks, header requested {banks}")
    if mbc == "MBC5" and banks > 16:
        raise ValueError(f"MBC5 supports at most 16 RAM banks, header requested {banks}")

    return SaveLayout(mbc=mbc, size=size, bank_size=RAM_BANK_SIZE, banks=banks)


def default_output_path(title: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", title.strip()).strip("_").lower()
    if not clean:
        clean = "gb_cart"
    return os.path.expanduser(f"~/Downloads/{clean}.sav")


def enable_ram(port: SerialPort, mbc: str) -> None:
    if mbc == "ROM":
        return
    write_cart_byte(port, 0x0000, 0x0A)


def disable_ram(port: SerialPort, mbc: str) -> None:
    if mbc == "ROM":
        return
    write_cart_byte(port, 0x0000, 0x00)


def select_ram_bank(port: SerialPort, layout: SaveLayout, bank: int) -> None:
    if layout.banks == 1:
        return
    if layout.mbc == "MBC1":
        write_cart_byte(port, 0x6000, 0x01)
    write_cart_byte(port, 0x4000, bank)


def read_save_ram(port: SerialPort, layout: SaveLayout) -> bytes:
    data = bytearray()
    enable_ram(port, layout.mbc)
    try:
        for bank in range(layout.banks):
            select_ram_bank(port, layout, bank)
            print(f"Reading save bank {bank + 1}/{layout.banks} ({layout.bank_size} bytes)")
            for offset in range(layout.bank_size):
                value = read_cart_byte(port, RAM_START + offset)
                if layout.mbc == "MBC2":
                    value &= 0x0F
                data.append(value)
    finally:
        try:
            disable_ram(port, layout.mbc)
        except Exception as exc:
            print(f"Warning: failed to disable cartridge RAM: {exc}", file=sys.stderr)

    return bytes(data[: layout.size])


def parse_force_size(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    multiplier = 1
    if normalized.endswith("k"):
        multiplier = 1024
        normalized = normalized[:-1]
    return int(normalized, 0) * multiplier


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial port, e.g. /dev/cu.usbmodemXXXX")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output", help="Path to write the .sav backup; defaults to ~/Downloads/<title>.sav")
    parser.add_argument("--force-size", help="Override save size, e.g. 8K, 32K, 65536")
    parser.add_argument("--skip-loopback", action="store_true")
    parser.add_argument("--skip-detect", action="store_true")
    args = parser.parse_args()

    port_path = args.port or find_default_port()
    if not port_path:
        print("No likely Chromatic serial port found. Pass --port /dev/...", file=sys.stderr)
        return 2

    print(f"Opening {port_path} at {args.baud} baud")
    try:
        with SerialPort(port_path, args.baud, args.timeout) as port:
            if not args.skip_loopback:
                print(f"Loopback: {'ok' if loopback(port) else 'failed'}")
            if not args.skip_detect:
                inserted, removed = detect_cart(port)
                print(f"DetectCart: inserted={inserted} removed={removed}")
                if not inserted:
                    print("No cartridge detected", file=sys.stderr)
                    return 1

            header = read_header(port)
            if not checksum_ok(header):
                print("Header checksum is bad; refusing to infer save layout", file=sys.stderr)
                return 1

            info = parse_header(header)
            layout = save_layout(info.cart_type, info.ram_size, parse_force_size(args.force_size))
            output_path = args.output or default_output_path(info.title)

            print("Cartridge:")
            print(f"  title: {info.title!r}")
            print(f"  cart_type: 0x{info.cart_type:02X} ({layout.mbc})")
            print(f"  ram_size: 0x{info.ram_size:02X}")
            print(f"  backup_size: {layout.size} bytes")

            save_data = read_save_ram(port, layout)
    except TimeoutError as exc:
        print(f"Timeout: {exc}", file=sys.stderr)
        print("Load Cart Clinic mode with cartclinic_enter_mode.py and retry.", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Unsupported save backup: {exc}", file=sys.stderr)
        return 2

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(save_data)

    print(f"Wrote save backup: {output_path} ({len(save_data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
