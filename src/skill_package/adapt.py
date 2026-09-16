"""Apply a skill's declared adaptation to a target embodiment.

This is the concrete difference between static playback and a portable skill:
the manifest DECLARES how to remap onto another robot, and `adapt()` performs
exactly that remap, or refuses and names the mapping that is missing. It never
guesses.
"""
from __future__ import annotations

import copy

from .schema import Embodiment, Manifest
from .verify import verify_portability


class AdaptationError(ValueError):
    """The skill cannot be adapted to the target; the message says what is missing."""


_UNIT_FACTOR = {
    "deg->rad": 0.017453292519943295,
    "rad->deg": 57.29577951308232,
    "mm->m": 0.001, "m->mm": 1000.0,
    "identity": 1.0,
}


def unit_factor(spec: str) -> float:
    if spec not in _UNIT_FACTOR:
        raise AdaptationError(
            "unknown unit conversion %r (known: %s)" % (spec, sorted(_UNIT_FACTOR)))
    return _UNIT_FACTOR[spec]


def adapt(m: Manifest, target: Embodiment) -> Manifest:
    """Return a new Manifest re-expressed for `target`, or raise AdaptationError.

    Portability is checked first; an undeclared remap is a refusal, not a
    silent best-effort. The returned manifest records the adaptation it applied
    in provenance.derived_from and keeps its own new content id on save.
    """
    port = verify_portability(m, target)
    if not port.ok:
        raise AdaptationError(
            "cannot adapt %s@%s to %s:\n  - %s"
            % (m.name, m.version, target.name, "\n  - ".join(port.findings)))

    out = copy.deepcopy(m)
    a = m.adaptation

    # joints: remap the embodiment onto the target's joint names/dof
    if a.joint_map:
        new_names = [a.joint_map.get(j, j) for j in m.embodiment.joint_names]
    else:
        new_names = list(target.joint_names)
    out.embodiment = Embodiment(
        name=target.name, dof=target.dof, joint_names=new_names,
        ee_frame=a.frame_transform.get("ee_frame", target.ee_frame),
        gripper=target.gripper, control_mode=target.control_mode,
        units=dict(target.units))

    # record the units conversion applied (for downstream payload rescaling)
    applied = {"joint_map": a.joint_map, "frame_transform": a.frame_transform,
               "unit_conversion": {}}
    for kind, spec in a.unit_conversion.items():
        applied["unit_conversion"][kind] = {"spec": spec, "factor": unit_factor(spec)}

    out.provenance.derived_from = list(m.provenance.derived_from) + [m.id]
    out.provenance.source = "authored"
    out.provenance.captured_on = target.name
    out.description = (m.description + " [adapted to %s]" % target.name).strip()
    # bump patch version so the adapted skill is a distinct artifact
    major, minor, patch = (m.version.split("+")[0].split("-")[0]).split(".")
    out.version = "%s.%s.%d" % (major, minor, int(patch) + 1)
    out._adaptation_applied = applied  # type: ignore[attr-defined]
    return out
