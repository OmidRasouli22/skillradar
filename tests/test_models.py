import pytest

from skillradar.ingestion.models import is_valid_refnr, refnr_of
from tests.helpers import posting


@pytest.mark.parametrize(
    "refnr", ["10001-1003252000-S", "13635-55654e14_JB5269454-S", "12688-REG-43773-RJA-S"]
)
def test_real_refnrs_are_valid(refnr):
    assert is_valid_refnr(refnr)
    assert refnr_of(posting(refnr)) == refnr


@pytest.mark.parametrize("value", [None, 42, "", "../a", "a/b", "a\nb", "ä", "x" * 65])
def test_unsafe_refnrs_are_rejected(value):
    assert not is_valid_refnr(value)
    assert refnr_of(posting(value)) is None


def test_missing_refnr():
    assert refnr_of({}) is None
