import copy
import json
import pytest

from cadi_saml import Assembly


def test_runtime_schema_is_json_safe_and_matches_signature():
    asm = Assembly("schema")
    catalog = asm.api_schema()
    json.dumps(catalog)
    box = catalog["capabilities"]["add_box"]
    assert box["source"] == "runtime_signature"
    assert box["parameters"]["name"]["required"] is True
    assert box["parameters"]["origin"]["default"] == [0.0, 0.0, 0.0]
    assert box["parameters"]["height"]["unit"] == "mm"
    assert "add_bolted_joint" in catalog["assembly_macros"]
    assert asm.describe_macro("add_bolted_joint")["parameters"]["thread"]["pattern"]
    with pytest.raises(KeyError):
        asm.describe("_replace_ir")


def test_compact_inspect_and_semantic_diff():
    asm = Assembly("context")
    box = asm.add_box("base", 10, 20, 30)
    box.add_port("mount", position=(0, 0, 15), diameter=5)
    asm.checkpoint("initial")
    context = asm.inspect("base", include=["parameters", "ports"])
    json.dumps(context)
    assert context["part_count"] == 1
    assert context["parts"][0]["ports"][0]["name"] == "mount"
    asm.add_cylinder("pin", 2, 5)
    asm.patch({"base.parameters.length": 12})
    diff = asm.diff_since("initial")
    assert diff["added_parts"] == ["pin"]
    assert diff["changed_parts"] == [{"part": "base", "fields": ["parameters"]}]


def test_preview_patch_isolated_validation_commit_and_conflict():
    asm = Assembly("patch")
    asm.add_box("block", 10, 20, 30)
    before = copy.deepcopy(asm.to_ir().parts["block"].parameters)
    proposal = asm.preview_patch({"block.parameters.length": 15})
    assert asm.to_ir().parts["block"].parameters == before
    assert proposal.validate()["valid"]
    proposal.commit()
    assert asm.to_ir().parts["block"].parameters["length"] == 15
    assert asm._parts["block"].parameters["length"] == 15
    with pytest.raises(RuntimeError, match="already committed"):
        proposal.commit()

    stale = asm.preview_patch({"block.parameters.width": 25})
    asm.patch({"block.parameters.height": 35})
    assert stale.validate()["valid"]
    with pytest.raises(RuntimeError, match="changed after preview"):
        stale.commit()


def test_preview_patch_rejects_unknown_or_invalid_paths_without_mutation():
    asm = Assembly("invalid")
    asm.add_box("block", 10, 20, 30)
    before = copy.deepcopy(asm.to_ir())
    with pytest.raises(KeyError):
        asm.preview_patch({"block.parameters.typo": 1})
    with pytest.raises(ValueError, match="protected"):
        asm.preview_patch({"block.ports": {}})
    with pytest.raises(TypeError, match="finite number"):
        asm.preview_patch({"block.parameters.length": float("nan")})
    assert asm.to_ir() == before


def test_structured_diagnostic_has_actionable_codes():
    asm = Assembly("issues")
    asm.add_box("a", 10, 10, 10)
    asm.add_box("b", 10, 10, 10)
    report = asm.diagnose()
    json.dumps(report)
    assert report["status"] == "FAIL"
    issue = next(i for i in report["issues"] if i["code"] == "VOLUMETRIC_CLASH")
    assert issue["parts"] == ["a", "b"]
    assert issue["actual"]["intersection_volume_mm3"] > 0
    assert issue["repair_options"]
