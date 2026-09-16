#!/usr/bin/env python3
"""End-to-end walk through the six properties on the bundled example skills.

    python3 examples/run_example.py

Validates two recorded skills and one composed skill; verifies integrity;
checks portability to a different arm (catching one missing remap, then
satisfying it); adapts; verifies the composition handoff; and verifies safety
against a robot's limits and a world state.
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import yaml                                                        # noqa: E402

from skill_package import adapt as adapt_mod                       # noqa: E402
from skill_package import manifest                                 # noqa: E402
from skill_package.registry import Registry                        # noqa: E402
from skill_package.schema import Embodiment                        # noqa: E402
from skill_package.verify import (verify_composition,              # noqa: E402
                                  verify_integrity, verify_portability,
                                  verify_safety)


def line(s=""):
    print(s)


def main():
    pick = manifest.load(os.path.join(HERE, "pick_cube"))
    place = manifest.load(os.path.join(HERE, "place"))
    manifest.save(pick, os.path.join(HERE, "pick_cube"))    # fill integrity + id
    manifest.save(place, os.path.join(HERE, "place"))
    pick = manifest.load(os.path.join(HERE, "pick_cube"))
    place = manifest.load(os.path.join(HERE, "place"))
    comp = manifest.load(os.path.join(HERE, "pick_and_place"))

    line("1. IDENTITY + STANDARDISATION")
    line("   pick_cube      %s@%s  id=%s" % (pick.name, pick.version, pick.id))
    line("   place_object   %s@%s  id=%s" % (place.name, place.version, place.id))
    line("   pick_and_place %s@%s  (composed)" % (comp.name, comp.version))

    line("\n2. PROVENANCE + INTEGRITY")
    r = verify_integrity(pick)
    line("   pick_cube integrity: %s (%d payload file(s))"
         % (r.report().splitlines()[0], len(pick.payload)))
    line("   captured on %r from episode(s) %s"
         % (pick.provenance.captured_on,
            [e["id"] for e in pick.provenance.episodes]))

    line("\n3. SAFETY VERIFICATION")
    robot = yaml.safe_load(open(os.path.join(HERE, "robot_limits.yaml")))
    world = yaml.safe_load(open(os.path.join(HERE, "world.yaml")))
    r = verify_safety(pick, robot, world)
    line("   against robot limits + world state: " + r.report())
    tight = {"max_force_n": 10.0, "max_speed_mps": 0.5, "min_clearance_m": 0.15}
    r = verify_safety(pick, tight, world)
    line("   against a weaker robot (max_force 10 N): " + r.report())

    line("\n4. PORTABILITY (the difference from static playback)")
    target = Embodiment.from_dict(
        yaml.safe_load(open(os.path.join(HERE, "robot_target.yaml"))))
    r = verify_portability(pick, target)
    line("   pick_cube as recorded -> %s:" % target.name)
    line("   " + r.report())

    line("\n   declaring the required remaps in the manifest...")
    portable = copy.deepcopy(pick)
    portable.adaptation.joint_map = dict(zip(pick.embodiment.joint_names,
                                             target.joint_names))
    portable.adaptation.unit_conversion = {"angle": "rad->deg"}
    portable.adaptation.frame_transform = {"ee_frame": "tool0"}
    portable.adaptation.requires = ["joint_map", "unit_conversion", "frame_transform"]
    r = verify_portability(portable, target)
    line("   " + r.report())

    line("\n5. ADAPTATION")
    adapted = adapt_mod.adapt(portable, target)
    line("   adapted %s -> %s@%s on %s"
         % (portable.name, adapted.name, adapted.version, adapted.embodiment.name))
    line("   new joints: %s" % adapted.embodiment.joint_names)
    line("   unit factor applied: %s"
         % getattr(adapted, "_adaptation_applied")["unit_conversion"])

    line("\n6. COMPOSITION (checked handoff, not concatenation)")
    reg = Registry(os.path.join(HERE, "..", "does-not-exist"))
    reg.add(pick)
    reg.add(place)
    r = verify_composition(comp, reg)
    line("   pick_and_place = pick_cube -> place_object")
    line("   " + r.report())

    broken = copy.deepcopy(place)
    broken.safety.preconditions = ["object_on_conveyor"]  # not established by pick
    reg2 = Registry(os.path.join(HERE, "..", "does-not-exist"))
    reg2.add(pick)
    reg2.add(broken)
    r = verify_composition(comp, reg2)
    line("   if place required an unmet precondition instead: " + r.report())


if __name__ == "__main__":
    main()
