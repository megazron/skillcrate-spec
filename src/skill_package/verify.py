"""The four checks that turn the six properties from prose into gates.

Every function returns a `Result(ok, findings)` where a finding names exactly
what failed and why. Nothing here silently passes: an unknown, an unsatisfiable
remap and a limit the target cannot honour are all failures with reasons.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import expr, manifest
from .schema import Embodiment, Manifest


@dataclass
class Result:
    ok: bool
    findings: list = field(default_factory=list)

    def __bool__(self):
        return self.ok

    def report(self):
        head = "OK" if self.ok else "FAILED"
        return head + "".join("\n  - " + f for f in self.findings)


# ------------------------------------------------------------------ integrity
def verify_integrity(m: Manifest, pkg_dir: str | None = None) -> Result:
    """Recompute every payload hash and compare with the manifest."""
    pkg_dir = pkg_dir or manifest.package_dir(m)
    findings = []
    declared = set(m.integrity)
    listed = set(m.payload)
    if declared != listed:
        only_i = declared - listed
        only_p = listed - declared
        if only_i:
            findings.append("integrity lists files not in payload: %s" % sorted(only_i))
        if only_p:
            findings.append("payload files with no integrity hash: %s" % sorted(only_p))
    for rel, want in m.integrity.items():
        p = os.path.join(pkg_dir, rel)
        if not os.path.isfile(p):
            findings.append("payload %r is missing" % rel)
            continue
        got = manifest.sha256_file(p)
        if got != want:
            findings.append("payload %r hash mismatch: manifest %s, file %s"
                            % (rel, want[:12], got[:12]))
    return Result(not findings, findings)


# --------------------------------------------------------------------- safety
def verify_safety(m: Manifest, robot_limits: dict | None = None,
                  world_state: dict | None = None) -> Result:
    """Refuse a skill whose declared limits exceed the robot's, or whose
    preconditions are false in the given world state."""
    findings = []
    s = m.safety
    rl = robot_limits or {}
    checks = (("max_force_n", "force"), ("max_speed_mps", "speed"),
              ("min_clearance_m", "clearance"))
    for attr, label in checks:
        skill_val = getattr(s, attr)
        if skill_val is None:
            continue
        cap = rl.get(attr)
        if cap is None:
            findings.append(
                "skill declares %s %s but the robot declares no %s limit to "
                "check it against" % (label, skill_val, label))
            continue
        # force/speed: skill must not exceed the robot's max.
        # clearance: skill's required minimum must not exceed what the robot can keep.
        if attr == "min_clearance_m":
            if skill_val > cap:
                findings.append(
                    "skill needs %s of %s m but the robot can only keep %s m"
                    % (label, skill_val, cap))
        else:
            if skill_val > cap:
                findings.append(
                    "skill assumes %s up to %s but the robot's limit is %s"
                    % (label, skill_val, cap))
    if world_state is not None:
        for c in s.preconditions:
            try:
                if not expr.evaluate(c, world_state):
                    findings.append("precondition not met: %s" % c)
            except expr.ConditionError as e:
                findings.append(str(e))
    return Result(not findings, findings)


# ---------------------------------------------------------------- portability
def verify_portability(m: Manifest, target: Embodiment) -> Result:
    """Is every required remap declared, and can it map onto the target?"""
    findings = []
    a = m.adaptation
    src = m.embodiment
    same = (target.dof == src.dof
            and target.joint_names == src.joint_names
            and target.units == src.units
            and target.ee_frame == src.ee_frame)
    if same and not a.requires:
        return Result(True, ["identical embodiment; no adaptation needed"])
    # every declared requirement must be satisfied by a provided remap
    provided = {
        "joint_map": a.joint_map, "frame_transform": a.frame_transform,
        "unit_conversion": a.unit_conversion, "workspace_bounds": a.workspace_bounds,
    }
    for req in a.requires:
        if not provided.get(req):
            findings.append(
                "adaptation.requires lists %r but adaptation.%s is empty" % (req, req))
    # if dof/joints differ, a joint_map covering every source joint is needed
    if target.joint_names != src.joint_names:
        if not a.joint_map:
            findings.append(
                "target joints %s differ from source %s but no joint_map is declared"
                % (target.joint_names, src.joint_names))
        else:
            unmapped = [j for j in src.joint_names if j not in a.joint_map]
            if unmapped:
                findings.append("joint_map does not cover source joints %s" % unmapped)
            bad = [t for t in a.joint_map.values() if t not in target.joint_names]
            if bad:
                findings.append("joint_map targets joints not on the target: %s" % bad)
    if target.units != src.units and not a.unit_conversion:
        findings.append("units differ (%s vs %s) but no unit_conversion is declared"
                        % (src.units, target.units))
    if target.ee_frame != src.ee_frame and "ee_frame" not in a.frame_transform:
        findings.append("ee_frame differs (%s vs %s) but frame_transform has no ee_frame"
                        % (src.ee_frame, target.ee_frame))
    return Result(not findings, findings)


# --------------------------------------------------------------- composition
def verify_composition(m: Manifest, registry) -> Result:
    """Each step must resolve, and step N's postconditions must satisfy step
    N+1's preconditions (a declared, checked handoff, not a bare concatenation)."""
    findings = []
    if not m.composition:
        return Result(False, ["this skill has no composition block"])
    resolved = []
    for st in m.composition.steps:
        sub = registry.resolve(st.skill)
        if sub is None:
            findings.append("step %r does not resolve in the registry" % st.skill)
            resolved.append(None)
        else:
            resolved.append(sub)
    for i in range(len(resolved) - 1):
        a, b = resolved[i], resolved[i + 1]
        if a is None or b is None:
            continue
        post = set(a.safety.postconditions)
        for pre in b.safety.preconditions:
            if pre not in post:
                findings.append(
                    "handoff gap: step %d (%s) does not establish precondition "
                    "%r that step %d (%s) requires"
                    % (i + 1, a.name, pre, i + 2, b.name))
    return Result(not findings, findings)
