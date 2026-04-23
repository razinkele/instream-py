"""Tests for NaN guards, capacity monitoring, and logging utilities."""
import logging
import numpy as np
import pytest


class TestCheckNan:
    def test_raises_on_nan_input(self):
        from salmopy.utils.guards import check_nan
        arr = np.array([1.0, np.nan, 3.0])
        with pytest.raises(ValueError, match="NaN"):
            check_nan(arr, "test_array")

    def test_passes_on_clean_input(self):
        from salmopy.utils.guards import check_nan
        arr = np.array([1.0, 2.0, 3.0])
        check_nan(arr, "test_array")  # should not raise

    def test_raises_on_inf_input(self):
        from salmopy.utils.guards import check_nan
        arr = np.array([1.0, np.inf, 3.0])
        with pytest.raises(ValueError, match="Inf"):
            check_nan(arr, "test_array")

    def test_raises_on_negative_inf_input(self):
        from salmopy.utils.guards import check_nan
        arr = np.array([1.0, -np.inf, 3.0])
        with pytest.raises(ValueError, match="Inf"):
            check_nan(arr, "test_array")

    def test_passes_on_empty_array(self):
        from salmopy.utils.guards import check_nan
        arr = np.array([])
        check_nan(arr, "empty")  # should not raise

    def test_warn_mode_logs_instead_of_raising(self, caplog):
        from salmopy.utils.guards import check_nan
        arr = np.array([1.0, np.nan, 3.0])
        with caplog.at_level(logging.WARNING):
            check_nan(arr, "test_array", raise_on_error=False)
        assert "NaN" in caplog.text


class TestCheckCapacity:
    def test_no_warning_below_threshold(self, caplog):
        from salmopy.utils.guards import check_capacity
        with caplog.at_level(logging.WARNING):
            check_capacity(50, 100, "trout")
        assert caplog.text == ""

    def test_warning_at_80_percent(self, caplog):
        from salmopy.utils.guards import check_capacity
        with caplog.at_level(logging.WARNING):
            check_capacity(80, 100, "trout")
        assert "80%" in caplog.text or "capacity" in caplog.text.lower()

    def test_error_at_95_percent(self, caplog):
        from salmopy.utils.guards import check_capacity
        with caplog.at_level(logging.ERROR):
            check_capacity(96, 100, "trout")
        assert "95%" in caplog.text or "capacity" in caplog.text.lower()

    def test_error_at_100_percent(self, caplog):
        from salmopy.utils.guards import check_capacity
        with caplog.at_level(logging.ERROR):
            check_capacity(100, 100, "trout")
        assert "capacity" in caplog.text.lower()


class TestCheckPositive:
    def test_passes_on_positive_values(self):
        from salmopy.utils.guards import check_positive
        arr = np.array([1.0, 2.0, 3.0])
        check_positive(arr, "weights")  # should not raise

    def test_warns_on_negative_values(self, caplog):
        from salmopy.utils.guards import check_positive
        arr = np.array([1.0, -0.5, 3.0])
        with caplog.at_level(logging.WARNING):
            check_positive(arr, "weights")
        assert "negative" in caplog.text.lower() or "weights" in caplog.text

    def test_passes_on_zeros(self):
        from salmopy.utils.guards import check_positive
        arr = np.array([0.0, 0.0])
        check_positive(arr, "values")  # zeros are OK


class TestGetLogger:
    def test_get_logger_returns_logger(self):
        from salmopy.utils.logging import get_logger
        logger = get_logger("test")
        assert isinstance(logger, logging.Logger)

    def test_logger_name_has_instream_prefix(self):
        from salmopy.utils.logging import get_logger
        logger = get_logger("hydraulics")
        assert logger.name == "salmopy.hydraulics"
