import importlib


def test_environment_component_package_imports() -> None:
    assert importlib.import_module("paystub_agi").__name__ == "paystub_agi"


def test_environment_idp_core_has_table_models() -> None:
    evidence = importlib.import_module("idp_core.models.evidence")

    assert hasattr(evidence, "Table")
    assert hasattr(evidence, "TableCell")


def test_environment_idp_ocr_is_the_tables_branch() -> None:
    # Only feature/tables ships the digital table detector.
    module = importlib.import_module("idp_ocr.readers.digital.tables")

    assert module.__name__ == "idp_ocr.readers.digital.tables"


def test_environment_idp_genai_service_exposes_capabilities() -> None:
    service = importlib.import_module("idp_genai.service")

    assert hasattr(service.GenAIService, "capabilities")
