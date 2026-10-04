from pathlib import Path

import pytest

from outpass.cli import ConfigurationError, RequestData, load_json, require_config


def valid_request() -> dict[str, str]:
    return {
        "request_type": "Working Day Pass",
        "departure_date": "2026-10-05",
        "departure_time": "09:00",
        "return_date": "2026-10-05",
        "return_time": "18:00",
        "place": "City center",
        "purpose": "Personal errand",
    }


def test_valid_request() -> None:
    request = RequestData.from_mapping(valid_request())
    assert request.place == "City center"


def test_rejects_return_before_departure() -> None:
    value = valid_request()
    value["return_time"] = "08:00"
    with pytest.raises(ConfigurationError, match="must be after"):
        RequestData.from_mapping(value)


def test_rejects_missing_field() -> None:
    value = valid_request()
    value["purpose"] = ""
    with pytest.raises(ConfigurationError, match="purpose"):
        RequestData.from_mapping(value)


def test_holiday_pass_requires_subtype() -> None:
    value = valid_request()
    value["request_type"] = "Holiday Pass"
    with pytest.raises(ConfigurationError, match="holiday_subtype"):
        RequestData.from_mapping(value)


def test_example_config_uses_supported_request_fields() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    config = load_json(project_dir / "config.example.json")
    require_config(config)

    supported_fields = set(RequestData.__annotations__)
    configured_fields = set(config["request"]["fields"])

    assert configured_fields == supported_fields
