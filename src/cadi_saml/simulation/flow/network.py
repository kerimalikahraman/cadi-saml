"""
cadi_saml.simulation.flow.network

Pipe network solver using the Hardy Cross iterative method.
Handles arbitrary branched/looped piping systems with multiple loops,
pumps, reservoirs, and demand nodes.

Algorithm
---------
Hardy Cross (1936) method — iterative loop correction:
  1. Assume initial flow distribution satisfying continuity at nodes.
  2. For each independent loop, compute head loss correction:
       ΔQ = -ΣhL / (n · Σ|hL|/Q)
     where hL = R·Q^n (Darcy-Weisbach: n=2, R = f·L/(D·2g·A²))
  3. Apply ΔQ to all pipes in the loop; repeat until convergence.

Reference
---------
  Hardy Cross (1936). Analysis of flow in networks of conduits or conductors.
  Univ. of Illinois Bull. 286.
  Streeter, V.L. & Wylie, E.B. (1983). Fluid Mechanics. McGraw-Hill.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from .fluid_properties import FluidState, get_water_properties


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PipeSegment:
    """A single pipe segment in the network."""
    pipe_id: str
    node_from: str
    node_to: str
    diameter_mm: float
    length_mm: float
    roughness_m: float = 4.5e-5          # Default: commercial steel
    minor_loss_k: float = 0.0            # Sum of fitting K-factors
    # Computed during solve:
    flow_rate_m3_s: float = 0.0          # Positive = from→to direction
    velocity_m_s: float = 0.0
    head_loss_m: float = 0.0             # Positive = from > to
    reynolds: float = 0.0
    friction_factor: float = 0.0


@dataclass
class PumpCurve:
    """Pump characteristic curve as a list of (flow_m3_s, head_m) pairs."""
    pump_id: str
    node_from: str          # Suction node
    node_to: str            # Discharge node
    curve_points: List[Tuple[float, float]]  # [(Q₁, H₁), (Q₂, H₂), ...]

    def head_at_flow(self, q: float) -> float:
        """Linear interpolation of pump head at flow rate q [m³/s]."""
        if not self.curve_points:
            return 0.0
        qs = [p[0] for p in self.curve_points]
        hs = [p[1] for p in self.curve_points]
        if q <= qs[0]:
            return hs[0]
        if q >= qs[-1]:
            return hs[-1]
        for i in range(len(qs) - 1):
            if qs[i] <= q <= qs[i + 1]:
                t = (q - qs[i]) / (qs[i + 1] - qs[i])
                return hs[i] + t * (hs[i + 1] - hs[i])
        return hs[-1]


@dataclass
class NodeResult:
    node_id: str
    pressure_head_m: float       # H = z + p/(ρg) [m]
    elevation_m: float
    demand_m3_s: float           # Negative = supply/source
    net_flow_in_m3_s: float      # Sum of inflows (should ≈ 0 after convergence)


@dataclass
class NetworkSolution:
    """Full pipe network solution."""
    converged: bool
    iterations: int
    residual_max: float          # Max loop head imbalance [m] at convergence
    pipes: Dict[str, PipeSegment]
    nodes: Dict[str, NodeResult]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "converged": self.converged,
            "iterations": self.iterations,
            "residual_m": round(self.residual_max, 6),
            "pipes": {
                pid: {
                    "flow_l_s": round(p.flow_rate_m3_s * 1e3, 4),
                    "velocity_m_s": round(p.velocity_m_s, 3),
                    "head_loss_m": round(p.head_loss_m, 4),
                    "reynolds": round(p.reynolds, 0),
                }
                for pid, p in self.pipes.items()
            },
            "nodes": {
                nid: {
                    "pressure_head_m": round(n.pressure_head_m, 3),
                    "net_flow_in_l_s": round(n.net_flow_in_m3_s * 1e3, 4),
                }
                for nid, n in self.nodes.items()
            },
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Pipe resistance formula
# ---------------------------------------------------------------------------

def _pipe_resistance(
    pipe: PipeSegment,
    fluid: FluidState,
    g: float = 9.80665,
) -> float:
    """
    Compute pipe resistance coefficient R such that hL = R · Q · |Q|.
    This form keeps sign information for loop corrections.

    R = f·L / (D·2g·A²) + K / (2g·A²)
    """
    d_m = pipe.diameter_mm * 1e-3
    l_m = pipe.length_mm * 1e-3
    area = math.pi / 4.0 * d_m ** 2

    # Estimate friction factor at current flow
    if abs(pipe.flow_rate_m3_s) < 1e-12:
        f = 0.02  # initial guess
    else:
        v = abs(pipe.flow_rate_m3_s) / area
        re = fluid.density * v * d_m / max(1e-10, fluid.dynamic_viscosity)
        pipe.reynolds = re
        if re < 2300:
            f = 64.0 / max(1.0, re)
        else:
            rel_r = pipe.roughness_m / d_m
            inv_f = -1.8 * math.log10((rel_r / 3.7) ** 1.11 + 6.9 / re)
            f = 1.0 / max(1e-6, inv_f ** 2)
            f = max(0.005, min(0.15, f))
        pipe.friction_factor = f

    R_friction = f * l_m / (d_m * 2.0 * g * area ** 2)
    R_minor = pipe.minor_loss_k / (2.0 * g * area ** 2)
    return R_friction + R_minor


# ---------------------------------------------------------------------------
# Hardy Cross solver
# ---------------------------------------------------------------------------

class PipeNetwork:
    """
    Pipe network solver using the Hardy Cross iterative correction method.

    Usage
    -----
    >>> net = PipeNetwork(fluid=get_water_properties(20))
    >>> net.add_pipe("P1", "A", "B", diameter_mm=100, length_mm=500_000)
    >>> net.add_pipe("P2", "B", "C", diameter_mm=80,  length_mm=300_000)
    >>> net.add_pipe("P3", "C", "A", diameter_mm=80,  length_mm=400_000)
    >>> net.set_node_demand("C", demand_m3_s=0.005)
    >>> net.set_node_head("A", head_m=50.0)   # reservoir / fixed-head node
    >>> result = net.solve()
    """

    def __init__(self, fluid: Optional[FluidState] = None):
        self.fluid = fluid or get_water_properties(20.0)
        self._pipes: Dict[str, PipeSegment] = {}
        self._pumps: Dict[str, PumpCurve] = {}
        self._node_demands: Dict[str, float] = {}      # m³/s (positive = demand/outflow)
        self._node_heads: Dict[str, float] = {}         # fixed total head [m]
        self._node_elevations: Dict[str, float] = {}    # elevation [m]

    # ---- Construction methods ------------------------------------------

    def add_pipe(
        self,
        pipe_id: str,
        node_from: str,
        node_to: str,
        diameter_mm: float,
        length_mm: float,
        roughness_m: float = 4.5e-5,
        minor_loss_k: float = 0.0,
        initial_flow_m3_s: float = 0.001,
    ) -> "PipeNetwork":
        """Add a pipe segment to the network."""
        self._pipes[pipe_id] = PipeSegment(
            pipe_id=pipe_id,
            node_from=node_from,
            node_to=node_to,
            diameter_mm=diameter_mm,
            length_mm=length_mm,
            roughness_m=roughness_m,
            minor_loss_k=minor_loss_k,
            flow_rate_m3_s=initial_flow_m3_s,
        )
        return self

    def add_pump(
        self,
        pump_id: str,
        node_from: str,
        node_to: str,
        curve_points: List[Tuple[float, float]],
    ) -> "PipeNetwork":
        """Add a pump to the network. curve_points = [(Q_m3/s, H_m), ...]"""
        self._pumps[pump_id] = PumpCurve(
            pump_id=pump_id,
            node_from=node_from,
            node_to=node_to,
            curve_points=sorted(curve_points, key=lambda p: p[0]),
        )
        return self

    def set_node_demand(self, node_id: str, demand_m3_s: float) -> "PipeNetwork":
        """Set demand (positive = consumption, negative = supply) at a node."""
        self._node_demands[node_id] = demand_m3_s
        return self

    def set_node_head(self, node_id: str, head_m: float) -> "PipeNetwork":
        """Fix total hydraulic head at a node (reservoir / pressure source)."""
        self._node_heads[node_id] = head_m
        return self

    def set_node_elevation(self, node_id: str, elevation_m: float) -> "PipeNetwork":
        """Set node elevation [m]."""
        self._node_elevations[node_id] = elevation_m
        return self

    # ---- Topology helpers -----------------------------------------------

    def _get_all_nodes(self) -> List[str]:
        nodes = set()
        for p in self._pipes.values():
            nodes.add(p.node_from)
            nodes.add(p.node_to)
        for pump in self._pumps.values():
            nodes.add(pump.node_from)
            nodes.add(pump.node_to)
        return sorted(nodes)

    def _find_loops(self) -> List[List[str]]:
        """
        Detect independent loops using DFS + cycle detection.
        Returns list of loops, each loop as ordered list of pipe_ids.
        For simple networks, returns loop cycles.
        """
        # Build adjacency list
        nodes = self._get_all_nodes()
        adj: Dict[str, List[Tuple[str, str]]] = {n: [] for n in nodes}
        for pid, p in self._pipes.items():
            adj[p.node_from].append((p.node_to, pid))
            adj[p.node_to].append((p.node_from, pid))

        visited_edges: set = set()
        loops: List[List[str]] = []

        def dfs(node: str, parent_edge: Optional[str], path_nodes: List[str], path_edges: List[str]):
            for neighbor, eid in adj[node]:
                if eid == parent_edge:
                    continue
                if eid in visited_edges:
                    continue
                if neighbor in path_nodes:
                    # Found a cycle
                    idx = path_nodes.index(neighbor)
                    loop_edges = path_edges[idx:]
                    loops.append(loop_edges)
                    for e in loop_edges:
                        visited_edges.add(e)
                    return
                visited_edges.add(eid)
                path_nodes.append(neighbor)
                path_edges.append(eid)
                dfs(neighbor, eid, path_nodes, path_edges)
                path_nodes.pop()
                path_edges.pop()

        for start in nodes:
            dfs(start, None, [start], [])

        return loops

    # ---- Head loss -------------------------------------------------------

    def _head_loss(self, pipe: PipeSegment) -> float:
        """Head loss hL = R·Q·|Q| for a pipe. Positive = from > to."""
        R = _pipe_resistance(pipe, self.fluid)
        q = pipe.flow_rate_m3_s
        hl = R * q * abs(q)
        pipe.head_loss_m = hl
        return hl

    # ---- Hardy Cross iteration ------------------------------------------

    def solve(
        self,
        max_iterations: int = 200,
        tolerance_m3_s: float = 1e-7,
        g: float = 9.80665,
    ) -> NetworkSolution:
        """
        Solve the network using Hardy Cross method.

        Parameters
        ----------
        max_iterations : Maximum iteration count
        tolerance_m3_s : Convergence criterion on flow correction [m³/s]
        g              : Gravitational acceleration [m/s²]
        """
        warnings_list: List[str] = []

        if not self._pipes:
            return NetworkSolution(
                converged=False,
                iterations=0,
                residual_max=float("inf"),
                pipes={},
                nodes={},
                warnings=["No pipes defined in network."],
            )

        loops = self._find_loops()

        if not loops:
            # Tree network — no iterative correction needed, just compute
            warnings_list.append(
                "No loops detected — network is a tree. "
                "Hardy Cross not required; flows determined by boundary conditions."
            )

        converged = False
        residual_max = float("inf")
        iteration = 0

        for iteration in range(max_iterations):
            max_dq = 0.0

            for loop_edges in loops:
                # Sum of head losses around the loop
                sum_hl = 0.0
                sum_hl_over_q = 0.0

                for eid in loop_edges:
                    pipe = self._pipes[eid]
                    hl = self._head_loss(pipe)
                    q = pipe.flow_rate_m3_s
                    if abs(q) < 1e-12:
                        continue
                    sum_hl += hl
                    sum_hl_over_q += abs(hl / q)

                if sum_hl_over_q < 1e-12:
                    continue

                # Hardy Cross correction
                dq = -sum_hl / (2.0 * sum_hl_over_q)
                max_dq = max(max_dq, abs(dq))

                for eid in loop_edges:
                    self._pipes[eid].flow_rate_m3_s += dq

            residual_max = max_dq
            if max_dq < tolerance_m3_s:
                converged = True
                break

        # --- Compute velocities & update head losses ----------------------
        for pipe in self._pipes.values():
            d_m = pipe.diameter_mm * 1e-3
            area = math.pi / 4.0 * d_m ** 2
            pipe.velocity_m_s = pipe.flow_rate_m3_s / max(1e-12, area)
            self._head_loss(pipe)

        # --- Node pressure heads -----------------------------------------
        node_results: Dict[str, NodeResult] = {}
        all_nodes = self._get_all_nodes()

        # Assign known heads first
        node_head: Dict[str, Optional[float]] = {n: None for n in all_nodes}
        for n, h in self._node_heads.items():
            node_head[n] = h

        # Propagate heads through pipes (BFS from fixed-head nodes)
        from collections import deque
        queue: deque = deque()
        for n, h in self._node_heads.items():
            if h is not None:
                queue.append(n)

        adj_pipes: Dict[str, List[str]] = {n: [] for n in all_nodes}
        for pid, p in self._pipes.items():
            adj_pipes[p.node_from].append(pid)
            adj_pipes[p.node_to].append(pid)

        while queue:
            n = queue.popleft()
            for pid in adj_pipes.get(n, []):
                p = self._pipes[pid]
                if p.node_from == n and node_head[p.node_to] is None:
                    node_head[p.node_to] = node_head[n] - p.head_loss_m
                    queue.append(p.node_to)
                elif p.node_to == n and node_head[p.node_from] is None:
                    node_head[p.node_from] = node_head[n] + p.head_loss_m
                    queue.append(p.node_from)

        for n in all_nodes:
            h = node_head.get(n) or 0.0
            demand = self._node_demands.get(n, 0.0)
            elev = self._node_elevations.get(n, 0.0)

            # Net flow check (continuity residual)
            net_in = -demand
            for pid in adj_pipes.get(n, []):
                p = self._pipes[pid]
                if p.node_to == n:
                    net_in += p.flow_rate_m3_s
                elif p.node_from == n:
                    net_in -= p.flow_rate_m3_s

            node_results[n] = NodeResult(
                node_id=n,
                pressure_head_m=round(h, 4),
                elevation_m=elev,
                demand_m3_s=demand,
                net_flow_in_m3_s=round(net_in, 8),
            )

        if not converged:
            warnings_list.append(
                f"Hardy Cross did not converge in {max_iterations} iterations. "
                f"Max flow residual: {residual_max:.2e} m³/s. "
                "Consider checking boundary conditions or increasing max_iterations."
            )

        return NetworkSolution(
            converged=converged,
            iterations=iteration + 1,
            residual_max=round(residual_max, 8),
            pipes=self._pipes,
            nodes=node_results,
            warnings=warnings_list,
        )
