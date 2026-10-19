"""
Every registry metric is run with every dimension, aggregation and grain it declares (alone and combined), in every domain scope it
supports, and with every dimension the router's validator lets through. A combination that is declared (or allowed) but not supported
fails here, the way revenue with dimension 'domain' failed in the eval (case rv03) before it was seen anywhere else.
"""

import itertools

import pytest

from registry import REGISTRY, Scope, compute
from router.spec import ALLOWED_DIMENSIONS

OK_STATUSES = {"ok", "no_record", "not_available"}


def _cases():
    out = []
    for m in REGISTRY.values():
        dims = [None, *sorted(set(m.dimensions) | ALLOWED_DIMENSIONS[m.id])]
        aggs = list(dict.fromkeys(("total", *m.aggregations)))
        grains = [None, *m.grains]
        domain_scopes = [None, *[(d,) for d in m.domains]]
        for dim, agg, grain, doms in itertools.product(dims, aggs, grains, domain_scopes):
            out.append(pytest.param(m.id, dim, agg, grain, doms, id=f"{m.id}|dim={dim}|agg={agg}|grain={grain}|doms={doms}"))
    return out


@pytest.mark.parametrize("metric_id,dim,agg,grain,doms", _cases())
def test_every_declared_combination_computes(farm_db, metric_id, dim, agg, grain, doms):
    result = compute(metric_id, farm_db, Scope(domains=doms, dimension=dim, aggregation=agg, grain=grain))
    assert result.status in OK_STATUSES, (result.status, result.message)
    if result.status != "ok":
        assert result.message, "a result that is not ok must carry its sentence"


def test_the_validator_allows_nothing_the_registry_does_not_declare_except_the_default_domain_view():
    """ALLOWED_DIMENSIONS is built from the registry's own declarations; 'domain' is the only addition, for the two money metrics."""
    for m in REGISTRY.values():
        extra = ALLOWED_DIMENSIONS[m.id] - set(m.dimensions)
        assert extra <= {"domain"}, (m.id, extra)
        if extra:
            assert m.id in ("expenses", "revenue")


def test_the_combinations_cover_every_metric():
    assert {p.values[0] for p in _cases()} == set(REGISTRY)
