"""Build and open a ``.skill`` archive (a zip of a package directory).

Packing refreshes the integrity map so the archive is self-describing;
unpacking verifies every payload hash and refuses an archive that has been
tampered with.
"""
from __future__ import annotations

import os
import zipfile

from . import manifest
from .verify import verify_integrity


class PackError(ValueError):
    pass


def pack(pkg_dir: str, out_path: str) -> str:
    """Zip a package directory into out_path (…/x.skill), integrity refreshed."""
    m = manifest.load(pkg_dir, recompute_id=True)
    m.integrity = manifest.build_integrity(pkg_dir, m.payload)
    manifest.save(m, pkg_dir, refresh_integrity=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(pkg_dir, manifest.MANIFEST_NAME), manifest.MANIFEST_NAME)
        for rel in m.payload:
            z.write(os.path.join(pkg_dir, rel), rel)
    return out_path


def unpack(archive: str, dest_dir: str, *, verify=True) -> str:
    """Extract a .skill archive into dest_dir and verify payload integrity."""
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if name.startswith("/") or ".." in name.split("/"):
                raise PackError("archive contains an unsafe path: %r" % name)
        z.extractall(dest_dir)
    m = manifest.load(dest_dir)
    if verify:
        r = verify_integrity(m, dest_dir)
        if not r.ok:
            raise PackError("unpacked archive fails integrity:\n" + r.report())
    return dest_dir
