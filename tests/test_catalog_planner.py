from pipeline_toolkit.catalog import Module, ModuleCatalog, load_catalog, plan_affected_modules


def catalog() -> ModuleCatalog:
    return ModuleCatalog(
        modules=(
            Module("catalog", ("modules/catalog/**",), (), "./gradlew :modules:catalog:test", "medium"),
            Module("spring-api", ("apps/spring-api/**",), ("catalog",), "./gradlew :apps:spring-api:test", "heavy"),
            Module("audio", ("modules/audio/**",), (), "./gradlew :modules:audio:test", "medium"),
        ),
        always_full_paths=("build-logic/**",),
    )


def test_planner_selects_changed_module_and_reverse_dependency():
    plan = plan_affected_modules(catalog(), ("modules/catalog/src/Catalog.java",))

    assert plan.full_suite is False
    assert plan.reason == "affected"
    assert tuple(module.id for module in plan.modules) == ("catalog", "spring-api")


def test_planner_falls_back_to_full_suite_for_common_path():
    plan = plan_affected_modules(catalog(), ("build-logic/src/main/kotlin/conventions.gradle.kts",))

    assert plan.full_suite is True
    assert plan.reason == "always-full-path"
    assert tuple(module.id for module in plan.modules) == ("audio", "catalog", "spring-api")


def test_catalog_loader_reads_v1_yaml(tmp_path):
    path = tmp_path / "catalog.yml"
    path.write_text(
        """version: 1
modules:
  - id: catalog
    kind: gradle
    paths: [modules/catalog/**]
    depends_on: []
    test_command: ./gradlew :modules:catalog:test --no-daemon
    tier: pr-and-release
    resource_profile: medium
always_full_paths: [build-logic/**]
"""
    )

    catalog = load_catalog(path)

    assert catalog.modules[0].id == "catalog"
    assert catalog.always_full_paths == ("build-logic/**",)
