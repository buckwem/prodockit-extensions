# Copyright (c) 2026 Mark Buckwell and contributors
# SPDX-License-Identifier: MIT

"""Validate and identify one candidate wheel for the protected release gate."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import stat
import sys
import zipfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from packaging.utils import InvalidWheelFilename, canonicalize_name, parse_wheel_filename
from packaging.version import Version

MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_WHEEL_BYTES = 512 * 1024 * 1024
CANONICAL_FORMAT = "prodockit-wheel-content-v1"


class WheelIdentityError(RuntimeError):
    """A wheel is malformed, ambiguous or unsafe to authorise for release."""


@dataclass(frozen=True)
class WheelIdentity:
    """The byte and canonical identities of one validated wheel."""

    schema: int
    canonical_format: str
    distribution: str
    version: str
    filename: str
    size: int
    file_count: int
    wheel_sha256: str
    wheel_contents_sha256: str

    def document(self) -> dict[str, object]:
        return asdict(self)


def _feed(hasher: Any, value: bytes) -> None:
    """Add one unambiguous length-prefixed value to a digest."""

    hasher.update(len(value).to_bytes(8, "big"))
    hasher.update(value)


def _safe_member(info: zipfile.ZipInfo) -> str:
    """Return one safe, canonical wheel member name."""

    name = info.filename
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or "\0" in name
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != name
    ):
        raise WheelIdentityError(f"wheel contains an unsafe member name: {name!r}")
    if info.is_dir() or name.endswith("/"):
        raise WheelIdentityError(f"wheel contains an explicit directory member: {name}")
    if info.flag_bits & 0x1:
        raise WheelIdentityError(f"wheel member is encrypted: {name}")
    member_mode = info.external_attr >> 16
    if stat.S_ISLNK(member_mode):
        raise WheelIdentityError(f"wheel contains a symbolic link: {name}")
    if info.file_size > MAX_MEMBER_BYTES:
        raise WheelIdentityError(f"wheel member is too large to inspect: {name}")
    return name


def _record_digest(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _validate_record(files: dict[str, bytes], record_name: str) -> None:
    """Require RECORD to describe every extracted file exactly once."""

    try:
        record_text = files[record_name].decode("utf-8")
        rows = list(csv.reader(io.StringIO(record_text, newline="")))
    except (UnicodeDecodeError, csv.Error) as error:
        raise WheelIdentityError(f"wheel RECORD is invalid: {error}") from error

    observed: set[str] = set()
    for row in rows:
        if len(row) != 3:
            raise WheelIdentityError("each wheel RECORD row must have exactly three fields")
        name, encoded_hash, encoded_size = row
        if name in observed:
            raise WheelIdentityError(f"wheel RECORD repeats {name}")
        if name not in files:
            raise WheelIdentityError(f"wheel RECORD names a missing file: {name}")
        observed.add(name)
        if name == record_name:
            if encoded_hash or encoded_size:
                raise WheelIdentityError("the wheel RECORD row for RECORD must be unhashed")
            continue
        expected_hash = f"sha256={_record_digest(files[name])}"
        if encoded_hash != expected_hash:
            raise WheelIdentityError(f"wheel RECORD hash differs for {name}")
        if encoded_size != str(len(files[name])):
            raise WheelIdentityError(f"wheel RECORD size differs for {name}")

    missing = set(files) - observed
    if missing:
        raise WheelIdentityError("wheel RECORD omits: " + ", ".join(sorted(missing)))


def _metadata(files: dict[str, bytes], dist_info: str) -> tuple[str, str]:
    metadata_name = f"{dist_info}/METADATA"
    if metadata_name not in files:
        raise WheelIdentityError("wheel does not contain its METADATA file")
    try:
        message = BytesParser().parsebytes(files[metadata_name])
    except (TypeError, ValueError) as error:
        raise WheelIdentityError(f"wheel METADATA is invalid: {error}") from error
    distribution = message.get("Name", "").strip()
    version = message.get("Version", "").strip()
    if (
        not distribution
        or not version
        or any(character in distribution + version for character in "\0\r\n")
    ):
        raise WheelIdentityError("wheel METADATA must contain single-line Name and Version")
    return distribution, version


def inspect_wheel(path: Path) -> WheelIdentity:
    """Validate one wheel and return its raw and canonical identities."""

    candidate = path.expanduser().resolve()
    if candidate.suffix != ".whl" or not candidate.is_file():
        raise WheelIdentityError(f"not one wheel file: {candidate}")
    size = candidate.stat().st_size
    if size <= 0 or size > MAX_WHEEL_BYTES:
        raise WheelIdentityError("wheel size is outside the supported inspection limit")

    raw_hasher = hashlib.sha256()
    with candidate.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            raw_hasher.update(block)

    try:
        with zipfile.ZipFile(candidate) as archive:
            infos = archive.infolist()
            names = [_safe_member(info) for info in infos]
            if len(names) != len(set(names)):
                raise WheelIdentityError("wheel contains duplicate member names")
            if sum(info.file_size for info in infos) > MAX_WHEEL_BYTES:
                raise WheelIdentityError("expanded wheel is too large to inspect")
            files = {name: archive.read(info) for name, info in zip(names, infos, strict=True)}
            modes = {
                name: (info.external_attr >> 16) & 0o7777
                for name, info in zip(names, infos, strict=True)
            }
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        if isinstance(error, WheelIdentityError):
            raise
        raise WheelIdentityError(f"could not read wheel: {error}") from error

    records = [name for name in files if name.endswith(".dist-info/RECORD")]
    if len(records) != 1:
        raise WheelIdentityError("wheel must contain exactly one dist-info RECORD")
    record_name = records[0]
    dist_info = record_name.removesuffix("/RECORD")
    if "/" in dist_info or not dist_info.endswith(".dist-info"):
        raise WheelIdentityError("wheel RECORD is not in one top-level dist-info directory")
    for name in files:
        if name.endswith(".dist-info/RECORD") and name != record_name:
            raise WheelIdentityError("wheel contains more than one dist-info directory")

    _validate_record(files, record_name)
    distribution, version = _metadata(files, dist_info)
    try:
        filename_distribution, filename_version, _, _ = parse_wheel_filename(candidate.name)
    except InvalidWheelFilename as error:
        raise WheelIdentityError(f"wheel filename is invalid: {error}") from error
    if filename_distribution != canonicalize_name(distribution):
        raise WheelIdentityError("wheel filename and METADATA name identify different projects")
    if filename_version != Version(version):
        raise WheelIdentityError("wheel filename and METADATA contain different versions")

    canonical = hashlib.sha256()
    _feed(canonical, CANONICAL_FORMAT.encode("ascii"))
    canonical_names = sorted(set(files) - {record_name})
    for name in canonical_names:
        _feed(canonical, name.encode("utf-8"))
        _feed(canonical, f"{modes[name]:04o}".encode("ascii"))
        _feed(canonical, files[name])

    return WheelIdentity(
        schema=1,
        canonical_format=CANONICAL_FORMAT,
        distribution=distribution,
        version=version,
        filename=candidate.name,
        size=size,
        file_count=len(files),
        wheel_sha256=raw_hasher.hexdigest(),
        wheel_contents_sha256=canonical.hexdigest(),
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("wheel", type=Path)
    result.add_argument("--output", type=Path)
    return result


def fail(message: str) -> NoReturn:
    print(f"canonical wheel inspection failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    try:
        identity = inspect_wheel(args.wheel)
        encoded = json.dumps(identity.document(), indent=2, sort_keys=True) + "\n"
        if args.output is None:
            print(encoded, end="")
        else:
            args.output.write_text(encoded, encoding="utf-8")
    except (OSError, WheelIdentityError) as error:
        fail(str(error))


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    main()
