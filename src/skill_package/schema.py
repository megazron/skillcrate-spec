"""The skill.yaml manifest schema, as dataclasses, plus a validator.

The schema is deliberately strict and versioned: every field the six open
properties need has a place, and `validate()` fails with a precise message
naming the field and the package when anything is missing or malformed. That
is the "standardisation" property -- a format a tool can check, not a
convention in a README.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import expr

SCHEMA_VERSION = 1
SOURCE_KINDS = ("recorded", "learned", "authored", "composed")
CONTROL_MODES = ("position", "velocity", "effort", "cartesian_pose", "cartesian_twist")

_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class SchemaError(ValueError):
    """A manifest is malformed; the message names the field and the package."""


def _req(d, key, where):
    if key not in d or d[key] in (None, ""):
        raise SchemaError("%s is missing required field %r" % (where, key))
    return d[key]


@dataclass
class Embodiment:
    name: str
    dof: int
    joint_names: list
    ee_frame: str
    gripper: str = "none"
    control_mode: str = "position"
    units: dict = field(default_factory=lambda: {"angle": "rad", "length": "m"})

    @staticmethod
    def from_dict(d, where="embodiment"):
        if not isinstance(d, dict):
            raise SchemaError("%s must be a mapping" % where)
        dof = _req(d, "dof", where)
        jn = _req(d, "joint_names", where)
        if not isinstance(dof, int) or dof <= 0:
            raise SchemaError("%s.dof must be a positive integer" % where)
        if not isinstance(jn, list) or len(jn) != dof:
            raise SchemaError(
                "%s.joint_names must be a list of length dof (%d), got %r"
                % (where, dof, jn))
        cm = d.get("control_mode", "position")
        if cm not in CONTROL_MODES:
            raise SchemaError("%s.control_mode %r not in %s" % (where, cm, CONTROL_MODES))
        return Embodiment(
            name=_req(d, "name", where), dof=dof, joint_names=list(jn),
            ee_frame=_req(d, "ee_frame", where), gripper=d.get("gripper", "none"),
            control_mode=cm,
            units=d.get("units", {"angle": "rad", "length": "m"}))

    def to_dict(self):
        return {"name": self.name, "dof": self.dof, "joint_names": self.joint_names,
                "ee_frame": self.ee_frame, "gripper": self.gripper,
                "control_mode": self.control_mode, "units": self.units}


@dataclass
class Provenance:
    author: str
    created: str
    source: str
    captured_on: str            # embodiment name
    episodes: list = field(default_factory=list)     # [{id, sha256}]
    derived_from: list = field(default_factory=list)  # parent skill ids

    @staticmethod
    def from_dict(d, where="provenance"):
        if not isinstance(d, dict):
            raise SchemaError("%s must be a mapping" % where)
        src = _req(d, "source", where)
        if src not in SOURCE_KINDS:
            raise SchemaError("%s.source %r not in %s" % (where, src, SOURCE_KINDS))
        return Provenance(
            author=_req(d, "author", where), created=str(_req(d, "created", where)),
            source=src, captured_on=_req(d, "captured_on", where),
            episodes=list(d.get("episodes", [])),
            derived_from=list(d.get("derived_from", [])))

    def to_dict(self):
        return {"author": self.author, "created": self.created,
                "source": self.source, "captured_on": self.captured_on,
                "episodes": self.episodes, "derived_from": self.derived_from}


@dataclass
class Adaptation:
    """What must be remapped for this skill to run on another embodiment."""
    joint_map: dict = field(default_factory=dict)      # source_joint -> target_joint
    frame_transform: dict = field(default_factory=dict)  # e.g. {ee_frame: "tool0"}
    unit_conversion: dict = field(default_factory=dict)  # e.g. {angle: "deg->rad"}
    workspace_bounds: dict = field(default_factory=dict)
    requires: list = field(default_factory=list)       # names of remaps that MUST be provided

    @staticmethod
    def from_dict(d, where="adaptation"):
        d = d or {}
        if not isinstance(d, dict):
            raise SchemaError("%s must be a mapping" % where)
        return Adaptation(
            joint_map=dict(d.get("joint_map", {})),
            frame_transform=dict(d.get("frame_transform", {})),
            unit_conversion=dict(d.get("unit_conversion", {})),
            workspace_bounds=dict(d.get("workspace_bounds", {})),
            requires=list(d.get("requires", [])))

    def to_dict(self):
        return {"joint_map": self.joint_map, "frame_transform": self.frame_transform,
                "unit_conversion": self.unit_conversion,
                "workspace_bounds": self.workspace_bounds, "requires": self.requires}


@dataclass
class Safety:
    max_force_n: float | None = None
    max_speed_mps: float | None = None
    min_clearance_m: float | None = None
    preconditions: list = field(default_factory=list)
    postconditions: list = field(default_factory=list)
    verified: dict = field(default_factory=dict)   # {tool, when, result, checks}

    @staticmethod
    def from_dict(d, where="safety"):
        d = d or {}
        if not isinstance(d, dict):
            raise SchemaError("%s must be a mapping" % where)
        pre = list(d.get("preconditions", []))
        post = list(d.get("postconditions", []))
        for label, conds in (("preconditions", pre), ("postconditions", post)):
            for c in conds:
                try:
                    expr.check_parses(c)
                except expr.UnsafeExpression as e:
                    raise SchemaError("%s.%s: %s" % (where, label, e))
        return Safety(
            max_force_n=d.get("max_force_n"), max_speed_mps=d.get("max_speed_mps"),
            min_clearance_m=d.get("min_clearance_m"),
            preconditions=pre, postconditions=post, verified=dict(d.get("verified", {})))

    def to_dict(self):
        return {"max_force_n": self.max_force_n, "max_speed_mps": self.max_speed_mps,
                "min_clearance_m": self.min_clearance_m,
                "preconditions": self.preconditions,
                "postconditions": self.postconditions, "verified": self.verified}


@dataclass
class Step:
    skill: str                  # sub-skill id or name@version
    bind: dict = field(default_factory=dict)

    @staticmethod
    def from_dict(d, where="composition.steps[]"):
        if not isinstance(d, dict):
            raise SchemaError("%s must be a mapping" % where)
        return Step(skill=_req(d, "skill", where), bind=dict(d.get("bind", {})))

    def to_dict(self):
        return {"skill": self.skill, "bind": self.bind}


@dataclass
class Composition:
    kind: str = "sequence"      # sequence | tree (tree reserved)
    steps: list = field(default_factory=list)

    @staticmethod
    def from_dict(d, where="composition"):
        if not d:
            return None
        if not isinstance(d, dict):
            raise SchemaError("%s must be a mapping" % where)
        steps = [Step.from_dict(s) for s in d.get("steps", [])]
        if not steps:
            raise SchemaError("%s has no steps" % where)
        return Composition(kind=d.get("kind", "sequence"), steps=steps)

    def to_dict(self):
        return {"kind": self.kind, "steps": [s.to_dict() for s in self.steps]}


@dataclass
class Manifest:
    schema_version: int
    name: str
    version: str
    description: str
    provenance: Provenance
    embodiment: Embodiment
    adaptation: Adaptation
    safety: Safety
    integrity: dict = field(default_factory=dict)      # path -> sha256
    payload: list = field(default_factory=list)        # payload file paths
    composition: Composition | None = None
    id: str = ""                                       # content hash, filled by manifest.py

    @staticmethod
    def from_dict(d, where="skill.yaml"):
        if not isinstance(d, dict):
            raise SchemaError("%s must be a mapping" % where)
        sv = d.get("schema_version", SCHEMA_VERSION)
        if sv != SCHEMA_VERSION:
            raise SchemaError(
                "%s schema_version %r is not supported (this tool speaks %d)"
                % (where, sv, SCHEMA_VERSION))
        name = _req(d, "name", where)
        ver = str(_req(d, "version", where))
        if not _SEMVER.match(ver):
            raise SchemaError(
                "%s.version %r is not semver (expected MAJOR.MINOR.PATCH)"
                % (where, ver))
        return Manifest(
            schema_version=sv, name=name, version=ver,
            description=d.get("description", ""),
            provenance=Provenance.from_dict(_req(d, "provenance", where)),
            embodiment=Embodiment.from_dict(_req(d, "embodiment", where)),
            adaptation=Adaptation.from_dict(d.get("adaptation")),
            safety=Safety.from_dict(d.get("safety")),
            integrity=dict(d.get("integrity", {})),
            payload=list(d.get("payload", [])),
            composition=Composition.from_dict(d.get("composition")),
            id=d.get("id", ""))

    def to_dict(self, include_id=True):
        out = {
            "schema_version": self.schema_version, "name": self.name,
            "version": self.version, "description": self.description,
            "provenance": self.provenance.to_dict(),
            "embodiment": self.embodiment.to_dict(),
            "adaptation": self.adaptation.to_dict(),
            "safety": self.safety.to_dict(),
            "payload": self.payload, "integrity": self.integrity,
        }
        if self.composition:
            out["composition"] = self.composition.to_dict()
        if include_id and self.id:
            out["id"] = self.id
        return out

    def validate(self):
        # cross-field: provenance.captured_on should match the embodiment name
        if self.provenance.captured_on != self.embodiment.name:
            raise SchemaError(
                "provenance.captured_on %r does not match embodiment.name %r"
                % (self.provenance.captured_on, self.embodiment.name))
        if self.provenance.source == "composed" and not self.composition:
            raise SchemaError(
                "provenance.source is 'composed' but there is no composition block")
        if self.composition and self.provenance.source != "composed":
            raise SchemaError(
                "a composition block requires provenance.source == 'composed'")
        return True
