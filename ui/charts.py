"""
Plotly figure builders for the dashboard tabs. Consumes the plain data
structures ui/queries.py returns - every number here was already computed
by SQL; nothing in this module does arithmetic beyond simple unit/percent
conversions for display.

Styling pattern (color palette, _layout/_empty_fig/_safe helpers) follows
the Lobels Stores Intelligence reference app
(github.com/SYLVESTER1922/stores-intelligence-assistant), adapted with
farm-appropriate branding rather than copied verbatim.
"""

import plotly.graph_objects as go

C_GREEN = "#2F6D3A"    # piggery
C_GOLD = "#C9A227"     # poultry
C_RED = "#B23A2E"      # alerts / losses
C_BLUE = "#3A6EA5"     # crops / revenue
C_NAVY = "#1B2A4E"
C_CREAM = "#F7F4EC"

PLOTLY_LAYOUT = dict(
    font=dict(family="Inter, Arial", size=12),
    plot_bgcolor="white",
    paper_bgcolor="white",
)


def _layout(height=380, margin=None, **extra):
    m = margin or dict(l=50, r=20, t=50, b=40)
    return dict(**PLOTLY_LAYOUT, height=height, margin=m, **extra)


def empty_fig(msg="No data available"):
    """Public - used by ui/app.py's load_* functions when a query itself
    raises (before any chart-building function gets a chance to)."""
    fig = go.Figure()
    fig.add_annotation(text=msg, xref="paper", yref="paper",
                        x=0.5, y=0.5, showarrow=False,
                        font=dict(size=15, color="#999"))
    fig.update_layout(**_layout())
    return fig


def _safe(fn):
    """Chart-building functions never raise into the UI - any failure
    (missing data, a query error) renders as an empty-state figure with the
    error message, mirroring the Lobels reference app's _safe decorator."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            print(f"Chart error [{fn.__name__}]: {e}")
            return empty_fig(f"Could not load chart: {str(e)[:150]}")
    return wrapper


def _month_label(d):
    return d.strftime("%b %Y")


@_safe
def mortality_chart(data):
    """data: {'piggery': [(month, deaths)], 'poultry': [(month, deaths)]}"""
    pig_months = [_month_label(m) for m, _ in data["piggery"]]
    pig_deaths = [d for _, d in data["piggery"]]
    poultry_months = [_month_label(m) for m, _ in data["poultry"]]
    poultry_deaths = [d for _, d in data["poultry"]]

    all_months = sorted(
        set(m for m, _ in data["piggery"]) | set(m for m, _ in data["poultry"])
    )
    labels = [_month_label(m) for m in all_months]
    pig_by_month = dict(zip(pig_months, pig_deaths))
    poultry_by_month = dict(zip(poultry_months, poultry_deaths))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=[pig_by_month.get(m, 0) for m in labels],
        name="Piggery", marker_color=C_GREEN))
    fig.add_trace(go.Bar(
        x=labels, y=[poultry_by_month.get(m, 0) for m in labels],
        name="Poultry", marker_color=C_GOLD))
    fig.update_layout(
        title="Mortality by Month (Deaths)",
        barmode="group", yaxis_title="Deaths",
        legend=dict(orientation="h", y=1.15),
        **_layout())
    return fig


@_safe
def fcr_chart(rows):
    """rows: [{'batch_code', 'domain', 'fcr'}, ...]"""
    if not rows:
        return empty_fig("No FCR data available.")
    rows = sorted(rows, key=lambda r: r["fcr"])
    names = [r["batch_code"] for r in rows]
    values = [float(r["fcr"]) for r in rows]
    colors = [C_GREEN if r["domain"] == "piggery" else C_GOLD for r in rows]
    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h", marker_color=colors,
        text=[f"{v:.2f}" for v in values], textposition="auto"))
    fig.update_layout(
        title="Feed Conversion Ratio by Batch (lower is better)",
        xaxis_title="FCR (kg feed / kg gain)",
        **_layout(height=max(320, 40 * len(rows)), margin=dict(l=90, r=20, t=50, b=40)))
    return fig


@_safe
def headcount_chart(data):
    """data: {'piggery': [(month, headcount)], 'poultry': [(month, headcount)]}"""
    fig = go.Figure()
    if data["piggery"]:
        fig.add_trace(go.Scatter(
            x=[_month_label(m) for m, _ in data["piggery"]],
            y=[h for _, h in data["piggery"]],
            name="Piggery", mode="lines+markers", line=dict(color=C_GREEN, width=3)))
    if data["poultry"]:
        fig.add_trace(go.Scatter(
            x=[_month_label(m) for m, _ in data["poultry"]],
            y=[h for _, h in data["poultry"]],
            name="Poultry", mode="lines+markers", line=dict(color=C_GOLD, width=3),
            yaxis="y2"))
    fig.update_layout(
        title="Headcount Trend by Month",
        yaxis=dict(title="Piggery headcount"),
        yaxis2=dict(title="Poultry headcount", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.15),
        **_layout())
    return fig


@_safe
def expenses_vs_revenue_chart(data):
    """data: {'expenses': [(month, total)], 'revenue': [(month, total)]}"""
    all_months = sorted(
        set(m for m, _ in data["expenses"]) | set(m for m, _ in data["revenue"])
    )
    labels = [_month_label(m) for m in all_months]
    exp_by_month = {_month_label(m): float(v) for m, v in data["expenses"]}
    rev_by_month = {_month_label(m): float(v) for m, v in data["revenue"]}

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=[exp_by_month.get(m, 0) for m in labels],
        name="Expenses", marker_color=C_RED))
    fig.add_trace(go.Bar(
        x=labels, y=[rev_by_month.get(m, 0) for m in labels],
        name="Revenue", marker_color=C_BLUE))
    fig.update_layout(
        title="Expenses vs Revenue by Month (USD)",
        barmode="group", yaxis_title="USD",
        legend=dict(orientation="h", y=1.15),
        **_layout())
    return fig


@_safe
def feed_cost_by_domain_chart(rows):
    """rows: [{'domain', 'total_kg', 'feed_cost'}, ...]"""
    if not rows:
        return empty_fig("No feed cost data available.")
    names = [r["domain"].capitalize() for r in rows]
    values = [float(r["feed_cost"]) for r in rows]
    colors = [C_GREEN if r["domain"] == "piggery" else C_GOLD for r in rows]
    fig = go.Figure(go.Bar(
        x=names, y=values, marker_color=colors,
        text=[f"${v:,.2f}" for v in values], textposition="outside"))
    fig.update_layout(
        title="Feed Cost by Domain (Full Period, USD)",
        yaxis_title="Feed Cost (USD)",
        **_layout())
    return fig


@_safe
def data_coverage_chart(counts):
    """counts: {'piggery_batches': n, 'poultry_batches': n, 'plantings': n}"""
    labels = ["Piggery Batches", "Poultry Batches", "Crop Plantings"]
    values = [counts["piggery_batches"], counts["poultry_batches"], counts["plantings"]]
    colors = [C_GREEN, C_GOLD, C_BLUE]
    fig = go.Figure(go.Bar(
        x=labels, y=values, marker_color=colors,
        text=values, textposition="outside"))
    fig.update_layout(title="Records by Domain", yaxis_title="Count", **_layout())
    return fig
