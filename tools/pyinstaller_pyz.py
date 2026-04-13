#!/usr/bin/env python3
"""List or extract modules from a PyInstaller PYZ archive."""

from __future__ import annotations

import argparse
import importlib.util
import marshal
import os
import struct
import zlib
from dataclasses import dataclass


MAGIC = b"PYZ\0"


@dataclass
class Entry:
    name: str
    typecode: int
    offset: int
    length: int


def load_pyz(path: str) -> tuple[bytes, list[Entry], bytes]:
    with open(path, "rb") as f:
        data = f.read()

    if data[:4] != MAGIC:
        raise ValueError("PYZ magic not found")

    pyc_magic = data[4:8]
    toc_offset = struct.unpack("!I", data[8:12])[0]
    toc = marshal.loads(data[toc_offset:])

    entries: list[Entry] = []
    items = toc.items() if isinstance(toc, dict) else toc
    for item in items:
        if isinstance(toc, dict):
            name, value = item
        else:
            name, value = item[0], item[1]
        typecode, offset, length = value
        entries.append(Entry(str(name), int(typecode), int(offset), int(length)))

    return data, sorted(entries, key=lambda entry: entry.name), pyc_magic


def safe_module_path(output_dir: str, module_name: str) -> str:
    rel = module_name.replace(".", os.sep) + ".pyc"
    path = os.path.abspath(os.path.join(output_dir, rel))
    root = os.path.abspath(output_dir)
    if not path.startswith(root + os.sep):
        raise ValueError(f"Unsafe module path: {module_name!r}")
    return path


def pyc_header(pyc_magic: bytes) -> bytes:
    magic = pyc_magic if pyc_magic != b"\0\0\0\0" else importlib.util.MAGIC_NUMBER
    return magic + b"\0" * 12


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pyz")
    parser.add_argument("--extract-to", help="Extract matching modules as .pyc files into this directory")
    parser.add_argument("--match", action="append", default=[], help="Substring to include; repeatable")
    args = parser.parse_args()

    data, entries, pyc_magic = load_pyz(args.pyz)
    print(f"pyc_magic={pyc_magic.hex()} entries={len(entries)}")

    matches = [
        entry
        for entry in entries
        if not args.match or any(needle in entry.name for needle in args.match)
    ]

    if args.extract_to:
        os.makedirs(args.extract_to, exist_ok=True)

    for entry in matches:
        print(f"{entry.typecode:2d} {entry.offset:8d} {entry.length:8d} {entry.name}")
        if args.extract_to:
            if entry.length == 0:
                continue
            payload = data[entry.offset : entry.offset + entry.length]
            code_data = zlib.decompress(payload)
            output_path = safe_module_path(args.extract_to, entry.name)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(pyc_header(pyc_magic))
                f.write(code_data)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
