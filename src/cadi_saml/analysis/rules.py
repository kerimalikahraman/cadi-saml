"""
cadi_saml.analysis.rules
========================
CATIA KnowledgeWare-grade Engineering Design Rules Engine.
Validates manufacturability, assembly safety, and standardized geometric constraints.
Provides structured self-correction feedback and repair suggestions for LLM CAD agents.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ..core.assembly import Assembly


@dataclass
class RuleViolation:
    rule_id: str
    severity: str  # "ERROR", "WARNING", "INFO"
    part_name: str
    message: str
    measured_value: float
    required_value: float
    repair_suggestion: str


class DesignRule:
    """Base engineering design rule."""
    def __init__(self, rule_id: str, description: str, severity: str = "ERROR"):
        self.rule_id = rule_id
        self.description = description
        self.severity = severity

    def check(self, assembly: "Assembly") -> List[RuleViolation]:
        raise NotImplementedError


class HoleEdgeDistanceRule(DesignRule):
    """
    Validates that holes are positioned sufficiently far from the part boundary.
    Standard rule: Center-to-edge distance e >= min_ratio * hole_diameter (default 1.5).
    """
    def __init__(self, min_ratio: float = 1.5):
        super().__init__(
            rule_id="RULE_HOLE_EDGE_DISTANCE",
            description="Hole center must be at least 1.5x diameter away from the nearest outer edge.",
            severity="ERROR",
        )
        self.min_ratio = min_ratio

    def check(self, assembly: "Assembly") -> List[RuleViolation]:
        violations = []
        for name, part in assembly._parts.items():
            params = part.node.parameters
            # Inspect parts with hole features or flanged holes
            if "holes" in params:
                length = float(params.get("length", 100.0))
                width = float(params.get("width", 100.0))
                for h in params["holes"]:
                    hdia = float(h.get("diameter", 6.0))
                    hx = float(h.get("x", 0.0))
                    hy = float(h.get("y", 0.0))

                    # Distance to rectangular boundary (assuming centered origin)
                    dist_x = min(abs(hx - (-length / 2.0)), abs(length / 2.0 - hx))
                    dist_y = min(abs(hy - (-width / 2.0)), abs(width / 2.0 - hy))
                    min_dist = min(dist_x, dist_y)

                    req_dist = self.min_ratio * hdia
                    if min_dist < req_dist - 1e-4:
                        violations.append(
                            RuleViolation(
                                rule_id=self.rule_id,
                                severity=self.severity,
                                part_name=name,
                                message=f"Hole (dia {hdia}mm) is only {min_dist:.2f}mm from edge.",
                                measured_value=round(min_dist, 2),
                                required_value=round(req_dist, 2),
                                repair_suggestion=(
                                    f"Increase margin of hole in '{name}' to at least {req_dist:.2f}mm "
                                    f"(e >= {self.min_ratio} * d) to prevent edge tear-out during punching/milling."
                                ),
                            )
                        )
        return violations


class SheetMetalBendRadiusRule(DesignRule):
    """
    Validates that sheet metal bend radius is at least equal to sheet thickness.
    Rule: bend_radius >= sheet_thickness.
    """
    def __init__(self, min_ratio: float = 1.0):
        super().__init__(
            rule_id="RULE_SHEET_METAL_BEND_RADIUS",
            description="Sheet metal inner bend radius must be >= sheet thickness to prevent cracking.",
            severity="ERROR",
        )
        self.min_ratio = min_ratio

    def check(self, assembly: "Assembly") -> List[RuleViolation]:
        violations = []
        for name, part in assembly._parts.items():
            params = part.node.parameters
            if part.node.part_type in ("sheet_metal", "sheet_metal_bracket"):
                thickness = float(params.get("thickness", 2.0))
                bends = params.get("bends", [])
                for b in bends:
                    r = float(b.get("radius", thickness))
                    req_r = self.min_ratio * thickness
                    if r < req_r - 1e-4:
                        violations.append(
                            RuleViolation(
                                rule_id=self.rule_id,
                                severity=self.severity,
                                part_name=name,
                                message=f"Sheet bend radius ({r}mm) is smaller than sheet thickness ({thickness}mm).",
                                measured_value=round(r, 2),
                                required_value=round(req_r, 2),
                                repair_suggestion=(
                                    f"Increase bend radius in '{name}' from {r}mm to at least {req_r}mm "
                                    f"to prevent metallurgical cracking during brake forming."
                                ),
                            )
                        )
        return violations


class BoltSpacingRule(DesignRule):
    """
    Validates pitch between adjacent bolts to ensure wrench/socket clearance.
    Rule: pitch >= 3.0 * bolt_diameter.
    """
    def __init__(self, min_pitch_ratio: float = 2.5):
        super().__init__(
            rule_id="RULE_BOLT_SPACING",
            description="Center-to-center bolt pitch must be >= 2.5x diameter for tool socket access.",
            severity="WARNING",
        )
        self.min_pitch_ratio = min_pitch_ratio

    def check(self, assembly: "Assembly") -> List[RuleViolation]:
        violations = []
        for name, part in assembly._parts.items():
            params = part.node.parameters
            pcd = params.get("bolt_pcd")
            count = params.get("bolt_count")
            dia = params.get("bolt_diameter", 8.0)
            if pcd and count and int(count) > 1:
                # Chord distance between adjacent holes on pitch circle
                pitch = float(pcd) * math.sin(math.pi / int(count))
                req_pitch = self.min_pitch_ratio * float(dia)
                if pitch < req_pitch:
                    violations.append(
                        RuleViolation(
                            rule_id=self.rule_id,
                            severity=self.severity,
                            part_name=name,
                            message=f"Adjacent bolt spacing is {pitch:.2f}mm on PCD {pcd}mm.",
                            measured_value=round(pitch, 2),
                            required_value=round(req_pitch, 2),
                            repair_suggestion=(
                                f"Increase bolt circle PCD in '{name}' or reduce bolt count "
                                f"so pitch is at least {req_pitch:.2f}mm for socket wrench access."
                            ),
                        )
                    )
        return violations


class DesignRuleEngine:
    """CATIA KnowledgeWare-inspired design rule auditor."""
    def __init__(self):
        self.rules: List[DesignRule] = [
            HoleEdgeDistanceRule(min_ratio=1.5),
            SheetMetalBendRadiusRule(min_ratio=1.0),
            BoltSpacingRule(min_pitch_ratio=2.5),
        ]

    def add_rule(self, rule: DesignRule) -> DesignRuleEngine:
        self.rules.append(rule)
        return self

    def evaluate(self, assembly: "Assembly") -> Dict[str, Any]:
        """Runs all registered rules and returns an engineering compliance audit."""
        all_violations: List[RuleViolation] = []
        for r in self.rules:
            all_violations.extend(r.check(assembly))

        errors = [v for v in all_violations if v.severity == "ERROR"]
        warnings = [v for v in all_violations if v.severity == "WARNING"]

        passed = len(errors) == 0
        total_checks = len(self.rules)
        score = max(0.0, 100.0 - (len(errors) * 35.0 + len(warnings) * 10.0))

        # Build LLM repair prompt if violations exist
        llm_repair = ""
        if all_violations:
            llm_repair = "### 🚨 Engineering Design Rule Violations Detected:\n"
            for v in all_violations:
                llm_repair += f"- **[{v.severity}] {v.part_name}**: {v.message}\n  *Action:* {v.repair_suggestion}\n"

        return {
            "passed": passed,
            "score_percent": round(score, 1),
            "total_rules_evaluated": total_checks,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "severity": v.severity,
                    "part_name": v.part_name,
                    "message": v.message,
                    "measured": v.measured_value,
                    "required": v.required_value,
                    "suggestion": v.repair_suggestion,
                }
                for v in all_violations
            ],
            "llm_repair_prompt": llm_repair,
        }


def check_design_rules(assembly: "Assembly") -> Dict[str, Any]:
    """Convenience function to evaluate KnowledgeWare design rules on an assembly."""
    engine = DesignRuleEngine()
    return engine.evaluate(assembly)
