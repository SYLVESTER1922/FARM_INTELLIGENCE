"""
Case type for the eval set. Every case carries a `split`. The harness runs
`dev` only; a `locked` case is refused unless --include-locked is passed, and
nothing may be marked `locked` until Sylvester and Tadiwanashe Dzimbanete have
reviewed it (spec-chatbot-v2-plan.md, section 11).
"""

from dataclasses import dataclass, field

ZERO_TOLERANCE_GROUPS = {"money", "headcount"}


@dataclass
class Case:
    id: str
    question: str
    kind: str                      # answer | refuse | clarify
    oracle: tuple                  # (oracle method name, kwargs)
    group: str                     # headcount | money | perf | ops | refusal | clarify | scope | noisy
    fair: str = "v1"               # v1: a v1-style engine could answer it correctly
                                   # v2_only: expected behaviour depends on a v2 decision
    source: str = "draft"          # live | draft
    filter: tuple = None           # (date_from, date_to): the dashboard filter in effect
    zt: bool = None                # zero-tolerance (money / headcount); default from group
    denial_topics: tuple = ()      # answerable cases: words that name the asked-about data;
                                   # a refusal that explicitly denies tracking one is a false claim
    split: str = "dev"
    review: str = ""               # what the reviewer should check about this case

    def __post_init__(self):
        if self.zt is None:
            self.zt = self.group in ZERO_TOLERANCE_GROUPS
        if self.split not in ("dev", "locked"):
            raise ValueError(f"{self.id}: bad split {self.split!r}")
