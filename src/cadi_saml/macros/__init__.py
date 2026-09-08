"""
cadi_saml.macros
================
High-level parametric assembly macros for cadi_saml CAD Kernel.
Automates multi-component engineering structures, standard bolted joints,
rotating shaft stacks, gear pairs, weldments, planetary stages, and cams.
"""

from .fasteners_macro import add_bolted_joint
from .structural_macros import add_mounting_bracket, add_profile_frame, add_motor_mount
from .powertrain_macros import add_bearing_support, add_gear_pair, add_shaft_stack
from .shaft_features import add_shaft_keyway, add_circlip_groove, lookup_din_6885, lookup_din_471
from .weldment_macros import add_gusset, add_end_cap
from .planetary_macros import add_planetary_stage, solve_planetary_teeth
from .cam_macros import add_disk_cam, evaluate_motion_law
from .hole_wizard import add_threaded_hole, lookup_metric_thread, METRIC_THREADS
from .piping_macros import add_pipe_route, PIPE_SCHEDULES, analyze_pipe_route_flow
from .iris_nozzle import build_variable_exhaust_nozzle, IrisNozzleMechanism, IrisNozzleMetrics

__all__ = [
    "add_bolted_joint",
    "add_mounting_bracket",
    "add_profile_frame",
    "add_motor_mount",
    "add_bearing_support",
    "add_gear_pair",
    "add_shaft_stack",
    "add_shaft_keyway",
    "add_circlip_groove",
    "lookup_din_6885",
    "lookup_din_471",
    "add_gusset",
    "add_end_cap",
    "add_planetary_stage",
    "solve_planetary_teeth",
    "add_disk_cam",
    "evaluate_motion_law",
    "add_threaded_hole",
    "lookup_metric_thread",
    "METRIC_THREADS",
    "add_pipe_route",
    "PIPE_SCHEDULES",
    "analyze_pipe_route_flow",
    "build_variable_exhaust_nozzle",
    "IrisNozzleMechanism",
    "IrisNozzleMetrics",
]
