import copy
import os
import subprocess
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from skill_package import adapt as adapt_mod                       # noqa: E402
from skill_package import expr, manifest, pack                     # noqa: E402
from skill_package.registry import Registry                        # noqa: E402
from skill_package.schema import (Embodiment, Manifest, SchemaError)  # noqa: E402
from skill_package.verify import (verify_composition,              # noqa: E402
                                  verify_integrity, verify_portability,
                                  verify_safety)

ROOT = os.path.join(os.path.dirname(__file__), "..")
EX = os.path.join(ROOT, "examples")


# ------------------------------------------------------------ minimal builders
def _min_manifest(**over):
    d = {
        "schema_version": 1, "name": "s", "version": "1.0.0", "description": "d",
        "provenance": {"author": "a", "created": "2026-01-01", "source": "recorded",
                       "captured_on": "arm"},
        "embodiment": {"name": "arm", "dof": 2, "joint_names": ["a", "b"],
                       "ee_frame": "tool"},
        "adaptation": {}, "safety": {}, "payload": [], "integrity": {},
    }
    d.update(over)
    return d


def _write_pkg(tmp_path, manifest_dict, payloads=None):
    d = tmp_path / "pkg"
    d.mkdir()
    for name, content in (payloads or {}).items():
        (d / name).write_text(content)
    (d / "skill.yaml").write_text(yaml.safe_dump(manifest_dict, sort_keys=False))
    return str(d)


# --------------------------------------------------------------------- schema
def test_valid_manifest_loads():
    m = Manifest.from_dict(_min_manifest())
    assert m.validate() is True


def test_bad_semver_rejected():
    with pytest.raises(SchemaError):
        Manifest.from_dict(_min_manifest(version="1.0"))


def test_missing_provenance_rejected():
    d = _min_manifest()
    del d["provenance"]
    with pytest.raises(SchemaError):
        Manifest.from_dict(d)


def test_joint_names_length_must_match_dof():
    d = _min_manifest(embodiment={"name": "arm", "dof": 3,
                                  "joint_names": ["a", "b"], "ee_frame": "t"})
    with pytest.raises(SchemaError):
        Manifest.from_dict(d)


def test_captured_on_must_match_embodiment():
    d = _min_manifest()
    d["provenance"]["captured_on"] = "other"
    with pytest.raises(SchemaError):
        Manifest.from_dict(d).validate()


def test_composition_requires_composed_source():
    d = _min_manifest(composition={"kind": "sequence",
                                   "steps": [{"skill": "x"}]})
    with pytest.raises(SchemaError):
        Manifest.from_dict(d).validate()


def test_unparseable_precondition_rejected():
    d = _min_manifest(safety={"preconditions": ["a +"]})
    with pytest.raises(SchemaError):
        Manifest.from_dict(d)


# ----------------------------------------------------------------------- expr
def test_expr_safe_subset_evaluates():
    assert expr.evaluate("a and b > 2", {"a": True, "b": 3}) is True
    assert expr.evaluate("not open or x < 0", {"open": True, "x": 5}) is False


def test_expr_rejects_dunder_and_calls():
    for bad in ("__import__('os')", "a.b", "open('x')", "[i for i in a]"):
        with pytest.raises(expr.UnsafeExpression):
            expr.check_parses(bad)


def test_expr_missing_fact_is_condition_error():
    with pytest.raises(expr.ConditionError):
        expr.evaluate("missing_fact", {})


def test_names_used():
    assert expr.names_used("a and b > c") == {"a", "b", "c"}


# ------------------------------------------------------------------ integrity
def test_content_id_is_stable_and_content_sensitive(tmp_path):
    p = _write_pkg(tmp_path, _min_manifest(name="k", payload=["t.txt"]),
                   {"t.txt": "hello"})
    m1 = manifest.load(p)
    manifest.save(m1, p)
    id1 = manifest.load(p).id
    id2 = manifest.load(p).id
    assert id1 == id2 and id1.startswith("sk_")
    (tmp_path / "pkg" / "t.txt").write_text("changed")
    manifest.save(manifest.load(p), p)
    assert manifest.load(p).id != id1


def test_integrity_catches_tampering(tmp_path):
    p = _write_pkg(tmp_path, _min_manifest(name="k", payload=["t.txt"]),
                   {"t.txt": "data"})
    manifest.save(manifest.load(p), p)
    m = manifest.load(p)
    assert verify_integrity(m).ok
    (tmp_path / "pkg" / "t.txt").write_text("tampered")
    assert not verify_integrity(m).ok


def test_missing_payload_hash_is_flagged(tmp_path):
    d = _min_manifest(name="k", payload=["t.txt"], integrity={})
    p = _write_pkg(tmp_path, d, {"t.txt": "x"})
    m = manifest.load(p)  # integrity empty, payload listed
    r = verify_integrity(m)
    assert not r.ok and any("no integrity hash" in f for f in r.findings)


# --------------------------------------------------------------------- safety
def test_safety_refuses_force_over_robot_limit():
    m = Manifest.from_dict(_min_manifest(safety={"max_force_n": 20.0}))
    assert not verify_safety(m, {"max_force_n": 10.0}, {}).ok
    assert verify_safety(m, {"max_force_n": 25.0}, {}).ok


def test_safety_refuses_false_precondition():
    m = Manifest.from_dict(_min_manifest(safety={"preconditions": ["ready"]}))
    assert not verify_safety(m, {}, {"ready": False}).ok
    assert verify_safety(m, {}, {"ready": True}).ok


def test_safety_flags_clearance_the_robot_cannot_keep():
    m = Manifest.from_dict(_min_manifest(safety={"min_clearance_m": 0.20}))
    assert not verify_safety(m, {"min_clearance_m": 0.10}, {}).ok


# ---------------------------------------------------------------- portability
def _src():
    return Manifest.from_dict(_min_manifest(
        name="k",
        embodiment={"name": "arm", "dof": 2, "joint_names": ["a", "b"],
                    "ee_frame": "tool", "units": {"angle": "rad", "length": "m"}}))


def test_portability_missing_remap_then_satisfied():
    m = _src()
    target = Embodiment.from_dict({"name": "t", "dof": 2,
                                   "joint_names": ["x", "y"], "ee_frame": "tool"})
    assert not verify_portability(m, target).ok
    m.adaptation.joint_map = {"a": "x", "b": "y"}
    m.adaptation.requires = ["joint_map"]
    assert verify_portability(m, target).ok


def test_adapt_applies_the_remap():
    m = _src()
    target = Embodiment.from_dict({"name": "t", "dof": 2,
                                   "joint_names": ["x", "y"], "ee_frame": "tip",
                                   "units": {"angle": "deg", "length": "m"}})
    m.adaptation.joint_map = {"a": "x", "b": "y"}
    m.adaptation.unit_conversion = {"angle": "rad->deg"}
    m.adaptation.frame_transform = {"ee_frame": "tip"}
    m.adaptation.requires = ["joint_map", "unit_conversion", "frame_transform"]
    out = adapt_mod.adapt(m, target)
    assert out.embodiment.joint_names == ["x", "y"]
    assert out.embodiment.ee_frame == "tip"
    assert out.id != m.id or out.version != m.version
    assert m.id in out.provenance.derived_from


def test_adapt_refuses_when_incomplete():
    m = _src()
    target = Embodiment.from_dict({"name": "t", "dof": 2,
                                   "joint_names": ["x", "y"], "ee_frame": "tool"})
    with pytest.raises(adapt_mod.AdaptationError):
        adapt_mod.adapt(m, target)


# --------------------------------------------------------------- composition
def _grasp_and_place():
    pick = Manifest.from_dict(_min_manifest(
        name="pick", safety={"postconditions": ["grasped"]}))
    place = Manifest.from_dict(_min_manifest(
        name="place", safety={"preconditions": ["grasped"],
                              "postconditions": ["placed"]}))
    comp = Manifest.from_dict(_min_manifest(
        name="pnp",
        provenance={"author": "a", "created": "2026", "source": "composed",
                    "captured_on": "arm"},
        composition={"kind": "sequence",
                     "steps": [{"skill": "pick"}, {"skill": "place"}]}))
    return pick, place, comp


def test_composition_handoff_ok():
    pick, place, comp = _grasp_and_place()
    reg = Registry("/nonexistent")
    reg.add(pick)
    reg.add(place)
    assert verify_composition(comp, reg).ok


def test_composition_handoff_gap_caught():
    pick, place, comp = _grasp_and_place()
    place.safety.preconditions = ["on_conveyor"]  # not established by pick
    reg = Registry("/nonexistent")
    reg.add(pick)
    reg.add(place)
    r = verify_composition(comp, reg)
    assert not r.ok and any("handoff gap" in f for f in r.findings)


def test_composition_unresolved_step_caught():
    pick, place, comp = _grasp_and_place()
    reg = Registry("/nonexistent")
    reg.add(pick)  # place not registered
    r = verify_composition(comp, reg)
    assert not r.ok and any("does not resolve" in f for f in r.findings)


# ----------------------------------------------------------------------- pack
def test_pack_unpack_round_trip(tmp_path):
    p = _write_pkg(tmp_path, _min_manifest(name="k", payload=["t.txt"]),
                   {"t.txt": "payload"})
    manifest.save(manifest.load(p), p)
    arc = str(tmp_path / "k.skill")
    pack.pack(p, arc)
    dest = str(tmp_path / "out")
    pack.unpack(arc, dest)
    assert manifest.load(dest).name == "k"


def test_unpack_rejects_tampered_archive(tmp_path):
    import zipfile
    p = _write_pkg(tmp_path, _min_manifest(name="k", payload=["t.txt"]),
                   {"t.txt": "payload"})
    manifest.save(manifest.load(p), p)
    arc = str(tmp_path / "k.skill")
    pack.pack(p, arc)
    # rewrite the payload inside the zip
    import shutil
    tampered = str(tmp_path / "bad.skill")
    shutil.copy(arc, tampered)
    with zipfile.ZipFile(arc) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
    data["t.txt"] = b"evil"
    with zipfile.ZipFile(tampered, "w") as z:
        for n, b in data.items():
            z.writestr(n, b)
    with pytest.raises(pack.PackError):
        pack.unpack(tampered, str(tmp_path / "out2"))


# ------------------------------------------------------------------ examples
def test_example_packages_validate():
    for name in ("pick_cube", "place", "pick_and_place"):
        m = manifest.load(os.path.join(EX, name))
        assert m.validate() is True


# ----------------------------------------------------------------------- cli
def _cli(*args):
    return subprocess.run([sys.executable, "-m", "skill_package.cli", *args],
                          cwd=ROOT, env=dict(os.environ, PYTHONPATH="src"),
                          capture_output=True, text=True)


def test_cli_selftest():
    r = _cli("selftest")
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_validate_example():
    r = _cli("validate", "examples/pick_cube")
    assert r.returncode == 0 and "pick_cube" in r.stdout


def test_cli_portability_fails_without_remap():
    r = _cli("portability", "examples/pick_cube", "--target", "examples/robot_target.yaml")
    assert r.returncode == 1 and "FAILED" in r.stdout
