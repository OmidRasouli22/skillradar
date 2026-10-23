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


def test_plain_http_is_rejected():
    raw = load_config().model_dump(mode="json")
    raw["api"]["base_url"] = "http://rest.arbeitsagentur.de/jobboerse/jobsuche-service"

    with pytest.raises(ValidationError, match="https"):
        SearchConfig.model_validate(raw)


def test_only_narrows_the_search():
    config = load_config().only(cities=["Berlin"], terms=["Python", "Java"])

    assert config.queries() == [("Python", "Berlin"), ("Java", "Berlin")]


def test_only_without_filters_keeps_everything():
    config = load_config()

    assert config.only().queries() == config.queries()


def test_only_rejects_unknown_names():
    with pytest.raises(ValueError, match="Atlantis"):
        load_config().only(cities=["Atlantis"])
