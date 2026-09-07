"""
cadi_saml.simulation.units

Strict dimensional and physical unit conversion engine.
Prevents unit mismatches (e.g. pressure vs force, mm vs m, l/s vs m3/s).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Union


# Conversion factors to standard SI base/derived units:
# length -> meter (m)
# pressure -> Pascal (Pa)
# force -> Newton (N)
# flow_rate -> m^3/s
# velocity -> m/s
# temperature -> Kelvin (K)
# density -> kg/m^3
# dynamic_viscosity -> Pa*s (kg/(m*s))
# kinematic_viscosity -> m^2/s
# power -> Watt (W)

UNIT_CONVERSIONS: Dict[str, Dict[str, float]] = {
    "length": {
        "m": 1.0,
        "mm": 1e-3,
        "cm": 1e-2,
        "inch": 0.0254,
        "in": 0.0254,
        "ft": 0.3048,
    },
    "pressure": {
        "pa": 1.0,
        "kpa": 1e3,
        "mpa": 1e6,
        "bar": 1e5,
        "mbar": 100.0,
        "psi": 6894.757,
        "atm": 101325.0,
    },
    "force": {
        "n": 1.0,
        "kn": 1e3,
        "mn": 1e6,
        "lbf": 4.44822,
        "kgf": 9.80665,
    },
    "flow_rate": {
        "m3/s": 1.0,
        "m3/h": 1.0 / 3600.0,
        "l/s": 1e-3,
        "l/min": 1e-3 / 60.0,
        "l/h": 1e-3 / 3600.0,
        "gpm": 6.30902e-5,  # US Gallons per minute
    },
    "velocity": {
        "m/s": 1.0,
        "km/h": 1.0 / 3.6,
        "ft/s": 0.3048,
    },
    "density": {
        "kg/m3": 1.0,
        "g/cm3": 1000.0,
        "kg/l": 1000.0,
    },
    "dynamic_viscosity": {
        "pa.s": 1.0,
        "pa*s": 1.0,
        "mpa.s": 1e-3,
        "cp": 1e-3,  # centipoise
        "p": 0.1,    # poise
    },
    "kinematic_viscosity": {
        "m2/s": 1.0,
        "cst": 1e-6, # centistokes
        "st": 1e-4,  # stokes
        "mm2/s": 1e-6,
    },
    "power": {
        "w": 1.0,
        "kw": 1e3,
        "hp": 745.7,  # metric/mechanical horsepower approx 745.7W
    },
}


@dataclass(frozen=True)
class Quantity:
    """Represents a physical quantity with strict dimension and unit validation."""
    value: float
    unit: str
    dimension: str

    def __post_init__(self):
        u = self.unit.lower()
        dim = self.dimension.lower()
        if dim == "temperature":
            if u not in ("k", "c", "f"):
                raise ValueError(f"Unknown temperature unit: '{self.unit}'. Valid: 'K', 'C', 'F'")
            return

        if dim not in UNIT_CONVERSIONS:
            raise ValueError(f"Unknown dimension: '{self.dimension}'. Valid: {list(UNIT_CONVERSIONS.keys()) + ['temperature']}")
        
        if u not in UNIT_CONVERSIONS[dim]:
            raise ValueError(f"Unit '{self.unit}' does not belong to dimension '{self.dimension}'. Valid: {list(UNIT_CONVERSIONS[dim].keys())}")

    def to_si(self) -> float:
        """Convert quantity value to SI base unit."""
        dim = self.dimension.lower()
        u = self.unit.lower()

        if dim == "temperature":
            if u == "c":
                return self.value + 273.15
            elif u == "f":
                return (self.value - 32.0) * (5.0 / 9.0) + 273.15
            return self.value

        factor = UNIT_CONVERSIONS[dim][u]
        return self.value * factor

    def convert_to(self, target_unit: str) -> Quantity:
        """Convert quantity to another unit within the same dimension."""
        dim = self.dimension.lower()
        t_unit = target_unit.lower()

        if dim == "temperature":
            si_val = self.to_si()
            if t_unit == "k":
                out_val = si_val
            elif t_unit == "c":
                out_val = si_val - 273.15
            elif t_unit == "f":
                out_val = (si_val - 273.15) * (9.0 / 5.0) + 32.0
            else:
                raise ValueError(f"Invalid target temperature unit: {target_unit}")
            return Quantity(value=out_val, unit=target_unit, dimension=self.dimension)

        if t_unit not in UNIT_CONVERSIONS[dim]:
            raise ValueError(f"Target unit '{target_unit}' invalid for dimension '{self.dimension}'")

        si_val = self.to_si()
        target_factor = UNIT_CONVERSIONS[dim][t_unit]
        out_val = si_val / target_factor
        return Quantity(value=out_val, unit=target_unit, dimension=self.dimension)

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "unit": self.unit, "dimension": self.dimension}


def ensure_quantity(val: Union[Quantity, float], default_unit: str, dimension: str) -> Quantity:
    """Helper to convert raw float or existing Quantity into a guaranteed Quantity."""
    if isinstance(val, Quantity):
        if val.dimension.lower() != dimension.lower():
            raise TypeError(f"Expected dimension '{dimension}', got '{val.dimension}'")
        return val
    return Quantity(value=float(val), unit=default_unit, dimension=dimension)
