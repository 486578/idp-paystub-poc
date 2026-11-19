import paystub_agi


def test_public_api_exports_the_component() -> None:
    assert set(paystub_agi.__all__) == {
        "AnalyzerConfig",
        "AutoTextractReader",
        "ConfigError",
        "ExtractionError",
        "FileEvidenceStore",
        "PaystubAgiError",
        "PaystubAnalyzer",
        "PaystubResult",
        "ReadingError",
        "StoreError",
        "StubStatus",
    }
    for name in paystub_agi.__all__:
        assert getattr(paystub_agi, name) is not None
