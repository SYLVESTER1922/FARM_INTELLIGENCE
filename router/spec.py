"""
The routed spec: the ONLY thing the LLM produces (plan decision D11). A closed schema built from the registry, so the model can
name only registry metrics and known dimensions; everything else is validated in code before anything runs.

The LLM never computes a date, a number or a SQL clause. It copies the words that name a period (`period_phrase`) and the domain
words it saw; the scope resolver reads the same words independently, and any disagreement becomes a clarifying question
(router/crosscheck.py), never a silent pick.
"""

import re
from dataclasses import dataclass, field

from catalog.untracked import KNOWN, OUT_OF_SCOPE
from registry import REGISTRY

NONE = "none"                                     # sentinel in place of null, so one schema works across providers
METRIC_IDS = tuple(sorted(REGISTRY))
DOMAINS = ("piggery", "poultry", "crops", "shared")
DIMENSIONS = (NONE, "domain", "category", "buyer", "product", "batch")
AGGREGATIONS = ("total", "avg_per_week")
GRAINS = (NONE, "month")
REFUSALS = (NONE, *(u.code for u in KNOWN), OUT_OF_SCOPE[0])        # the curated list in catalog/untracked.py

# Which dimensions a metric accepts (the registry's own declaration, plus the default 'domain' view for the money metrics).
_REGISTRY_DIMS = {m.id: set(m.dimensions) for m in REGISTRY.values()}
ALLOWED_DIMENSIONS = {mid: dims | ({"domain"} if mid in ("expenses", "revenue") else set()) for mid, dims in _REGISTRY_DIMS.items()}


def json_schema() -> dict:
    """Strict JSON schema: every property required, nothing extra, every free choice an enum."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["metric", "dimension", "category_text", "domains", "period_phrase", "all_time", "aggregation",
                     "grain", "ambiguous_between", "refusal", "follow_up"],
        "properties": {
            "metric": {"type": "string", "enum": [*METRIC_IDS, NONE]},
            "dimension": {"type": "string", "enum": list(DIMENSIONS)},
            "category_text": {"type": "string"},
            "domains": {"type": "array", "items": {"type": "string", "enum": list(DOMAINS)}},
            "period_phrase": {"type": "string"},
            "all_time": {"type": "boolean"},
            "aggregation": {"type": "string", "enum": list(AGGREGATIONS)},
            "grain": {"type": "string", "enum": list(GRAINS)},
            "ambiguous_between": {"type": "array", "items": {"type": "string", "enum": list(METRIC_IDS)}},
            "refusal": {"type": "string", "enum": list(REFUSALS)},
            "follow_up": {"type": "boolean"},
        },
    }


@dataclass
class RoutedSpec:
    metric: str = None                 # a registry id, or None
    dimension: str = None
    category_text: str = None
    domains: tuple = ()
    period_phrase: str = None
    all_time: bool = False
    aggregation: str = "total"
    grain: str = None
    ambiguous_between: tuple = ()
    refusal: str = None
    follow_up: bool = False
    problems: list = field(default_factory=list)   # validation findings; a non-empty list never reaches execution
    notes: list = field(default_factory=list)      # observations that do not block (logged, never acted on)

    @property
    def valid(self):
        return not self.problems


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s\-]", " ", (text or "").lower())).strip()


def parse(data, question: str) -> RoutedSpec:
    """Validate the model's JSON against the closed vocabularies. Anything outside them is a problem, not a guess."""
    spec = RoutedSpec()
    if not isinstance(data, dict):
        spec.problems.append("not_an_object")
        return spec

    metric = data.get("metric")
    if metric == NONE:
        spec.metric = None
    elif metric in REGISTRY:
        spec.metric = metric
    else:
        spec.problems.append(f"unknown_metric:{metric!r}")

    dim = data.get("dimension", NONE)
    if dim not in DIMENSIONS:
        spec.problems.append(f"unknown_dimension:{dim!r}")
    elif dim != NONE:
        spec.dimension = dim
        if spec.metric and dim not in ALLOWED_DIMENSIONS.get(spec.metric, set()):
            if dim == "domain" and len(REGISTRY[spec.metric].domains) > 1:
                spec.dimension = None                       # a metric that spans several sections already reports one row per section
                spec.notes.append("dimension_domain_is_the_default_view")
            else:
                spec.problems.append(f"dimension_not_allowed:{spec.metric}/{dim}")

    doms = data.get("domains", [])
    if not isinstance(doms, list) or any(d not in DOMAINS for d in doms):
        spec.problems.append(f"bad_domains:{doms!r}")
    else:
        order = {d: i for i, d in enumerate(DOMAINS)}
        spec.domains = tuple(sorted(set(doms), key=order.get))

    spec.category_text = (data.get("category_text") or "").strip() or None
    spec.period_phrase = (data.get("period_phrase") or "").strip() or None
    spec.all_time = bool(data.get("all_time", False))
    spec.follow_up = bool(data.get("follow_up", False))

    agg = data.get("aggregation", "total")
    if agg not in AGGREGATIONS:
        spec.problems.append(f"unknown_aggregation:{agg!r}")
    else:
        spec.aggregation = agg
    grain = data.get("grain", NONE)
    if grain not in GRAINS:
        spec.problems.append(f"unknown_grain:{grain!r}")
    else:
        spec.grain = None if grain == NONE else grain

    amb = data.get("ambiguous_between", [])
    if not isinstance(amb, list) or any(a not in REGISTRY for a in amb):
        spec.problems.append(f"bad_ambiguous_between:{amb!r}")
    else:
        spec.ambiguous_between = tuple(dict.fromkeys(amb))
        if spec.ambiguous_between and len(spec.ambiguous_between) < 2:
            spec.problems.append("ambiguous_between_needs_two")

    ref = data.get("refusal", NONE)
    if ref not in REFUSALS:
        spec.problems.append(f"unknown_refusal:{ref!r}")
    else:
        spec.refusal = None if ref == NONE else ref

    if spec.metric is None and not spec.refusal and not spec.ambiguous_between:
        spec.refusal = "out_of_scope"                      # "none" with no reason is out of scope, not a problem
    if spec.metric and spec.refusal:
        spec.problems.append("metric_and_refusal")

    # The period phrase is only a second opinion: the resolver reads the period from the user's own words, and the cross-check asks
    # when a phrase appears where the resolver found none. A phrase the model tidied up (a typo fixed) is therefore harmless, but
    # it is recorded.
    if spec.period_phrase and _norm(spec.period_phrase) not in _norm(question):
        spec.notes.append(f"period_phrase_not_verbatim:{spec.period_phrase!r}")
    return spec
