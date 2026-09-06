"""Bounded, deterministic design exploration and one-dimensional tolerance chains."""
from __future__ import annotations
from dataclasses import dataclass
from itertools import product
import math
from typing import Callable


@dataclass(frozen=True)
class DimensionTolerance:
    name: str
    nominal: float
    lower: float
    upper: float
    coefficient: float = 1.0

    def __post_init__(self):
        if not self.name or not all(math.isfinite(x) for x in (self.nominal, self.lower, self.upper, self.coefficient)):
            raise ValueError('Dimension name and finite values required')
        if self.lower > 0 or self.upper < 0 or self.lower > self.upper or self.coefficient == 0:
            raise ValueError('Deviations must straddle zero; coefficient must be nonzero')


class ToleranceStack:
    """Signed linear dimension chain. All lengths are mm; deviations are signed."""
    def __init__(self):
        self.dimensions = {}

    def add_dimension_tolerance(self, name, nominal, lower, upper, coefficient=1.0):
        if name in self.dimensions:
            raise ValueError(f'Duplicate dimension: {name}')
        self.dimensions[name] = DimensionTolerance(name, nominal, lower, upper, coefficient)
        return self

    def analyze_stackup(self):
        if not self.dimensions:
            raise ValueError('Empty tolerance stack')
        nominal = minimum = maximum = 0.0
        contributions = []
        for d in self.dimensions.values():
            nominal += d.nominal * d.coefficient
            ends = [(d.nominal + e) * d.coefficient for e in (d.lower, d.upper)]
            minimum += min(ends)
            maximum += max(ends)
            contributions.append({'name': d.name, 'range_mm': abs(d.coefficient) * (d.upper - d.lower)})
        return {'nominal_mm': nominal, 'minimum_mm': minimum, 'maximum_mm': maximum,
                'method': 'worst_case_linear',
                'contributors': sorted(contributions, key=lambda d: d['range_mm'], reverse=True)}

    def recommend_shim(self, target_min, target_max, available_thicknesses, shim_tolerance=0.0):
        """Choose a shim that subtracts from the gap and meets the whole worst-case interval."""
        if not all(math.isfinite(x) for x in (target_min, target_max, shim_tolerance)) or target_min > target_max or shim_tolerance < 0:
            raise ValueError('Invalid target interval or shim tolerance')
        stack = self.analyze_stackup()
        choices = sorted(set(float(x) for x in available_thicknesses))
        if any(not math.isfinite(x) or x < shim_tolerance for x in choices):
            raise ValueError('Invalid shim thickness')
        candidates = []
        for thickness in choices:
            lo = stack['minimum_mm'] - thickness - shim_tolerance
            hi = stack['maximum_mm'] - thickness + shim_tolerance
            if lo >= target_min - 1e-12 and hi <= target_max + 1e-12:
                candidates.append({'thickness_mm': thickness, 'minimum_gap_mm': lo, 'maximum_gap_mm': hi})
        return {'feasible': bool(candidates), 'recommendation': min(candidates, key=lambda c: abs((c['minimum_gap_mm'] + c['maximum_gap_mm']) - (target_min + target_max))) if candidates else None,
                'candidates': candidates}


class DesignStudy:
    """Finite grid search. Each evaluator must build a fresh model; failures remain in history.

    Evaluator returns a dict of finite scalar metrics. It may raise for invalid geometry,
    invalid FEA or unsupported manufacturing conditions. No automatic mutation of a model.
    """
    def __init__(self, evaluator: Callable, objective: str, minimize=True, max_trials=100):
        if not callable(evaluator) or not objective or not isinstance(max_trials, int) or max_trials < 1:
            raise ValueError('Evaluator, objective and positive integer budget required')
        self.evaluator, self.objective = evaluator, objective
        self.minimize, self.max_trials = minimize, max_trials
        self.constraints = {}

    def add_design_constraint(self, metric, minimum=None, maximum=None):
        if minimum is None and maximum is None:
            raise ValueError('At least one constraint bound required')
        if any(x is not None and not math.isfinite(x) for x in (minimum, maximum)):
            raise ValueError('Bounds must be finite')
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError('Reversed constraint bounds')
        self.constraints[metric] = (minimum, maximum)
        return self

    def parameter_sweep(self, parameters):
        if not parameters:
            raise ValueError('Parameter grid is empty')
        keys, values = list(parameters), [list(v) for v in parameters.values()]
        if any(not v for v in values):
            raise ValueError('Parameter choices cannot be empty')
        count = math.prod(map(len, values))
        if count > self.max_trials:
            raise ValueError(f'Grid has {count} trials; budget is {self.max_trials}')
        trials = []
        for combination in product(*values):
            params = dict(zip(keys, combination))
            trial = {'parameters': params.copy(), 'metrics': {}, 'status': 'FAILED', 'error': None}
            try:
                metrics = dict(self.evaluator(params.copy()))
                required = {self.objective, *self.constraints}
                if not required.issubset(metrics) or any(not math.isfinite(float(v)) for v in metrics.values()):
                    raise ValueError('Missing metric or non-finite result')
                trial['metrics'] = metrics
                failed = [name for name, (lo, hi) in self.constraints.items()
                          if (lo is not None and metrics[name] < lo) or (hi is not None and metrics[name] > hi)]
                trial['failed_constraints'] = failed
                trial['status'] = 'INFEASIBLE' if failed else 'FEASIBLE'
            except Exception as exc:
                trial['error'] = f'{type(exc).__name__}: {exc}'
            trials.append(trial)
        return trials

    def compare_variants(self, trials):
        return sorted([t for t in trials if t['status'] == 'FEASIBLE'],
                      key=lambda t: t['metrics'][self.objective], reverse=not self.minimize)

    def optimize_design(self, parameters):
        trials = self.parameter_sweep(parameters)
        ranked = self.compare_variants(trials)
        return {'best': ranked[0] if ranked else None, 'trials': trials,
                'evaluated': len(trials), 'method': 'finite_grid',
                'scope': 'Best feasible candidate in the supplied grid; no global optimum claim.'}
