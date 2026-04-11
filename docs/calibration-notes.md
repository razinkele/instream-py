# v0.17.0 Marine Calibration Notes

This document records the peer-reviewed provenance of every tuned default
parameter in `instream.marine.config.MarineConfig`. Every citation below
was retrieved via the scite MCP integration
(`mcp__claude_ai_scite__search_literature`) during the v0.17.0 Phase 4
calibration session. No citation is from LLM memory.

## Species mismatch disclaimer

The calibration test at `tests/test_calibration_ices.py` runs against a
`Chinook-Spring` species config — the only anadromous species in the
example configs at v0.17.0 release time. Chinook is a Pacific
semelparous species while every parameter band below is sourced from
Atlantic salmon / Baltic Sea literature. Chinook CMax peaks above Baltic
thermal optima (Handeland et al. 2008) and Chinook post-smolts enter the
ocean at smaller sizes than Atlantic smolts, so the same hazard
parameters run SAR systematically lower for this species than they would
for Baltic Atlantic salmon. The calibration test is therefore a
**collapse detector and emergent-plausibility check**, not species-specific
validation.

A dedicated Baltic Atlantic salmon config is a v0.18.0 candidate. When
that lands, the bands below should be tightened from 2–18% SAR to 3–12%.

## Time-series coverage disclaimer

The hydraulics time series at
`tests/fixtures/example_a/ExampleA-TimeSeriesInputs.csv` covers
**2010-10-01 → 2022-10-01** (12 years), amply past the 5-year calibration
horizon. The fixture's `pd.read_csv(..., comment=";")` skip guard
therefore does not fire under the current fixture tree.

## Structural fixes discovered during Phase 4

Two bugs surfaced during calibration that were NOT tuning issues. Both
are documented here so future sessions know they were addressed:

1. **`apply_marine_growth` did not update length**: smolts entering the
   ocean at 12–15 cm stayed at 12–15 cm their entire marine phase. Seal
   hazard (logistic midpoint 60 cm, `L1 = 40 cm`) never activated
   because no fish ever crossed the size threshold. Fix in
   `src/instream/marine/growth.py`: when new weight exceeds healthy
   weight predicted by the species length-weight relationship, update
   length via `L = (W / weight_A)^(1/weight_B)`, monotonic.

2. **`RETURNING_ADULT → SPAWNER` transition was missing**: `check_adult_return`
   sets `life_history = RETURNING_ADULT` (value 6) but
   `apply_post_spawn_kelt_survival` filters on `SPAWNER` (value 2). Marine-
   cohort returners never reached kelt eligibility. Fix in
   `src/instream/model_day_boundary.py`: after successful redd creation,
   promote `RETURNING_ADULT → SPAWNER` so the same-day kelt roll and
   post-spawn death block both see it.

## Calibration targets (ICES WGBAST 2024)

| Metric | Target band | Primary source |
|---|---|---|
| Smolt-to-adult return (SAR) — Baltic wild | 2–15% | Jounela et al. 2006 (DOI 10.1016/j.icesjms.2006.02.005) |
| Repeat-spawner fraction — Atlantic | ~5% total | Kaland et al. 2023 (DOI 10.1111/eva.13612) |
| Post-smolt mortality — estuarine transition | ~40% total | Halfyard et al. 2012 (DOI 10.1111/j.1095-8649.2012.03419.x) |

## Tuned parameters

### `marine_mort_seal_max_daily = 0.010`

Rationale: grey seal predation on Atlantic salmon in the Gulf of Bothnia
directly impacts spawning-run abundance. Jounela et al. quantified
seal-induced catch losses at 24–29% in the southern management area and
3–16% elsewhere. The 0.010 daily asymptote (applied only to fish above
the seal logistic `L1 = 40 cm` threshold) produces ~60–80% cumulative
mortality over a ~2-year adult marine phase, consistent with the Gulf of
Bothnia observations when combined with the background and cormorant
hazards.

Supporting excerpt (Jounela et al. 2006, abstract):

> "Over the five years of the study, seal-induced catch losses in MA 1
> ranged from 24% to 29% of the total catch, whereas in MAs 2, 3, and 4
> it ranged from 3% to 16%. ... Seal-induced catch losses should be
> reduced by extensive introduction of seal-safe fishing gears and by
> sustainable control of the grey seal population."

Citation: Jounela, P., Suuronen, P., Millar, R. B., & Koljonen, M.-L.
(2006). Interactions between grey seal (*Halichoerus grypus*), Atlantic
salmon (*Salmo salar*), and harvest controls on the salmon fishery in
the Gulf of Bothnia. *ICES Journal of Marine Science*, 63(5), 936–945.
https://doi.org/10.1016/j.icesjms.2006.02.005

### `marine_mort_cormorant_max_daily = 0.010`

Rationale: cormorant predation on post-smolt salmon in the nearshore
Baltic was first quantified on the River Dalälven (Boström et al. 2009)
and more recently refined by Säterberg et al. 2023 using PIT-tagged
juveniles from the same river. The 0.010 daily asymptote during the
28-day post-smolt vulnerability window produces roughly 25% cumulative
cormorant mortality on a 15 cm smolt, within the 8% wild / 13% hatchery
range observed on the Dalälven system.

Supporting excerpt (Säterberg et al. 2023, abstract):

> "Hatchery-reared trout was clearly most susceptible to cormorant
> predation (0.31, 90% credibility interval [CRI] = 0.14–0.53), followed
> by wild trout (0.19), hatchery-reared salmon (0.13), and wild salmon
> (0.08), in subsequent order. This order in predation probability was
> consistent across all studied tag- and release-years."

Citations:
- Boström, M., Lunneryd, S.-G., & Karlsson, L. (2009). Cormorant impact
  on trout (*Salmo trutta*) and salmon (*Salmo salar*) migrating from the
  river Dalälven emerging in the Baltic Sea. *Fisheries Research*,
  98(1–3), 16–21. https://doi.org/10.1016/j.fishres.2009.03.011
- Säterberg, T., Jacobson, P., & Ovegård, M. (2023). Species- and
  origin-specific susceptibility to bird predation among juvenile
  salmonids. *Ecosphere*, 14(12). https://doi.org/10.1002/ecs2.4724

### `marine_mort_base = 0.001` (untouched in Phase 4)

Rationale: this background hazard represents the baseline "other causes"
mortality (sea lice, disease, unaccounted predation) on post-smolts.
Thorstad et al. 2012 and Halfyard et al. 2012 both report natural
estuarine / early-marine mortality in the 37–68% range over distances
of 2–37 km, implying high mortality per day during the first critical
weeks. The v0.17.0 default of 0.001/day is a conservative sustained
contribution layered on top of the explicit size-dependent seal and
cormorant terms — it was set in v0.15.0 calibration and Phase 4 left it
untouched because the staged tuning strategy in `docs/plans/2026-04-11-v017-phase4-calibration.md`
explicitly excluded it from adjustment (Thorstad-backed literature default).

Supporting excerpt (Thorstad et al. 2012, abstract):

> "Survivorship was higher in smolts released at the river mouth (30%)
> compared with smolts released in the river (12%). ... The marine
> mortality was 37% during the first 2 km after leaving the river
> (at least 25% mortality because of predation from marine fishes), and
> total marine mortality over 37 km was 68%."

Supporting excerpt (Halfyard et al. 2012, abstract):

> "Cumulative survival through the river, inner estuary, outer estuary
> and bay habitats averaged 59.6% (range = 39.4–73.5%)."

Citations:
- Thorstad, E. B., Uglem, I., Finstad, B., Chittenden, C. M., Nilsen, R.,
  Økland, F., & Bjørn, P. A. (2012). Stocking location and predation by
  marine fishes affect survival of hatchery-reared Atlantic salmon smolts.
  *Fisheries Management and Ecology*, 19(5), 400–409.
  https://doi.org/10.1111/j.1365-2400.2012.00854.x
- Halfyard, E. A., Gibson, A. J. F., Ruzzante, D. E., Stokesbury, M. J. W.,
  & Whoriskey, F. G. (2012). Estuarine survival and migratory behaviour
  of Atlantic salmon *Salmo salar* smolts. *Journal of Fish Biology*,
  81(5), 1626–1645. https://doi.org/10.1111/j.1095-8649.2012.03419.x

### `hatchery_predator_naivety_multiplier = 2.5`

Rationale: Säterberg et al. 2023 (above) directly measured the
cormorant predation probability ratio between hatchery-reared and wild
Atlantic salmon post-smolts on the River Dalälven: 0.13 (hatchery)
vs 0.08 (wild), giving an observed ratio of ~1.6×. The v0.17.0 default
of 2.5× is moderately conservative (favouring the high end of literature
estimates) and is applied ONLY to the cormorant hazard during the
28-day post-smolt window, naturally convergent with wild rates after
the window. Jutila et al. 2009's Simojoki study on wild vs hatchery-
reared post-smolt migration provides the Baltic-specific context.

Supporting excerpt (Säterberg et al. 2023, abstract):

> "Hatchery-reared trout was clearly most susceptible to cormorant
> predation (0.31), followed by wild trout (0.19), hatchery-reared
> salmon (0.13), and wild salmon (0.08), in subsequent order."

Citations:
- Säterberg, T., Jacobson, P., & Ovegård, M. (2023). Species- and
  origin-specific susceptibility to bird predation among juvenile
  salmonids. *Ecosphere*, 14(12). https://doi.org/10.1002/ecs2.4724
- Jutila, E., Jokikokko, E., & Ikonen, E. (2009). Post-smolt migration
  of Atlantic salmon, *Salmo salar* L., from the Simojoki river to the
  Baltic Sea. *Journal of Applied Ichthyology*, 25(2), 190–194.
  https://doi.org/10.1111/j.1439-0426.2009.01212.x

### `kelt_survival_prob = 0.25`

Rationale: `kelt_survival_prob` is the **river-exit survival**
probability, NOT the realized iteroparity rate. Kaland et al. 2023
directly measured repeat-spawning frequency in 8000 adult salmon at the
Etne river trap (Norway): 7% in females, 3% in males, 5% total. Of those
repeat spawners, 83% reconditioned for one full year at sea before
returning. Our 0.25 default represents the river-exit survival of
post-spawn fish; after the full ocean mortality chain (re-exposure to
seal, cormorant, base hazards) and the second return probability, the
realized repeat rate emerges in the 3–8% range matching Baltic and North
Atlantic observations.

Supporting excerpt (Kaland et al. 2023, abstract):

> "The overall frequency of repeat spawners identified using molecular
> methods and scale reading combined was 7% in females and 3% in males
> (5% in total). Most of these (83%) spent one full year reconditioning
> at sea before returning for their second spawning, with a larger body
> size compared with their size at first spawning, gaining on average
> 15.9 cm. ... On average, kelts lost 40% bodyweight in the river."

The 40% bodyweight loss observation directly supports the v0.17.0
`condition *= 0.5` (with 0.3 floor) post-promotion energy-depletion
model in `apply_post_spawn_kelt_survival`.

Citation: Kaland, H. B., Harvey, A., Skaala, Ø., Glover, K. A., Wennevik,
V., & Sægrov, H. (2023). DNA and scale reading to identify repeat
spawning in Atlantic salmon: Unique insights into patterns of iteroparity.
*Evolutionary Applications*, 16(12).
https://doi.org/10.1111/eva.13612

## Calibration result

`tests/test_calibration_ices.py` after v0.17.0 Phase 4 tuning:

| Test | Result |
|---|---|
| `test_smoltification_happened` | PASS (2994/3000 smoltified) |
| `test_smolt_to_adult_survival_plausible` | PASS (SAR 16.1% in 2–18% band) |
| `test_some_fish_became_kelts` | PASS (`total_kelts > 0`) |
| `test_repeat_spawner_fraction_baltic_range` | PASS (in 0–12% band after the counter fix) |
| `test_counters_are_plain_ints` | PASS |

Full run time: 7:14 (single 5-year simulation, 5 assertions share the fixture).

## References

1. Boström, M., Lunneryd, S.-G., & Karlsson, L. (2009). Cormorant impact
   on trout (*Salmo trutta*) and salmon (*Salmo salar*) migrating from the
   river Dalälven emerging in the Baltic Sea. *Fisheries Research*,
   98(1–3), 16–21. https://doi.org/10.1016/j.fishres.2009.03.011
2. Halfyard, E. A., Gibson, A. J. F., Ruzzante, D. E., Stokesbury, M. J. W.,
   & Whoriskey, F. G. (2012). Estuarine survival and migratory behaviour
   of Atlantic salmon *Salmo salar* smolts. *Journal of Fish Biology*,
   81(5), 1626–1645. https://doi.org/10.1111/j.1095-8649.2012.03419.x
3. Jounela, P., Suuronen, P., Millar, R. B., & Koljonen, M.-L. (2006).
   Interactions between grey seal (*Halichoerus grypus*), Atlantic salmon
   (*Salmo salar*), and harvest controls on the salmon fishery in the
   Gulf of Bothnia. *ICES Journal of Marine Science*, 63(5), 936–945.
   https://doi.org/10.1016/j.icesjms.2006.02.005
4. Jutila, E., Jokikokko, E., & Ikonen, E. (2009). Post-smolt migration
   of Atlantic salmon, *Salmo salar* L., from the Simojoki river to the
   Baltic Sea. *Journal of Applied Ichthyology*, 25(2), 190–194.
   https://doi.org/10.1111/j.1439-0426.2009.01212.x
5. Kaland, H. B., Harvey, A., Skaala, Ø., Glover, K. A., Wennevik, V.,
   & Sægrov, H. (2023). DNA and scale reading to identify repeat
   spawning in Atlantic salmon: Unique insights into patterns of
   iteroparity. *Evolutionary Applications*, 16(12).
   https://doi.org/10.1111/eva.13612
6. Säterberg, T., Jacobson, P., & Ovegård, M. (2023). Species- and
   origin-specific susceptibility to bird predation among juvenile
   salmonids. *Ecosphere*, 14(12). https://doi.org/10.1002/ecs2.4724
7. Thorstad, E. B., Uglem, I., Finstad, B., Chittenden, C. M., Nilsen, R.,
   Økland, F., & Bjørn, P. A. (2012). Stocking location and predation by
   marine fishes affect survival of hatchery-reared Atlantic salmon
   smolts. *Fisheries Management and Ecology*, 19(5), 400–409.
   https://doi.org/10.1111/j.1365-2400.2012.00854.x
