"""Tests for light calculations — day length, irradiance, cell light."""

import numpy as np
import pytest


def _get_backend(name):
    from instream.backends import get_backend

    return get_backend(name)


class TestDayLength:
    """Test solar geometry calculations."""

    @pytest.fixture(params=["numpy", "numba"])
    def backend(self, request):
        try:
            return _get_backend(request.param)
        except (NotImplementedError, ImportError):
            pytest.skip(f"{request.param} backend not available")

    def test_equator_equinox_is_half_day(self, backend):
        """At equator on equinox, day and night are equal."""
        day_length, twilight, irradiance = backend.compute_light(
            julian_date=80,
            latitude=0.0,
            light_correction=1.0,
            shading=1.0,
            light_at_night=0.9,
            twilight_angle=6.0,
        )
        np.testing.assert_allclose(day_length, 0.5, atol=0.02)

    def test_arctic_summer_long_day(self, backend):
        """Above arctic circle in summer, nearly 24h daylight."""
        day_length, twilight, irradiance = backend.compute_light(
            julian_date=172,
            latitude=70.0,
            light_correction=1.0,
            shading=1.0,
            light_at_night=0.9,
            twilight_angle=6.0,
        )
        assert day_length > 0.9  # nearly all day

    def test_arctic_winter_short_day(self, backend):
        """Above arctic circle in winter, nearly 0h daylight."""
        day_length, twilight, irradiance = backend.compute_light(
            julian_date=355,
            latitude=70.0,
            light_correction=1.0,
            shading=1.0,
            light_at_night=0.9,
            twilight_angle=6.0,
        )
        assert day_length < 0.1  # nearly all night

    def test_latitude_41_june_21(self, backend):
        """At latitude 41 on June 21, day length ~15.1 hours = ~0.629 days."""
        day_length, twilight, irradiance = backend.compute_light(
            julian_date=172,
            latitude=41.0,
            light_correction=0.7,
            shading=0.9,
            light_at_night=0.9,
            twilight_angle=6.0,
        )
        # 15.1 hours = 0.629 days
        np.testing.assert_allclose(day_length, 0.629, atol=0.015)

    def test_twilight_positive(self, backend):
        """Twilight should be positive for moderate latitudes."""
        _, twilight, _ = backend.compute_light(
            julian_date=172,
            latitude=41.0,
            light_correction=0.7,
            shading=0.9,
            light_at_night=0.9,
            twilight_angle=6.0,
        )
        assert twilight > 0.0

    def test_irradiance_higher_in_summer(self, backend):
        """Irradiance at latitude 41 should be higher in summer than winter."""
        _, _, irr_summer = backend.compute_light(
            julian_date=172,
            latitude=41.0,
            light_correction=0.7,
            shading=0.9,
            light_at_night=0.9,
            twilight_angle=6.0,
        )
        _, _, irr_winter = backend.compute_light(
            julian_date=355,
            latitude=41.0,
            light_correction=0.7,
            shading=0.9,
            light_at_night=0.9,
            twilight_angle=6.0,
        )
        assert irr_summer > irr_winter

    def test_irradiance_positive(self, backend):
        """Irradiance should be non-negative."""
        _, _, irradiance = backend.compute_light(
            julian_date=80,
            latitude=41.0,
            light_correction=0.7,
            shading=0.9,
            light_at_night=0.9,
            twilight_angle=6.0,
        )
        assert irradiance >= 0.0


class TestCellLight:
    """Test light at cell mid-depth (Beer-Lambert)."""

    @pytest.fixture(params=["numpy", "numba"])
    def backend(self, request):
        try:
            return _get_backend(request.param)
        except (NotImplementedError, ImportError):
            pytest.skip(f"{request.param} backend not available")

    def test_light_decreases_with_depth(self, backend):
        """Deeper cells should have less light (Beer-Lambert)."""
        depths = np.array([10.0, 50.0, 100.0, 200.0])
        light = backend.compute_cell_light(
            depths=depths,
            irradiance=100.0,
            turbid_coef=0.0017,
            turbidity=5.0,
            light_at_night=0.9,
        )
        # Light should decrease with depth
        assert np.all(np.diff(light) < 0)

    def test_dry_cell_gets_night_light(self, backend):
        """Cells with depth=0 should get light_at_night value."""
        depths = np.array([0.0, 50.0])
        light = backend.compute_cell_light(
            depths=depths,
            irradiance=100.0,
            turbid_coef=0.0017,
            turbidity=5.0,
            light_at_night=0.9,
        )
        np.testing.assert_allclose(light[0], 0.9)

    def test_turbid_water_less_light(self, backend):
        """Higher turbidity should reduce light at depth."""
        depths = np.array([50.0])
        light_clear = backend.compute_cell_light(
            depths=depths,
            irradiance=100.0,
            turbid_coef=0.0017,
            turbidity=1.0,
            light_at_night=0.9,
        )
        light_turbid = backend.compute_cell_light(
            depths=depths,
            irradiance=100.0,
            turbid_coef=0.0017,
            turbidity=20.0,
            light_at_night=0.9,
        )
        assert light_clear[0] > light_turbid[0]

    def test_zero_turbidity_minimal_attenuation(self, backend):
        """With zero turbidity and constant, light barely attenuates."""
        depths = np.array([50.0])
        light = backend.compute_cell_light(
            depths=depths,
            irradiance=100.0,
            turbid_coef=0.0,
            turbidity=0.0,
            light_at_night=0.9,
        )
        # With zero attenuation, light at mid-depth ≈ surface light
        np.testing.assert_allclose(light[0], 100.0, rtol=0.01)


class TestDailyIntegralIrradiance:
    """Verify irradiance uses daily integral, not noon elevation."""

    def test_irradiance_less_than_noon_peak(self):
        """Daily-integrated irradiance must be less than noon-peak."""
        from instream.backends.numpy_backend import NumpyBackend

        backend = NumpyBackend()
        _dl, _tl, irr = backend.compute_light(172, 45.0, 1.0, 1.0, 0.0, 6.0)
        noon_peak = 1360.0 * np.sin(np.radians(90.0 - abs(45.0 - 23.45)))
        assert irr < noon_peak * 0.85, (
            f"irradiance {irr:.1f} should be well below noon peak {noon_peak:.1f}"
        )

    def test_irradiance_zero_at_polar_winter(self):
        from instream.backends.numpy_backend import NumpyBackend

        backend = NumpyBackend()
        _dl, _tl, irr = backend.compute_light(355, 80.0, 1.0, 1.0, 0.0, 6.0)
        assert irr == 0.0

    def test_irradiance_equator_equinox(self):
        """At equator on equinox: I = (S0/pi) * sin(pi/2) = S0/pi ~ 433."""
        from instream.backends.numpy_backend import NumpyBackend

        backend = NumpyBackend()
        _dl, _tl, irr = backend.compute_light(80, 0.0, 1.0, 1.0, 0.0, 6.0)
        expected = 1360.0 / np.pi
        assert abs(irr - expected) < 50.0, (
            f"equator equinox irradiance {irr:.1f} should be near {expected:.1f}"
        )

    def test_irradiance_backend_parity_numba(self):
        pytest.importorskip("numba")
        from instream.backends.numpy_backend import NumpyBackend
        from instream.backends.numba_backend import NumbaBackend

        np_b = NumpyBackend()
        nb_b = NumbaBackend()
        for jd in [1, 80, 172, 266, 355]:
            for lat in [0.0, 30.0, 60.0, 80.0]:
                np_r = np_b.compute_light(jd, lat, 1.0, 1.0, 0.0, 6.0)
                nb_r = nb_b.compute_light(jd, lat, 1.0, 1.0, 0.0, 6.0)
                np.testing.assert_allclose(
                    np_r[2], nb_r[2], rtol=1e-10, err_msg=f"jd={jd}, lat={lat}"
                )


class TestLightBackendParity:
    """Verify numpy and numba produce identical light results."""

    def test_compute_light_parity(self):
        try:
            np_b = _get_backend("numpy")
            nb_b = _get_backend("numba")
        except (NotImplementedError, ImportError):
            pytest.skip("Numba not available")

        for jd in [1, 80, 172, 265, 355]:
            for lat in [0, 20, 41, 60, 70]:
                r_np = np_b.compute_light(jd, lat, 0.7, 0.9, 0.9, 6.0)
                r_nb = nb_b.compute_light(jd, lat, 0.7, 0.9, 0.9, 6.0)
                np.testing.assert_allclose(
                    r_np,
                    r_nb,
                    rtol=1e-12,
                    err_msg=f"Light parity failed at jd={jd}, lat={lat}",
                )

    def test_cell_light_parity(self):
        try:
            np_b = _get_backend("numpy")
            nb_b = _get_backend("numba")
        except (NotImplementedError, ImportError):
            pytest.skip("Numba not available")

        depths = np.array([0.0, 10.0, 50.0, 100.0, 200.0])
        r_np = np_b.compute_cell_light(depths, 100.0, 0.0017, 5.0, 0.9)
        r_nb = nb_b.compute_cell_light(depths, 100.0, 0.0017, 5.0, 0.9)
        np.testing.assert_allclose(r_np, r_nb, rtol=1e-12)


class TestTurbidityConstant:
    """Test the additive turbidity constant in Beer-Lambert attenuation."""

    def test_turbidity_constant_increases_attenuation(self):
        from instream.backends.numpy_backend import NumpyBackend

        backend = NumpyBackend()
        depths = np.array([50.0, 100.0])
        light_no_const = backend.compute_cell_light(
            depths, 500.0, 0.01, 5.0, 0.001, 0.0
        )
        light_with_const = backend.compute_cell_light(
            depths, 500.0, 0.01, 5.0, 0.001, 0.005
        )
        np.testing.assert_array_less(light_with_const, light_no_const)

    def test_zero_constant_unchanged(self):
        from instream.backends.numpy_backend import NumpyBackend

        backend = NumpyBackend()
        depths = np.array([0.0, 50.0, 100.0])
        light = backend.compute_cell_light(depths, 500.0, 0.01, 5.0, 0.001, 0.0)
        expected_50 = 500.0 * np.exp(-0.05 * 50.0 / 2.0)
        np.testing.assert_allclose(light[1], expected_50, rtol=1e-12)
