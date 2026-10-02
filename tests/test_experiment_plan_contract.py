import pytest

from pipeline_toolkit.experiments import contract


@pytest.mark.parametrize("selected_scope,expected", [
    ("ci", {"suite": "full-java", "argv": ["./gradlew", "check"], "fixture": {"seed": 42}, "modules": ["api", "worker"]}),
    ("test", {"suite": "unit-java", "argv": ["./gradlew", "test"], "dependency_mode": "locked"}),
])
def test_selector_preserves_complete_selected_execution_data(selected_scope, expected):
    plan = {"version": 1, "scopes": {
        "ci": {"suite": "full-java", "argv": ["./gradlew", "check"], "fixture": {"seed": 42}, "modules": ["api", "worker"]},
        "test": {"suite": "unit-java", "argv": ["./gradlew", "test"], "dependency_mode": "locked"},
    }}
    assert contract.select_test_plan_scope(plan, selected_scope) == expected


@pytest.mark.parametrize("selected_scope", ["ci", "test"])
def test_unversioned_legacy_plan_selects_only_its_declared_scope(selected_scope):
    plan = {"scope": selected_scope, "suite": "full-java", "argv": ["./gradlew", "check"]}
    assert contract.select_test_plan_scope(plan, selected_scope) == {
        "scope": selected_scope, "suite": "full-java", "argv": ["./gradlew", "check"],
    }
    with pytest.raises(contract.ExperimentError, match="source_identity_unverified"):
        contract.select_test_plan_scope(plan, "test" if selected_scope == "ci" else "ci")


@pytest.mark.parametrize("plan,selected_scope", [
    (None, "ci"),
    ([], "ci"),
    ({}, "ci"),
    ({"version": 1, "scopes": {"ci": {"suite": "full-java"}}}, "unknown"),
    ({"version": 1, "scopes": {"ci": {"suite": "full-java"}}}, None),
    ({"version": 1, "scopes": {"ci": {"suite": "full-java"}}}, "test"),
    ({"version": 1, "scopes": {"ci": {"suite": "full-java"}, "unknown": {"suite": "full-java"}}}, "ci"),
    ({"version": 2, "scopes": {"ci": {"suite": "full-java"}}}, "ci"),
    ({"version": True, "scopes": {"ci": {"suite": "full-java"}}}, "ci"),
    ({"version": 1.0, "scopes": {"ci": {"suite": "full-java"}}}, "ci"),
    ({"scopes": {"ci": {"suite": "full-java"}}}, "ci"),
    ({"version": 1}, "ci"),
    ({"version": 1, "scopes": []}, "ci"),
    ({"version": 1, "scopes": {}}, "ci"),
    ({"version": 1, "scopes": {"ci": []}}, "ci"),
    ({"version": 1, "scopes": {"ci": {}}}, "ci"),
    ({"version": 1, "scopes": {"ci": {"suite": ""}}}, "ci"),
    ({"version": 1, "scopes": {"ci": {"suite": "  "}}}, "ci"),
    ({"version": 1, "scopes": {"ci": {"suite": 1}}}, "ci"),
    ({"version": 1, "scopes": {"ci": {"suite": "full-java"}, "test": {}}}, "ci"),
    ({"version": 1, "scopes": {"ci": {"suite": "full-java"}}, "scope": "ci"}, "ci"),
    ({"version": 1, "scopes": {"ci": {"suite": "full-java"}}, "suite": "full-java"}, "ci"),
    ({"scope": "ci", "suite": "full-java", "version": 1}, "ci"),
    ({"scope": "ci", "suite": "full-java", "scopes": {}}, "ci"),
    ({"scope": "unknown", "suite": "full-java"}, "unknown"),
    ({"scope": "ci"}, "ci"),
    ({"scope": "ci", "suite": ""}, "ci"),
])
def test_selector_rejects_malformed_or_ambiguous_plan_without_fallback(plan, selected_scope):
    with pytest.raises(contract.ExperimentError, match="source_identity_unverified"):
        contract.select_test_plan_scope(plan, selected_scope)
