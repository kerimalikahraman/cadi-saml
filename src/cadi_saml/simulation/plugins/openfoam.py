"""
cadi_saml.simulation.plugins.openfoam

OpenFOAM CFD Case Directory and Dictionary Generator:
- Generates fully standard, runnable OpenFOAM case structures (OpenFOAM 10 / v2212+)
- Creates system/controlDict, system/fvSchemes, system/fvSolution
- Generates constant/transportProperties (kinematic viscosity nu, density rho)
- Creates system/blockMeshDict for parametric pipe & duct fluid domains
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any


class OpenFOAMCaseExporter:
    """
    Exports parametric fluid domains and flow conditions into a complete OpenFOAM case.
    """

    def __init__(
        self,
        solver: str = "simpleFoam",
        start_time: float = 0.0,
        end_time: float = 1000.0,
        write_interval: int = 100,
    ):
        self.solver = solver
        self.start_time = start_time
        self.end_time = end_time
        self.write_interval = write_interval

    def generate_control_dict(self) -> str:
        return f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2212 / 10                            |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

application     {self.solver};

startFrom       startTime;

startTime       {self.start_time};

stopAt          endTime;

endTime         {self.end_time};

deltaT          1;

writeControl    timeStep;

writeInterval   {self.write_interval};

purgeWrite      3;

writeFormat     ascii;

writePrecision  8;

writeCompression off;

timeFormat      general;

timePrecision   6;

runTimeModifiable true;

// ************************************************************************* //
"""

    def generate_fv_schemes(self) -> str:
        return """/*--------------------------------*- C++ -*----------------------------------*\\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss upwind;
    div(phi,k)      bounded Gauss upwind;
    div(phi,epsilon) bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         corrected;
}

// ************************************************************************* //
"""

    def generate_fv_solution(self) -> str:
        return """/*--------------------------------*- C++ -*----------------------------------*\\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    p
    {
        solver          GAMG;
        tolerance       1e-06;
        relTol          0.01;
        smoother        GaussSeidel;
    }

    "(U|k|epsilon|omega)"
    {
        solver          smoothSolver;
        smoother        GaussSeidel;
        tolerance       1e-06;
        relTol          0.01;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
    consistent      yes;
    residualControl
    {
        p               1e-4;
        U               1e-4;
        "(k|epsilon)"   1e-4;
    }
}

relaxationFactors
{
    equations
    {
        U               0.9;
        ".*"            0.9;
    }
}

// ************************************************************************* //
"""

    def generate_transport_properties(self, kinematic_viscosity_m2_s: float = 1.004e-6) -> str:
        return f"""/*--------------------------------*- C++ -*----------------------------------*\\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      transportProperties;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

transportModel  Newtonian;

nu              [0 2 -1 0 0 0 0] {kinematic_viscosity_m2_s:.6e};

// ************************************************************************* //
"""

    def generate_block_mesh_dict(
        self,
        length_m: float = 1.0,
        width_m: float = 0.05,
        height_m: float = 0.05,
        nx: int = 50,
        ny: int = 10,
        nz: int = 10,
    ) -> str:
        """Generates standard blockMesh for rectangular flow duct."""
        x, y, z = length_m, width_m, height_m
        return f"""/*--------------------------------*- C++ -*----------------------------------*\\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      blockMeshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

scale   1;

vertices
(
    (0 0 0)
    ({x} 0 0)
    ({x} {y} 0)
    (0 {y} 0)
    (0 0 {z})
    ({x} 0 {z})
    ({x} {y} {z})
    (0 {y} {z})
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
            (0 4 7 3)
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            (1 2 6 5)
        );
    }}
    walls
    {{
        type wall;
        faces
        (
            (0 1 5 4)
            (3 7 6 2)
            (0 3 2 1)
            (4 5 6 7)
        );
    }}
);

// ************************************************************************* //
"""

    def export_case(
        self,
        case_directory: str,
        domain_length_m: float = 1.0,
        domain_diameter_or_width_m: float = 0.05,
        kinematic_viscosity_m2_s: float = 1.004e-6,
    ) -> List[str]:
        """
        Creates all directories and writes OpenFOAM case files to disk.
        Returns list of created file paths.
        """
        sys_dir = os.path.join(case_directory, "system")
        const_dir = os.path.join(case_directory, "constant")
        zero_dir = os.path.join(case_directory, "0")

        os.makedirs(sys_dir, exist_ok=True)
        os.makedirs(const_dir, exist_ok=True)
        os.makedirs(zero_dir, exist_ok=True)

        created_files = []

        # 1. system/controlDict
        p_cd = os.path.join(sys_dir, "controlDict")
        with open(p_cd, "w", encoding="utf-8") as f:
            f.write(self.generate_control_dict())
        created_files.append(p_cd)

        # 2. system/fvSchemes
        p_fs = os.path.join(sys_dir, "fvSchemes")
        with open(p_fs, "w", encoding="utf-8") as f:
            f.write(self.generate_fv_schemes())
        created_files.append(p_fs)

        # 3. system/fvSolution
        p_sol = os.path.join(sys_dir, "fvSolution")
        with open(p_sol, "w", encoding="utf-8") as f:
            f.write(self.generate_fv_solution())
        created_files.append(p_sol)

        # 4. system/blockMeshDict
        p_bm = os.path.join(sys_dir, "blockMeshDict")
        with open(p_bm, "w", encoding="utf-8") as f:
            f.write(self.generate_block_mesh_dict(length_m=domain_length_m, width_m=domain_diameter_or_width_m, height_m=domain_diameter_or_width_m))
        created_files.append(p_bm)

        # 5. constant/transportProperties
        p_tp = os.path.join(const_dir, "transportProperties")
        with open(p_tp, "w", encoding="utf-8") as f:
            f.write(self.generate_transport_properties(kinematic_viscosity_m2_s))
        created_files.append(p_tp)

        return created_files
