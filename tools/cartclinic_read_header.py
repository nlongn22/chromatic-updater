#!/usr/bin/env python3
"""
Read the fixed Game Boy cartridge header through ModRetro's Cart Clinic protocol.

This intentionally sends only read-only Cart Clinic commands:
  - 0x01 Loopback
  - 0x05 DetectCart
  - 0x02 ReadCartByte

It does not switch MBC banks, enable RAM, write SRAM, erase flash, or write flash.
The Chromatic must already be running the Cart Clinic FPGA/firmware path used by
MRUpdater.
"""

from __future__ import annotations

import argparse
import glob
import os
import select
import struct
import sys
import termios
import time
import tty
from dataclasses import dataclass


CMD_LOOPBACK = 0x01
CMD_READ_CART_BYTE = 0x02
CMD_DETECT_CART = 0x05

REPLY_LEN = {
    CMD_LOOPBACK: 4,
    CMD_READ_CART_BYTE: 4,
    CMD_DETECT_CART: 4,
}

GB_HEADER_START = 0x0100
GB_HEADER_END_EXCLUSIVE = 0x0150


@dataclass
class HeaderInfo:
    title: str
    cgb_flag: int
    cart_type: int
    rom_size: int
    ram_size: int
    header_checksum: int


class SerialPort:
    def __init__(self, path: str, baudrate: int, timeout_s: float) -> None:
        self.path = path
        self.timeout_s = timeout_s
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self._old_attrs = termios.tcgetattr(self.fd)
        self._configure(baudrate)

    def _configure(self, baudrate: int) -> None:
        baud_const = getattr(termios, f"B{baudrate}", None)
        if baud_const is None:
            raise ValueError(f"Unsupported baud rate for termios: {baudrate}")

        tty.setraw(self.fd)
        attrs = termios.tcgetattr(self.fd)

        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0
        attrs[4] = baud_const
        attrs[5] = baud_const
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0

        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def write(self, data: bytes) -> None:
        while data:
            _, writable, _ = select.select([], [self.fd], [], self.timeout_s)
            if not writable:
                raise TimeoutError("Timed out waiting for serial port to become writable")
            written = os.write(self.fd, data)
            data = data[written:]

    def read_response(self, expected_id: int, length: int) -> bytes:
        deadline = time.monotonic() + self.timeout_s
        buf = bytearray()

        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select([self.fd], [], [], min(0.02, remaining))
            if readable:
                try:
                    buf.extend(os.read(self.fd, 4096))
                except BlockingIOError:
                    pass

            while True:
                idx = buf.find(bytes([expected_id]))
                if idx < 0:
                    if len(buf) > 256:
                        del buf[:-32]
                    break
                if idx:
                    del buf[:idx]
                if len(buf) >= length:
                    return bytes(buf[:length])
                break

        ascii_tail = bytes(buf[-96:]).decode("ascii", errors="replace")
        raise TimeoutError(
            f"Timed out waiting for reply 0x{expected_id:02X}; "
            f"tail_hex={bytes(buf[-96:]).hex()} tail_ascii={ascii_tail!r}"
        )

    def transact(self, expected_id: int, payload: bytes) -> bytes:
        self.write(payload)
        return self.read_response(expected_id, REPLY_LEN[expected_id])

    def close(self) -> None:
        try:
            termios.tcsetattr(self.fd, termios.TCSANOW, self._old_attrs)
        finally:
            os.close(self.fd)

    def __enter__(self) -> "SerialPort":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def find_default_port() -> str | None:
    patterns = [
        "/dev/cu.usbmodem*",
        "/dev/tty.usbmodem*",
        "/dev/ttyACM*",
        "/dev/cu.usbserial*",
        "/dev/ttyUSB*",
    ]
    ports: list[str] = []
    for pattern in patterns:
        ports.extend(sorted(glob.glob(pattern)))

    ignored_suffixes = ("Bluetooth-Incoming-Port", "wlan-debug")
    ports = [p for p in ports if not p.endswith(ignored_suffixes)]
    return ports[0] if ports else None


def loopback(port: SerialPort) -> bool:
    request = struct.pack("<BBBB", CMD_LOOPBACK, 0xA5, 0x5A, 0x3C)
    return port.transact(CMD_LOOPBACK, request) == request


def detect_cart(port: SerialPort) -> tuple[bool, bool]:
    request = struct.pack("<BBBB", CMD_DETECT_CART, 0, 0, 0)
    reply = port.transact(CMD_DETECT_CART, request)
    cmd, status, _, _ = struct.unpack("<BBBB", reply)
    if cmd != CMD_DETECT_CART:
        raise RuntimeError(f"Unexpected DetectCart reply id: 0x{cmd:02X}")
    return bool(status & 0x01), bool(status & 0x02)


def read_cart_byte(port: SerialPort, addr: int) -> int:
    request = struct.pack("<BHB", CMD_READ_CART_BYTE, addr & 0xFFFF, 0)
    reply = port.transact(CMD_READ_CART_BYTE, request)
    cmd, reply_addr, data = struct.unpack("<BHB", reply)
    if cmd != CMD_READ_CART_BYTE:
        raise RuntimeError(f"Unexpected ReadCartByte reply id: 0x{cmd:02X}")
    if reply_addr != addr:
        raise RuntimeError(f"ReadCartByte address mismatch: got 0x{reply_addr:04X}, wanted 0x{addr:04X}")
    return data


def read_header(port: SerialPort) -> bytes:
    return bytes(read_cart_byte(port, addr) for addr in range(GB_HEADER_START, GB_HEADER_END_EXCLUSIVE))


def parse_header(header: bytes) -> HeaderInfo:
    if len(header) != GB_HEADER_END_EXCLUSIVE - GB_HEADER_START:
        raise ValueError(f"Expected 0x50 header bytes, got {len(header)}")

    title_raw = header[0x0134 - GB_HEADER_START : 0x0144 - GB_HEADER_START]
    title = title_raw.split(b"\0", 1)[0].decode("ascii", errors="replace").strip()
    return HeaderInfo(
        title=title,
        cgb_flag=header[0x0143 - GB_HEADER_START],
        cart_type=header[0x0147 - GB_HEADER_START],
        rom_size=header[0x0148 - GB_HEADER_START],
        ram_size=header[0x0149 - GB_HEADER_START],
        header_checksum=header[0x014D - GB_HEADER_START],
    )


def checksum_ok(header: bytes) -> bool:
    x = 0
    for b in header[0x0134 - GB_HEADER_START : 0x014D - GB_HEADER_START]:
        x = (x - b - 1) & 0xFF
    return x == header[0x014D - GB_HEADER_START]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial port, e.g. /dev/cu.usbmodemXXXX")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--dump-header", help="Optional path to write the raw 0x0100-0x014F header bytes")
    args = parser.parse_args()

    port_path = args.port or find_default_port()
    if not port_path:
        print("No likely Chromatic serial port found. Pass --port /dev/...", file=sys.stderr)
        return 2

    print(f"Opening {port_path} at {args.baud} baud")
    with SerialPort(port_path, args.baud, args.timeout) as port:
        print(f"Loopback: {'ok' if loopback(port) else 'failed'}")
        inserted, removed = detect_cart(port)
        print(f"DetectCart: inserted={inserted} removed={removed}")

        header = read_header(port)
        info = parse_header(header)

    if args.dump_header:
        with open(args.dump_header, "wb") as f:
            f.write(header)

    print("Header:")
    print(f"  title: {info.title!r}")
    print(f"  cgb_flag: 0x{info.cgb_flag:02X}")
    print(f"  cart_type: 0x{info.cart_type:02X}")
    print(f"  rom_size: 0x{info.rom_size:02X}")
    print(f"  ram_size: 0x{info.ram_size:02X}")
    print(f"  header_checksum: 0x{info.header_checksum:02X} ({'ok' if checksum_ok(header) else 'bad'})")
    print(f"  raw: {header.hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
