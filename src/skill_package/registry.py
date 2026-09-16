"""A minimal on-disk registry: a directory of skill packages.

Used to resolve sub-skills for composition and to walk lineage. A package is
resolvable by its content id, by ``name@version``, or by bare ``name`` (latest
version wins).
"""
from __future__ import annotations

import os

from . import manifest
from .schema import Manifest


def _semver_key(v: str):
    core = v.split("+")[0].split("-")[0]
    try:
        return tuple(int(x) for x in core.split("."))
    except ValueError:
        return (0, 0, 0)


class Registry:
    def __init__(self, root: str):
        self.root = root
        self._by_id = {}
        self._by_name = {}
        if os.path.isdir(root):
            self._scan()

    def _scan(self):
        for entry in sorted(os.listdir(self.root)):
            d = os.path.join(self.root, entry)
            if os.path.isfile(os.path.join(d, manifest.MANIFEST_NAME)):
                try:
                    m = manifest.load(d)
                except Exception:                               # noqa: BLE001
                    continue
                self._index(m)

    def _index(self, m: Manifest):
        self._by_id[m.id] = m
        self._by_name.setdefault(m.name, []).append(m)

    def add(self, m: Manifest):
        self._index(m)
        return m

    def get(self, skill_id: str):
        return self._by_id.get(skill_id)

    def resolve(self, ref: str):
        """Resolve by id, name@version, or bare name (latest)."""
        if ref in self._by_id:
            return self._by_id[ref]
        if "@" in ref:
            name, ver = ref.split("@", 1)
            for m in self._by_name.get(name, []):
                if m.version == ver:
                    return m
            return None
        cands = self._by_name.get(ref, [])
        if not cands:
            return None
        return max(cands, key=lambda m: _semver_key(m.version))

    def lineage(self, skill_id: str):
        """The chain of parent ids for a skill, oldest last."""
        m = self.get(skill_id)
        if not m:
            return []
        return list(m.provenance.derived_from)

    def __len__(self):
        return len(self._by_id)
