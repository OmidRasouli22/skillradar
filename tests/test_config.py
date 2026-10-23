import pytest
from pydantic import ValidationError

from skillradar.config import SearchConfig, load_config


def test_default_config_loads():
    config = load_config()

    assert "Stuttgart" in config.cities
    assert "Data Engineer" in config.terms
    assert len(config.queries()) == len(config.cities) * len(config.terms)


def test_terms_and_cities_are_unique():
    config = load_config()

    assert len(set(config.cities)) == len(config.cities)
    assert len(set(config.terms)) == len(config.terms)


def test_page_size_above_api_maximum_is_rejected():
    raw = load_config().model_dump(mode="json")
    raw["api"]["page_size"] = 500

    with pytest.raises(ValidationError):
        SearchConfig.model_validate(raw)
