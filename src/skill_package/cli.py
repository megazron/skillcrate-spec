"""skillpkg CLI: scaffold, validate, verify, check portability, adapt, compose."""
from __future__ import annotations

import argparse
import os
import sys

import yaml

from . import adapt as adapt_mod
from . import manifest, pack
from .registry import Registry
from .schema import Embodiment, SchemaError
from .verify import (verify_composition, verify_integrity, verify_portability,
                     verify_safety)

_SCAFFOLD = {
    "schema_version": 1,
    "name": "my_skill",
    "version": "0.1.0",
    "description": "what this skill does",
    "provenance": {
        "author": "you", "created": "2026-01-01", "source": "recorded",
        "captured_on": "my_arm", "episodes": [], "derived_from": [],
    },
    "embodiment": {
        "name": "my_arm", "dof": 7,
        "joint_names": ["j%d" % i for i in range(1, 8)],
        "ee_frame": "tool0", "gripper": "parallel", "control_mode": "position",
        "units": {"angle": "rad", "length": "m"},
    },
    "adaptation": {"joint_map": {}, "frame_transform": {}, "unit_conversion": {},
                   "workspace_bounds": {}, "requires": []},
    "safety": {
        "max_force_n": 20.0, "max_speed_mps": 0.25, "min_clearance_m": 0.10,
        "preconditions": ["gripper_open and object_visible"],
        "postconditions": ["object_grasped"],
        "verified": {},
    },
    "payload": [],
    "integrity": {},
}


def _load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _embodiment_from_file(path):
    return Embodiment.from_dict(_load_yaml(path), where=path)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="skillpkg",
        description="A versioned, checkable package format for robot skills.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="scaffold a new skill package directory")
    p.add_argument("dir")

    for name, helptext in [("validate", "schema-validate the manifest"),
                           ("verify", "recompute and check payload integrity")]:
        q = sub.add_parser(name, help=helptext)
        q.add_argument("pkg")

    q = sub.add_parser("verify-safety", help="check limits and preconditions")
    q.add_argument("pkg")
    q.add_argument("--robot", help="YAML with the target robot's limits")
    q.add_argument("--world", help="YAML with world-state facts")

    q = sub.add_parser("portability", help="check the adaptation contract to a target")
    q.add_argument("pkg")
    q.add_argument("--target", required=True)

    q = sub.add_parser("adapt", help="adapt a skill to a target embodiment")
    q.add_argument("pkg")
    q.add_argument("--target", required=True)
    q.add_argument("-o", "--out", required=True)

    q = sub.add_parser("compose", help="validate a composed skill's handoffs")
    q.add_argument("pkg")
    q.add_argument("--registry", required=True)

    q = sub.add_parser("pack", help="zip a package into a .skill archive")
    q.add_argument("dir")
    q.add_argument("-o", "--out", required=True)

    q = sub.add_parser("unpack", help="extract and integrity-check a .skill archive")
    q.add_argument("archive")
    q.add_argument("dest")

    sub.add_parser("selftest", help="build, adapt and compose an in-memory example")

    a = ap.parse_args(argv)

    try:
        return _dispatch(a)
    except (SchemaError, manifest.PackageError, adapt_mod.AdaptationError,
            pack.PackError) as e:
        print("ERROR:", e)
        return 2


def _dispatch(a):
    if a.cmd == "init":
        os.makedirs(a.dir, exist_ok=True)
        mpath = os.path.join(a.dir, manifest.MANIFEST_NAME)
        if os.path.exists(mpath):
            print("refusing to overwrite", mpath)
            return 2
        with open(mpath, "w") as f:
            yaml.safe_dump(_SCAFFOLD, f, sort_keys=False)
        print("wrote", mpath)
        return 0

    if a.cmd == "validate":
        m = manifest.load(a.pkg)
        print("OK: %s@%s  id=%s  (%d payload, %s)"
              % (m.name, m.version, m.id, len(m.payload),
                 "composed" if m.composition else m.provenance.source))
        return 0

    if a.cmd == "verify":
        m = manifest.load(a.pkg)
        r = verify_integrity(m)
        print(r.report())
        return 0 if r.ok else 1

    if a.cmd == "verify-safety":
        m = manifest.load(a.pkg)
        robot = _load_yaml(a.robot) if a.robot else None
        world = _load_yaml(a.world) if a.world else None
        r = verify_safety(m, robot, world)
        print(r.report())
        return 0 if r.ok else 1

    if a.cmd == "portability":
        m = manifest.load(a.pkg)
        t = _embodiment_from_file(a.target)
        r = verify_portability(m, t)
        print(r.report())
        return 0 if r.ok else 1

    if a.cmd == "adapt":
        m = manifest.load(a.pkg)
        t = _embodiment_from_file(a.target)
        out = adapt_mod.adapt(m, t)
        os.makedirs(a.out, exist_ok=True)
        # copy payloads across so the adapted package is self-contained
        src_dir = manifest.package_dir(m)
        for rel in out.payload:
            data = open(os.path.join(src_dir, rel), "rb").read()
            dst = os.path.join(a.out, rel)
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            open(dst, "wb").write(data)
        manifest.save(out, a.out)
        print("adapted %s -> %s@%s (target %s), wrote %s"
              % (m.name, out.name, out.version, t.name, a.out))
        return 0

    if a.cmd == "compose":
        m = manifest.load(a.pkg)
        reg = Registry(a.registry)
        r = verify_composition(m, reg)
        print(r.report())
        return 0 if r.ok else 1

    if a.cmd == "pack":
        out = pack.pack(a.dir, a.out)
        print("wrote", out)
        return 0

    if a.cmd == "unpack":
        pack.unpack(a.archive, a.dest)
        print("unpacked and verified into", a.dest)
        return 0

    if a.cmd == "selftest":
        return _selftest()
    return 0


def _selftest():
    import tempfile
    ok = True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print("  %-52s %s" % (name, "OK" if cond else "*** FAILED ***"))

    with tempfile.TemporaryDirectory() as d:
        pkgd = os.path.join(d, "pick")
        os.makedirs(pkgd)
        open(os.path.join(pkgd, "traj.csv"), "w").write("t,q\n0,0\n1,0.5\n")
        raw = dict(_SCAFFOLD)
        raw["name"] = "pick"
        raw["payload"] = ["traj.csv"]
        with open(os.path.join(pkgd, "skill.yaml"), "w") as f:
            yaml.safe_dump(raw, f, sort_keys=False)
        m = manifest.load(pkgd)
        manifest.save(m, pkgd)
        m = manifest.load(pkgd)
        check("manifest validates and has a content id", m.id.startswith("sk_"))
        check("integrity verifies", verify_integrity(m).ok)
        # tamper
        open(os.path.join(pkgd, "traj.csv"), "a").write("2,9\n")
        check("integrity catches a tampered payload", not verify_integrity(m).ok)
        # safety
        r = verify_safety(m, {"max_force_n": 10.0}, {"gripper_open": True,
                                                     "object_visible": True})
        check("safety refuses a force limit above the robot's", not r.ok)
        r = verify_safety(m, {"max_force_n": 30.0, "max_speed_mps": 1.0,
                              "min_clearance_m": 0.2},
                          {"gripper_open": False, "object_visible": True})
        check("safety refuses when a precondition is false", not r.ok)
        # portability
        tgt = Embodiment.from_dict({
            "name": "other", "dof": 7,
            "joint_names": ["a%d" % i for i in range(1, 8)],
            "ee_frame": "tool0"})
        check("portability catches an undeclared joint remap",
              not verify_portability(m, tgt).ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
