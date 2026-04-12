"""Quick diagnostic: growth_rate_for at realistic available_drift levels."""
from instream.modules.growth import growth_rate_for
import numpy as np

kwargs = dict(
    activity=0, length=4.5, weight=0.7, depth=30.0, velocity=15.0,
    light=50.0, turbidity=3.0, temperature=10.0,
    drift_conc=3.2e-10, search_prod=0.0, search_area=20000.0,
    available_search=0.0, available_shelter=0.0,
    shelter_speed_frac=0.0, superind_rep=1, prev_consumption=0.0,
    step_length=1.0, cmax_A=0.303, cmax_B=-0.275,
    cmax_temp_table_x=np.array([0., 4., 8., 13., 16., 18., 19., 20.]),
    cmax_temp_table_y=np.array([0., 0.3, 0.7, 0.95, 1.0, 0.6, 0.3, 0.]),
    react_dist_A=4.0, react_dist_B=2.0, turbid_threshold=5.0,
    turbid_min=0.1, turbid_exp=-0.116, light_threshold=20.0,
    light_min=0.5, light_exp=-0.2, capture_R1=1.3, capture_R9=0.4,
    max_speed_A=2.8, max_speed_B=21.0, max_swim_temp_term=1.0,
    resp_A=36.0, resp_B=0.783, resp_D=1.4, resp_temp_term=1.0,
    prey_energy_density=2500.0, fish_energy_density=5900.0,
)

for ad in [1.0, 0.01, 0.001, 0.0005, 0.0001, 0.0]:
    g = growth_rate_for(available_drift=ad, **kwargs)
    print(f"available_drift={ad:10.5f}  growth={g:+.8f} g/d  {'POS' if g > 0 else 'NEG'}")
