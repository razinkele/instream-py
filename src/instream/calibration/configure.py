"""Regex auto-discovery of FreeParameters from a loaded config.

Adapted from osmopy's `calibration/configure.py`. Given a config
object (dict-of-dicts OR Pydantic ModelConfig) and a list of regex
patterns, scans the config tree and produces FreeParameter instances
with sane default bounds (±factor around current value).

Key use case: in a calibration session you rarely want to hand-list
20 FreeParameters. Instead, say "all species.*.cmax_A and
reaches.*.drift_conc" — let the scanner find them and pick bounds
centered on the current YAML values.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Pattern, Sequence, Tuple

from instream.calibration.problem import FreeParameter, Transform


@dataclass
class DiscoveryRule:
    """One regex auto-discovery pattern.

    Attributes
    ----------
    pattern : str
        Dot-delimited regex; segments are joined by `\\.` in the final
        compiled regex. Example: `"species.*.cmax_A"` matches
        "species.Chinook-Spring.cmax_A" and any other species.
    transform : Transform
        LINEAR or LOG. LOG is default for concentrations/rates.
    factor : float
        Multiplicative factor for default bounds:
        lower = current/factor, upper = current*factor. Default 3×.
    min_lower : float, optional
        Floor for lower bound (prevents e.g. drift_conc going below 0).
    max_upper : float, optional
        Cap for upper bound.
    """
    pattern: str
    transform: Transform = Transform.LINEAR
    factor: float = 3.0
    min_lower: Optional[float] = None
    max_upper: Optional[float] = None

    def compiled(self) -> Pattern[str]:
        # Escape literal dots in pattern, but leave `.*` alone
        parts = self.pattern.split(".")
        escaped = []
        for p in parts:
            if p == "*":
                escaped.append(r"[^.]+")
            else:
                escaped.append(re.escape(p))
        return re.compile(r"^" + r"\.".join(escaped) + r"$")


def _walk(
    obj: Any,
    prefix: str = "",
) -> Iterable[Tuple[str, Any]]:
    """Yield (dot.path, value) pairs for all leaf numeric attributes in obj.

    Recurses into dicts and Pydantic model-like objects.
    """
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield prefix, obj
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            sub = f"{prefix}.{k}" if prefix else str(k)
            yield from _walk(v, sub)
        return
    if hasattr(obj, "__dict__") or hasattr(obj, "model_fields"):
        # Pydantic v2 exposes model_fields; dataclass uses __dict__.
        if hasattr(obj, "model_fields"):
            field_names = list(obj.model_fields.keys())
        else:
            field_names = list(vars(obj).keys())
        for name in field_names:
            if name.startswith("_"):
                continue
            try:
                v = getattr(obj, name)
            except AttributeError:
                continue
            sub = f"{prefix}.{name}" if prefix else name
            yield from _walk(v, sub)
        return
    # Anything else (list, str, None, ...) — skip
    return


def discover_parameters(
    config: Any,
    rules: Sequence[DiscoveryRule],
) -> List[FreeParameter]:
    """Scan config, return FreeParameter for every leaf matching any rule.

    Multiple rules may match the same key; the FIRST matching rule wins
    (so order them by specificity, most specific first).

    If the current value is 0 and transform=LOG, the param is skipped
    (can't log-scan from zero).
    """
    compiled_rules = [(r, r.compiled()) for r in rules]
    out: List[FreeParameter] = []
    seen_keys: set = set()

    for key, value in _walk(config):
        if key in seen_keys:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        for rule, regex in compiled_rules:
            if regex.match(key):
                v = float(value)
                if rule.transform is Transform.LOG and v <= 0.0:
                    break  # skip — can't log-scan
                if rule.transform is Transform.LOG:
                    lower = v / rule.factor
                    upper = v * rule.factor
                else:
                    delta = abs(v) * (rule.factor - 1.0) if v != 0 else rule.factor
                    lower = v - delta
                    upper = v + delta
                if rule.min_lower is not None:
                    lower = max(lower, rule.min_lower)
                if rule.max_upper is not None:
                    upper = min(upper, rule.max_upper)
                out.append(
                    FreeParameter(
                        key=key,
                        lower=float(lower),
                        upper=float(upper),
                        transform=rule.transform,
                    )
                )
                seen_keys.add(key)
                break
    return out
