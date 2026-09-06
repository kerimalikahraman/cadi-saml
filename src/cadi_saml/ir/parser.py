"""
cadi_saml.ir.parser
===================
Deterministic parser that converts SAML YAML/dict syntax into AssemblyIR.
"""

from __future__ import annotations

import re
import yaml
from typing import Any, Dict, List, Union

from .nodes import (
    AssemblyIR,
    ExportFormat,
    MateNode,
    MateType,
    MetadataNode,
    PartNode,
    PortNode,
    UnitSystem,
)


class SAMLParserError(Exception):
    """Raised when SAML syntax or semantic validation fails."""
    pass


class SAMLParser:
    """Parses SAML YAML specification into an AssemblyIR data structure."""

    @staticmethod
    def parse_string(saml_str: str) -> AssemblyIR:
        """Parse raw YAML or clean markdown codeblocks."""
        clean_text = saml_str.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:yaml|json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)
        
        try:
            data = yaml.safe_load(clean_text)
        except yaml.YAMLError as e:
            raise SAMLParserError(f"YAML Syntax Error: {e}")

        if not isinstance(data, dict):
            raise SAMLParserError("Top-level SAML must be a dictionary or YAML mapping.")

        return SAMLParser.parse_dict(data)

    @staticmethod
    def parse_dict(data: Dict[str, Any]) -> AssemblyIR:
        """Parse structured dictionary into AssemblyIR."""
        # 1. Parse Metadata
        meta_dict = data.get("metadata", {})
        metadata = MetadataNode(
            name=meta_dict.get("name", "UnnamedAssembly"),
            units=UnitSystem(meta_dict.get("units", "mm")),
            tolerance_standard=meta_dict.get("tolerance_standard", "ISO 2768-m"),
            material=meta_dict.get("material"),
            export_formats=[
                ExportFormat(fmt.upper()) for fmt in meta_dict.get("export_formats", ["STEP"])
            ],
            version=str(meta_dict.get("version", "1.0.0")),
        )

        assembly = AssemblyIR(metadata=metadata)

        # 2. Parameters
        for p_name, p_val in data.get("parameters", {}).items():
            assembly.set_param(p_name, float(p_val))

        # 3. Parts
        for p_name, p_def in data.get("parts", {}).items():
            part = PartNode(
                name=p_name,
                part_type=p_def.get("type", "primitive"),
                shape=p_def.get("shape"),
                parameters=p_def.get("parameters", {}),
                source_file=p_def.get("source_file"),
            )
            # Ports
            for port_name, port_def in p_def.get("ports", {}).items():
                port = PortNode(
                    name=port_name,
                    port_type=port_def.get("type", "face"),
                    relative_position=tuple(port_def.get("position", (0.0, 0.0, 0.0))),
                    normal=tuple(port_def.get("normal", (0.0, 0.0, 1.0))),
                    diameter=port_def.get("diameter"),
                )
                part.add_port(port)

            assembly.add_part(part)

        # 4. Mates / Constraints
        for m_def in data.get("mates", []):
            mate = MateNode(
                mate_type=MateType(m_def.get("type", "FLUSH").upper()),
                first_part=m_def["first_part"],
                second_part=m_def["second_part"],
                first_selector=m_def.get("first_selector"),
                second_selector=m_def.get("second_selector"),
                offset=float(m_def.get("offset", 0.0)),
                angle=float(m_def.get("angle", 0.0)),
            )
            assembly.add_mate(mate)

        # Validate
        errors = assembly.validate()
        if errors:
            raise SAMLParserError(f"Validation failed: {'; '.join(errors)}")

        return assembly
