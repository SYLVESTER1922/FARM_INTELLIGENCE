# 02: Expand the catalog to the three planted findings

**What to build:** A farm owner can ask about the poultry mortality spike, the piggery
disease outbreak, or the unpaid crop sale, in plain language, and get a correct answer for
each — proving the pattern from ticket 01 generalizes to a multi-entry catalog, including
the case where two clusters could plausibly both match a question.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Three more catalog entries added: poultry mortality spike (`BRO-P02`), piggery
      disease outbreak (`PIG-B02`), crop debtor (`SB-PL2-25A`) — each with a declared
      `query_id`, required parameters, and a curated phrase cluster.
- [ ] Each of the three is answerable end-to-end via the tier-1 matcher alone, with
      correct phrasing and correct `query_log` rows (`intent_source=deterministic`,
      correct `query_id`).
- [ ] A question deliberately crafted to plausibly match two clusters at once (e.g.
      overlapping vocabulary between two of the now-four catalog entries) logs
      `intent_source=unresolved`, `failure_reason=ambiguous`, `query_id` null — and the
      system does not guess between the two candidates.
- [ ] All of ticket 01's acceptance criteria still pass against the now-four-entry
      catalog (no regression in the single-match or no-match cases).
