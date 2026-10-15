"""The metric registry: one definition per metric, shared by chat and dashboard."""

from registry.core import REGISTRY, Coverage, Metric, Result, Scope, label  # noqa: F401
from registry import money, headcount, performance, operations  # noqa: F401  (registers the metrics)


def compute(metric_id: str, conn, scope: Scope = None) -> Result:
    """Run one metric. Unknown ids raise KeyError: the routing step can only name registry ids."""
    return REGISTRY[metric_id].compute(conn, scope or Scope())
