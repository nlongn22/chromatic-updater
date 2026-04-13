#!/usr/bin/env python3
"""List or extract a PyInstaller CArchive appended to an executable."""

from __future__ import annotations

import argparse
import os
import struct
import zlib
from dataclasses import dataclass


MAGIC = b"MEI\014\013\012\013\016"
COOKIE_FORMAT = "!8sIIII64s"
COOKIE_LEN = struct.calcsize(COOKIE_FORMAT)
TOC_FIXED_FORMAT = "!IIIIBc"
TOC_FIXED_LEN = struct.calcsize(TOC_FIXED_FORMAT)


@dataclass
class Entry:
    name: str
    offset: int
    length: int
    uncompressed_length: int
    compressed: bool
    typecode: str


@dataclass
class Archive:
    start: int
    package_length: int
    toc_offset: int
    toc_length: int
    python_version: int
    python_lib: str
    entries: list[Entry]


def find_cookie(data: bytes) -> tuple[int, tuple[bytes, int, int, int, int, bytes]]:
    cookie_pos = data.rfind(MAGIC)
    if cookie_pos < 0:
        raise ValueError("PyInstaller cookie magic not found")
    if cookie_pos + COOKIE_LEN > len(data):
        raise ValueError("Truncated PyInstaller cookie")
    return cookie_pos, struct.unpack(COOKIE_FORMAT, data[cookie_pos : cookie_pos + COOKIE_LEN])


def parse_archive(data: bytes) -> Archive:
    cookie_pos, (_, package_length, toc_offset, toc_length, python_version, python_lib_raw) = find_cookie(data)
    start = cookie_pos + COOKIE_LEN - package_length
    if start < 0:
        raise ValueError("Invalid package length in cookie")

    toc_start = start + toc_offset
    toc_end = toc_start + toc_length
    toc = data[toc_start:toc_end]
    if len(toc) != toc_length:
        raise ValueError("Truncated PyInstaller table of contents")

    entries: list[Entry] = []
    pos = 0
    while pos < len(toc):
        fixed = toc[pos : pos + TOC_FIXED_LEN]
        if len(fixed) != TOC_FIXED_LEN:
            raise ValueError("Truncated PyInstaller TOC entry")

        entry_length, offset, length, uncompressed_length, compressed, typecode = struct.unpack(TOC_FIXED_FORMAT, fixed)
        name_start = pos + TOC_FIXED_LEN
        name_end = pos + entry_length
        raw_name = toc[name_start:name_end].split(b"\0", 1)[0]
        name = raw_name.decode("utf-8", errors="replace")
        entries.append(
            Entry(
                name=name,
                offset=start + offset,
                length=length,
                uncompressed_length=uncompressed_length,
                compressed=bool(compressed),
                typecode=typecode.decode("ascii", errors="replace"),
            )
        )
        pos += entry_length

    python_lib = python_lib_raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")
    return Archive(start, package_length, toc_offset, toc_length, python_version, python_lib, entries)


def safe_output_path(output_dir: str, name: str) -> str:
    normalized = os.path.normpath(name).lstrip(os.sep)
    path = os.path.abspath(os.path.join(output_dir, normalized))
    root = os.path.abspath(output_dir)
    if path != root and not path.startswith(root + os.sep):
        raise ValueError(f"Unsafe archive path: {name!r}")
    return path


def extract_entry(data: bytes, entry: Entry) -> bytes:
    payload = data[entry.offset : entry.offset + entry.length]
    if len(payload) != entry.length:
        raise ValueError(f"Truncated payload for {entry.name}")
    if not entry.compressed:
        return payload
    return zlib.decompress(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--extract-to", help="Extract matching entries into this directory")
    parser.add_argument("--match", action="append", default=[], help="Substring to include; repeatable")
    args = parser.parse_args()

    with open(args.archive, "rb") as f:
        data = f.read()

    archive = parse_archive(data)
    print(
        f"package_start={archive.start} package_length={archive.package_length} "
        f"python={archive.python_version} python_lib={archive.python_lib!r} entries={len(archive.entries)}"
    )

    matches = [
        entry
        for entry in archive.entries
        if not args.match or any(needle in entry.name for needle in args.match)
    ]

    if args.extract_to:
        os.makedirs(args.extract_to, exist_ok=True)

    for entry in matches:
        print(
            f"{entry.typecode} {'z' if entry.compressed else '-'} "
            f"{entry.length:8d} {entry.uncompressed_length:8d} {entry.name}"
        )
        if args.extract_to:
            output_path = safe_output_path(args.extract_to, entry.name)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(extract_entry(data, entry))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
