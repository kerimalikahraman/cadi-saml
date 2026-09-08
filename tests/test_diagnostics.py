from cadi_saml import environment_report


def test_environment_report_is_json_serializable_and_non_fatal():
    report = environment_report()
    assert report["cadi_saml_version"]
    assert report["python_version"]
    assert {"numpy", "scipy", "gmsh", "cadquery-ocp", "pyyaml"} <= set(report["dependencies"])
    assert isinstance(report["calculix"]["available"], bool)
