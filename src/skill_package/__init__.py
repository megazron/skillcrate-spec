"""skillcrate-spec: a versioned, checkable package format for robot skills.

Makes the six properties commercial one-tap skills lack -- adaptation,
cross-embodiment portability, provenance, safety verification, composition and
standardisation -- explicit in a manifest and checkable by tooling.
"""
from . import adapt, expr, manifest, pack, registry, schema, verify
from .registry import Registry
from .schema import (Adaptation, Composition, Embodiment, Manifest, Provenance,
                     Safety, SchemaError, Step)
from .verify import Result

__version__ = "0.1.0"
__all__ = [
    "schema", "manifest", "expr", "verify", "adapt", "registry", "pack",
    "Manifest", "Embodiment", "Provenance", "Adaptation", "Safety",
    "Composition", "Step", "SchemaError", "Result", "Registry",
]
