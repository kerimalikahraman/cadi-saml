# CADi SAML Training Data Contract & Evaluation Protocol (v0.6.0)

This specification defines the formal data contract, provenance tracking rules, schema invariants, and evaluation protocols for CADi SAML fine-tuning datasets.

---

## 1. Core Engineering Principles

CADi SAML is designed for deterministic, LLM-native mechanical CAD generation. To prevent LLM hallucinations, fabricated dimensions, and unverified solid models, training datasets must adhere to three non-negotiable rules:

1. **Zero Parameter Guessing**: An AI model must never invent unrequested dimensions. If an engineering prompt lacks internal parameters (e.g. wall thickness, bolt diameter, flange thickness), these values must be explicitly resolved from authoritative standard catalogs (`DIN`, `ISO`, `EN`) with formal provenance tracking.
2. **Deterministic B-Rep & Contract Execution**: Every training sample must compile into a valid, watertight, manifold OpenCASCADE solid and pass all post-build contract stages (`compilation`, `manifold`, `dimensions`, `interference`, `kinematics`, `provenance`).
3. **Auditability & Reproducibility**: Every dataset record includes a formal JSON Schema, a deterministic SHA-256 checksum, a mathematical `spec_completeness` ratio, and verifiable standard references.

---

## 2. Specification Completeness (`spec_completeness`)

Specification completeness measures the proportion of final geometry defined explicitly by user intent versus standard engineering catalogs:

$$\text{spec\_completeness} = \frac{|\mathcal{P}_{\text{input}}|}{|\mathcal{P}_{\text{input}}| + |\mathcal{P}_{\text{catalog}}|}$$

Where:
- $\mathcal{P}_{\text{input}}$: Set of parameters explicitly provided in the user prompt (e.g., beam length, envelope height, flange width).
- $\mathcal{P}_{\text{catalog}}$: Set of standard parameters retrieved from authoritative norms (e.g., DIN 1025 web/flange thickness).

**Examples**:
- Fully specified prompt (e.g., planetary gear train with module, tooth counts, width): $\text{spec\_completeness} = 1.0$.
- Standard I-beam (length, height, width provided; web & flange from DIN 1025-1): $\text{spec\_completeness} = \frac{3}{3 + 2} = 0.60$.

---

## 3. Dataset JSON Schema Invariants

All dataset files (`saml_gold_dataset.jsonl`, `saml_negative_dataset.jsonl`) conform strictly to [`schema/saml_dataset_schema.json`](file:///c:/Users/Kahraman/Documents/Cad_Ai/library/schema/saml_dataset_schema.json):

```json
{
  "id": "saml_gold_000001",
  "instruction": "Create an 80mm tall structural I-beam with length 200mm and flange width 46mm.",
  "input": "",
  "output": "from cadi_saml import Assembly\n...",
  "output_type": "executable_code",
  "metadata": {
    "category": "structural_beam",
    "spec_completeness": 0.60,
    "contract_verified": true,
    "provenance_tracked": true,
    "source_standards": ["DIN 1025-1 IPE 80"],
    "execution_status": "verified_passed",
    "reasoning_summary": "User requested IPE 80 envelope (L=200, h=80, b=46). Standard thicknesses (tw=3.8, tf=5.2) retrieved from DIN 1025-1 IPE 80.",
    "input_parameters": {"length": 200.0, "height": 80.0, "flange_width": 46.0},
    "catalog_parameters": {"web_thickness": 3.8, "flange_thickness": 5.2},
    "derived_parameters": {},
    "generator_meta": {
      "generator_version": "0.6.0",
      "library_version": "0.6.0",
      "catalog_version": "2026.1",
      "seed": 42,
      "checksum": "a8f3b21c90de4567"
    }
  }
}
```

---

## 4. Negative Dataset & Diagnostic Error Handling

In addition to positive gold samples, fine-tuning requires error prevention training on invalid, contradictory, or underspecified engineering prompts:

| Flaw Category | Cause | Expected LLM Output |
| :--- | :--- | :--- |
| **Underspecified Pipe** | No OD and no standard schedule | `CADISpecificationError(parameter='outer_dia')` |
| **Unknown Thread** | `M999` requested (non-ISO) | `CADISpecificationError(parameter='thread')` |
| **Kinematic Violation** | $z_r \neq z_s + 2 z_p$ in planetary gearbox | `CADISpecificationError(parameter='ring_teeth')` |
| **Ghost Part** | Contract checks part not in assembly | `CADISpecificationError(parameter='expected_specs.parts')` |
| **NaN / Bad Tolerance** | `max_clash_volume_mm3=NaN` | `CADISpecificationError(parameter='max_clash_volume_mm3')` |
| **Conflicting Specs** | Overlapping contradictory part specs | `CADISpecificationError(parameter='expected_specs')` |
| **Provenance Mismatch** | `effective_value` does not match model | `CADISpecificationError(parameter='provenance.effective_value')` |
| **Physical Collision** | Complete overlapping solid bodies | `CADISpecificationError(parameter='interference')` |

Target output for negative samples is formatted as structured diagnostic JSON to prevent the LLM from outputting faulty geometry.

---

## 5. Execution Runner & Audit Protocol

The validation script [`scripts/validate_gold_dataset.py`](file:///c:/Users/Kahraman/Documents/Cad_Ai/library/scripts/validate_gold_dataset.py) evaluates datasets using isolated sub-processes:

```bash
# Run isolated subprocess execution and parameter audit on all gold samples
python scripts/validate_gold_dataset.py --gold

# Validate negative diagnostic samples
python scripts/validate_gold_dataset.py --negative

# Run complete evaluation across all datasets
python scripts/validate_gold_dataset.py --all
```

CI tests in [`tests/test_ai_engine.py`](file:///c:/Users/Kahraman/Documents/Cad_Ai/library/tests/test_ai_engine.py) assert 100% success rate on both gold and negative datasets.
