"""The scope resolver: raw words + dashboard filter + farm profile -> a typed Scope, in code, never by an LLM."""

from resolver.periods import FARM_TZ, harare_today  # noqa: F401
from resolver.resolve import Resolution, Unresolved, all_time_scope, resolve  # noqa: F401
