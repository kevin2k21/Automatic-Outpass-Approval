from unittest.mock import Mock

import pytest

from outpass.cli import ConfigurationError, fill_field


def test_matching_readonly_field_is_accepted() -> None:
    locator = Mock()
    locator.evaluate.return_value = "input"
    locator.get_attribute.side_effect = lambda name: {"role": None, "readonly": ""}.get(name)
    locator.input_value.return_value = "2026-10-05"
    page = Mock()
    page.locator.return_value.first = locator

    fill_field(page, "input[name='returnDate']", "2026-10-05")

    locator.fill.assert_not_called()


def test_conflicting_readonly_field_is_rejected() -> None:
    locator = Mock()
    locator.evaluate.return_value = "input"
    locator.get_attribute.side_effect = lambda name: {"role": None, "readonly": ""}.get(name)
    locator.input_value.return_value = "2026-10-05"
    page = Mock()
    page.locator.return_value.first = locator

    with pytest.raises(ConfigurationError, match="locked"):
        fill_field(page, "input[name='returnDate']", "2026-10-06")
