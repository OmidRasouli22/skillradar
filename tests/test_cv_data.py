"""Skill families, similarity from postings, and reading the postings for the CV analysis."""

import os

import pytest

from skillradar.cv.families import SkillFamilies, load_families
from skillradar.cv.market import MarketCache, NoMarket, load_market
from skillradar.cv.similarity import Similarity
from skillradar.skills.taxonomy import key, load_taxonomy
from skillradar.transform.runner import serve_dir
from tests.cv_helpers import write_market

TAXONOMY = load_taxonomy()


class TestFamilies:
    def test_the_config_uses_known_names_only(self):
        families = load_families(TAXONOMY)
        assert "AWS" in families.implies["Cloud Computing"]
        assert families.substitutes()[key("Azure")] == {"AWS", "GCP"}

    def test_substitutes_go_both_ways(self):
        subs = load_families(TAXONOMY).substitutes()
        for name, others in subs.items():
            for other in others:
                assert name in {key(o) for o in subs[key(other)]}

    @pytest.mark.parametrize(
        "config, error",
        [
            ({"implies": {"Cloud Computing": ["AWZ"]}}, "AWZ"),
            ({"families": [["AWS", "Asure"]]}, "Asure"),
            ({"implies": {"SQL": ["SQL"]}}, "implies itself"),
            ({"families": [["AWS"]]}, "two or more"),
            ({"families": [["AWS", "AWS"]]}, "two or more"),
        ],
    )
    def test_mistakes_are_found(self, config, error):
        with pytest.raises(ValueError, match=error):
            SkillFamilies.model_validate(config).check(TAXONOMY)


class TestSimilarity:
    def test_skills_of_the_same_kind_of_job_are_alike(self):
        postings = [["AWS", "Terraform", "Kubernetes"]] * 3 + [
            ["GCP", "Terraform", "Kubernetes"]
        ] * 3
        postings += [["Excel", "SAP", "Word"]] * 3
        sim = Similarity(postings, min_postings=3)
        assert sim.of("AWS", "GCP") == pytest.approx(1.0)
        assert sim.of("AWS", "Excel") == 0.0
        assert sim.of("aws", "AWS") == 1.0

    def test_rare_skills_have_no_likeness(self):
        sim = Similarity([["AWS", "Rust"]] + [["AWS", "Go"]] * 3, min_postings=3)
        assert sim.of("Rust", "AWS") is None
        assert sim.of("Unknown", "AWS") is None

    def test_empty(self):
        assert Similarity([]).of("AWS", "GCP") is None


class TestMarket:
    def test_load(self, tmp_path):
        write_market(tmp_path)
        market = load_market(serve_dir(tmp_path), TAXONOMY)
        assert market.as_of == "2026-11-08"
        by_refnr = {p.refnr: p for p in market.postings}
        assert by_refnr["p1"].regions == {"BERLIN"} and by_refnr["p4"].regions == frozenset()
        assert by_refnr["p1"].published == "2026-11-05" and by_refnr["p3"].published is None
        # "Golang" (nice) and "Go" (required) are one skill now, and required.
        p2 = {s.name: s.required for s in by_refnr["p2"].skills}
        assert p2 == {"Azure": True, "Go": True, "Python": True, "Spark": True}

    def test_no_data(self, tmp_path):
        with pytest.raises(NoMarket):
            load_market(serve_dir(tmp_path), TAXONOMY)
        with pytest.raises(NoMarket):
            MarketCache(serve_dir(tmp_path), TAXONOMY).get()

    def test_cache_reads_again_after_a_build(self, tmp_path):
        write_market(tmp_path)
        cache = MarketCache(serve_dir(tmp_path), TAXONOMY)
        first = cache.get()
        assert cache.get() is first
        path = serve_dir(tmp_path) / "gold_postings.parquet"
        stat = path.stat()
        os.utime(path, (stat.st_atime, stat.st_mtime + 10))
        assert cache.get() is not first
