"""
Field tracking, for the completeness test (plan D5: "a unit test that fails if any result field is not rendered").
Templates read a result's figures and rows through these wrappers; each read is recorded. The test then compares what
was read against every key the result holds, so a field a template silently ignores is caught.
"""

# A key whose value is shown through another key counts as rendered when that one is: the domain CODE through its
# human LABEL, a month's first day through its "YYYY-MM" label.
ALIASES = {"domain": "label", "month_start": "month"}


class Tracked(dict):
    def __init__(self, data, sink):
        super().__init__(data)
        self._sink = sink

    def __getitem__(self, key):
        self._sink.add(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._sink.add(key)
        return super().get(key, default)


class Touch:
    """Collects the keys read from figures and from rows, and which rows were read at all."""

    def __init__(self):
        self.figure_keys, self.row_keys, self.rows_seen = set(), set(), 0

    def figures(self, data):
        return Tracked(data, self.figure_keys)

    def rows(self, rows):
        out = []
        for r in rows:
            self.rows_seen += 1
            out.append(Tracked(r, self.row_keys))
        return out

    def unrendered(self, result):
        """Keys the result holds that no template read (aliases resolved), as (where, key) pairs."""
        missing = []
        for k in result.figures:
            if k not in self.figure_keys:
                missing.append(("figures", k))
        row_keys = {k for r in result.rows for k in r}
        for k in row_keys:
            if k not in self.row_keys and ALIASES.get(k) not in self.row_keys:
                missing.append(("rows", k))
        if self.rows_seen < len(result.rows):
            missing.append(("rows", f"{len(result.rows) - self.rows_seen} row(s) never rendered"))
        return missing


def rendered_by_note(result, fig, *keys):
    """A figure whose value is stated by one of the result's own notes (the mortality denominator, the days behind a weekly
    average) is read here instead of being printed twice. Strict: the value must really appear in a note, or this raises,
    so a field can never be marked rendered without being shown."""
    from render.format import num
    text = " ".join(result.notes)
    for key in keys:
        value = fig[key]                                   # also records the read
        shown = [num(value), num(value, 1), num(value, 2), str(value)]
        if not any(sh in text for sh in shown):
            raise AssertionError(f"{result.metric_id}: {key}={value!r} is not stated in the result's notes")
