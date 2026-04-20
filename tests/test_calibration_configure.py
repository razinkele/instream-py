"""Tests for configure.py — regex parameter auto-discovery."""
import pytest
from types import SimpleNamespace


class TestWalkAndDiscover:
    def test_walk_nested_dict(self):
        from instream.calibration import DiscoveryRule, discover_parameters, Transform

        cfg = {
            "species": {
                "Chinook-Spring": {"cmax_A": 0.628, "cmax_B": 0.7},
                "Chinook-Fall": {"cmax_A": 0.55, "cmax_B": 0.68},
            },
        }
        rule = DiscoveryRule("species.*.cmax_A", Transform.LINEAR, factor=2.0)
        params = discover_parameters(cfg, [rule])
        keys = sorted(p.key for p in params)
        assert keys == [
            "species.Chinook-Fall.cmax_A",
            "species.Chinook-Spring.cmax_A",
        ]

    def test_bounds_centered_linear(self):
        from instream.calibration import DiscoveryRule, discover_parameters, Transform

        cfg = {"a": {"x": 10.0}}
        rule = DiscoveryRule("a.x", Transform.LINEAR, factor=2.0)
        p = discover_parameters(cfg, [rule])[0]
        # delta = 10 * (2-1) = 10; bounds = [0, 20]
        assert p.lower == pytest.approx(0.0)
        assert p.upper == pytest.approx(20.0)

    def test_bounds_centered_log(self):
        from instream.calibration import DiscoveryRule, discover_parameters, Transform

        cfg = {"a": {"x": 3.2e-10}}
        rule = DiscoveryRule("a.x", Transform.LOG, factor=10.0)
        p = discover_parameters(cfg, [rule])[0]
        # log: bounds = [v/10, v*10]
        assert p.lower == pytest.approx(3.2e-11)
        assert p.upper == pytest.approx(3.2e-9)

    def test_log_skips_zero_values(self):
        from instream.calibration import DiscoveryRule, discover_parameters, Transform

        cfg = {"a": {"x": 0.0, "y": 5.0}}
        rule = DiscoveryRule("a.*", Transform.LOG, factor=3.0)
        keys = [p.key for p in discover_parameters(cfg, [rule])]
        # x=0 can't log-scan; skipped
        assert keys == ["a.y"]

    def test_first_matching_rule_wins(self):
        from instream.calibration import DiscoveryRule, discover_parameters, Transform

        cfg = {"a": {"cmax_A": 0.5}}
        rule_specific = DiscoveryRule("a.cmax_A", Transform.LOG, factor=10.0)
        rule_generic = DiscoveryRule("a.*", Transform.LINEAR, factor=2.0)
        params = discover_parameters(cfg, [rule_specific, rule_generic])
        assert len(params) == 1
        assert params[0].transform == Transform.LOG

    def test_min_lower_max_upper_caps(self):
        from instream.calibration import DiscoveryRule, discover_parameters, Transform

        cfg = {"a": {"x": 10.0}}
        rule = DiscoveryRule(
            "a.x", Transform.LINEAR, factor=2.0,
            min_lower=5.0, max_upper=15.0,
        )
        p = discover_parameters(cfg, [rule])[0]
        assert p.lower == 5.0
        assert p.upper == 15.0

    def test_walks_dataclass_like_objects(self):
        from instream.calibration import DiscoveryRule, discover_parameters, Transform

        species = SimpleNamespace(cmax_A=0.628, cmax_B=0.7)
        outer = SimpleNamespace(species={"Chinook": species})
        rule = DiscoveryRule("species.*.cmax_A", Transform.LINEAR, factor=2.0)
        params = discover_parameters(outer, [rule])
        assert len(params) == 1
        assert params[0].key == "species.Chinook.cmax_A"

    def test_skips_booleans(self):
        from instream.calibration import DiscoveryRule, discover_parameters, Transform

        cfg = {"a": {"is_anadromous": True, "cmax_A": 0.5}}
        rule = DiscoveryRule("a.*", Transform.LINEAR, factor=2.0)
        keys = [p.key for p in discover_parameters(cfg, [rule])]
        assert keys == ["a.cmax_A"]
