"""Load and save a skill package, compute its content id, and hash payloads.

A package is a directory containing ``skill.yaml`` and any payload files it
names. The package ``id`` is a content hash over the canonical manifest (minus
the id itself) plus the payload integrity map, so the same skill always hashes
to the same id and any change to content or payload changes it.
"""
from __future__ import annotations

import hashlib
import json
import os

import yaml

from .schema import Manifest, SchemaError

MANIFEST_NAME = "skill.yaml"


class PackageError(ValueError):
    """The package directory or its files are missing or unreadable."""


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_id(m: Manifest) -> str:
    """A stable content id: sha256 over the manifest (without id) + integrity."""
    body = m.to_dict(include_id=False)
    body.pop("integrity", None)
    payload = {"manifest": body, "integrity": dict(sorted(m.integrity.items()))}
    return "sk_" + hashlib.sha256(_canonical(payload).encode()).hexdigest()[:24]


def build_integrity(pkg_dir: str, payload_paths) -> dict:
    """{relative path -> sha256} for every declared payload file."""
    out = {}
    for rel in payload_paths:
        p = os.path.join(pkg_dir, rel)
        if not os.path.isfile(p):
            raise PackageError("payload file %r declared but not found in %s"
                               % (rel, pkg_dir))
        out[rel] = sha256_file(p)
    return dict(sorted(out.items()))


def load(pkg_dir: str, *, validate=True, recompute_id=True) -> Manifest:
    """Load a package directory into a validated Manifest with its id filled."""
    if os.path.isfile(pkg_dir) and pkg_dir.endswith(MANIFEST_NAME):
        pkg_dir = os.path.dirname(pkg_dir) or "."
    mpath = os.path.join(pkg_dir, MANIFEST_NAME)
    if not os.path.isfile(mpath):
        raise PackageError("no %s in %s" % (MANIFEST_NAME, pkg_dir))
    with open(mpath) as f:
        raw = yaml.safe_load(f) or {}
    m = Manifest.from_dict(raw)
    if validate:
        m.validate()
    if recompute_id:
        m.id = compute_id(m)
    m._dir = pkg_dir  # type: ignore[attr-defined]
    return m


def save(m: Manifest, pkg_dir: str, *, refresh_integrity=True) -> str:
    """Write skill.yaml into pkg_dir, refreshing integrity and id first."""
    os.makedirs(pkg_dir, exist_ok=True)
    if refresh_integrity:
        m.integrity = build_integrity(pkg_dir, m.payload)
    m.id = compute_id(m)
    mpath = os.path.join(pkg_dir, MANIFEST_NAME)
    with open(mpath, "w") as f:
        yaml.safe_dump(m.to_dict(include_id=True), f, sort_keys=False)
    return mpath


def package_dir(m: Manifest) -> str:
    d = getattr(m, "_dir", None)
    if not d:
        raise PackageError("this manifest was not loaded from a directory")
    return d
