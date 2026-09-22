"""
Gradio app for the Farm Intelligence platform: a fixed-width left sidebar
nav (Dashboard, Chat, Herd & Flock, Feeding, Health, Breeding, Finance,
Reports, Settings) over a single-page content area, each nav item toggling
a gr.Column "page" rather than using gr.Tabs. The Chat page's wiring
(handle_message/_chat_fn) is untouched from the original tab-based layout.

Layout pattern (sidebar nav + stat cards + chart grid) follows a supplied
dashboard mockup reference; the underlying chart-type decisions (line for
trends, donut for share-of-total, bar for comparisons) and the Lobels
Stores Intelligence reference app's Plotly/CSS conventions carry over from
the earlier dashboard work.
"""

import base64
import os

import gradio as gr
import psycopg

from chatbot.engine import answer_question
from ui import charts, queries

FARM_CODE = "NIS-001"  # single real farm today; multi-farm UI is deferred
GENERIC_ERROR_MESSAGE = "Something went wrong - please try again."

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "netrisyl-logo.png")


def _logo_data_uri() -> str:
    """Base64-embedded inline, not a linked external file - so the logo
    always renders regardless of hosting/static-file setup, the same
    pattern used by the Savanna QSR app. Returns "" if the asset is
    missing, so a missing logo degrades to no image rather than a broken
    page."""
    if not os.path.exists(_LOGO_PATH):
        return ""
    with open(_LOGO_PATH, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# ---------------------------------------------------------------------------
# Chat page - unchanged chat/answer-engine wiring
# ---------------------------------------------------------------------------
def handle_message(question: str) -> str:
    try:
        dsn = os.environ["FARM_INTELLIGENCE_DB_DSN"]
        answer = answer_question(question, farm_code=FARM_CODE, dsn=dsn)
    except Exception:
        return GENERIC_ERROR_MESSAGE
    return answer.text


def _chat_fn(message: str, history: list) -> str:
    # `history` is Gradio's own display state (past exchanges) - it is
    # deliberately never passed into handle_message/answer_question, per
    # the backend's no-multi-turn design (spec-chatbot-ui.md).
    return handle_message(message)


# ---------------------------------------------------------------------------
# Data + chart wiring, shared by every page
# ---------------------------------------------------------------------------
def _dashboard_conn():
    """A fresh connection for dashboard queries, same DSN/credential pattern
    handle_message already uses. Raises if the DSN is missing/unreachable -
    each load_* function below catches that and degrades to an empty state
    rather than crashing the whole page."""
    dsn = os.environ["FARM_INTELLIGENCE_DB_DSN"]
    return psycopg.connect(dsn, autocommit=True)


def _stat_card_html(card):
    # A cumulative/lifetime total (e.g. Piglets Born) has no meaningful
    # "vs 30 days ago" percentage - it carries a neutral "caption" instead
    # of "pct_change", rendered without an up/down arrow.
    if "caption" in card:
        change_html = f'<span class="stat-change stat-flat">{card["caption"]}</span>'
    else:
        pct = card["pct_change"]
        if pct is None:
            change_html = '<span class="stat-change stat-flat">— no prior-period baseline</span>'
        else:
            cls = "stat-up" if pct >= 0 else "stat-down"
            arrow = "▲" if pct >= 0 else "▼"
            change_html = f'<span class="stat-change {cls}">{arrow} {abs(pct)}% vs 30 days ago</span>'
    return (
        f'<div class="stat-card">'
        f'<div class="stat-icon">{card["icon"]}</div>'
        f'<div class="stat-body">'
        f'<div class="stat-value">{card["value"]}</div>'
        f'<div class="stat-label">{card["label"]}</div>'
        f'{change_html}'
        f'</div>'
        f'</div>'
    )


def load_dashboard_stats():
    try:
        conn = _dashboard_conn()
        cards = queries.fetch_dashboard_stats(conn)
    except Exception as e:
        return f'<div class="stat-card">Could not load stats: {str(e)[:150]}</div>'
    return '<div class="stat-cards-row">' + "".join(_stat_card_html(c) for c in cards) + '</div>'


def load_dashboard_charts():
    try:
        conn = _dashboard_conn()
        herd_growth = charts.headcount_chart(queries.fetch_headcount_by_month(conn))
        fcr = charts.fcr_chart(queries.fetch_fcr_by_batch(conn))
        cost_vs_revenue = charts.expenses_vs_revenue_chart(queries.fetch_expenses_vs_revenue(conn))
        expense_breakdown = charts.expense_breakdown_chart(queries.fetch_expense_breakdown(conn))
        return herd_growth, fcr, cost_vs_revenue, expense_breakdown
    except Exception as e:
        empty = charts.empty_fig(f"Could not load: {str(e)[:150]}")
        return empty, empty, empty, empty


def load_herd_flock():
    try:
        conn = _dashboard_conn()
        mortality = charts.mortality_chart(queries.fetch_mortality_by_month(conn))
        fcr = charts.fcr_chart(queries.fetch_fcr_by_batch(conn))
        headcount = charts.headcount_chart(queries.fetch_headcount_by_month(conn))
        return mortality, fcr, headcount
    except Exception as e:
        empty = charts.empty_fig(f"Could not load: {str(e)[:150]}")
        return empty, empty, empty


def load_financials():
    try:
        conn = _dashboard_conn()
        trend = charts.expenses_vs_revenue_chart(queries.fetch_expenses_vs_revenue(conn))
        feed_split = charts.feed_cost_by_domain_chart(queries.fetch_feed_cost_by_domain(conn))
        debtors = queries.fetch_debtors(conn)
        rows = [[r["date"].isoformat(), r["domain"], r["product"], r["buyer"],
                  float(r["total_amount"]), r["batch_ref"]] for r in debtors]
        return trend, feed_split, rows
    except Exception as e:
        empty = charts.empty_fig(f"Could not load: {str(e)[:150]}")
        return empty, empty, []


def _finding_card(title, body, icon="⚠️"):
    return (
        f'<div class="finding-card">'
        f'<div class="finding-title">{icon} {title}</div>'
        f'<div class="finding-body">{body}</div>'
        f'</div>'
    )


def load_findings():
    try:
        conn = _dashboard_conn()
        f = queries.fetch_findings(conn)
    except Exception as e:
        msg = f"Could not load findings: {str(e)[:150]}"
        return f'<div class="finding-card">{msg}</div>' * 3

    poultry = f["poultry_mortality_spike"]
    piggery = f["piggery_disease_outbreak"]
    debtor = f["crop_debtor"]

    poultry_card = _finding_card(
        "Poultry Mortality Spike",
        (f"Batch <b>{poultry['batch_code']}</b> has a "
         f"<b>{poultry['mortality_pct']}%</b> mortality rate - the highest of "
         f"any poultry batch this period.")
        if poultry else "No poultry mortality data available.",
        icon="🐔",
    )
    piggery_card = _finding_card(
        "Piggery Disease Outbreak",
        (f"Batch <b>{piggery['batch_ref']}</b> has had "
         f"<b>{piggery['treatment_count']}</b> treatments, "
         f"totalling <b>${float(piggery['total_vet_cost']):.2f}</b> in vet costs.")
        if piggery else "No piggery health data available.",
        icon="🐖",
    )
    debtor_card = _finding_card(
        "Unpaid Crop Debtor",
        (f"<b>{debtor['buyer']}</b> owes <b>${float(debtor['total_amount']):.2f}</b> "
         f"for {debtor['product']} (batch {debtor['batch_ref']}).")
        if debtor else "No outstanding crop payments.",
        icon="🌾",
    )
    return poultry_card + piggery_card + debtor_card


def load_data_coverage():
    try:
        conn = _dashboard_conn()
        data = queries.fetch_data_coverage(conn)
    except Exception as e:
        return f"Could not load data coverage: {str(e)[:150]}", charts.empty_fig()

    c = data["counts"]
    info = (
        f"### Data Summary\n\n"
        f"**Records span:** {data['earliest_date']} to {data['latest_date']}\n\n"
        f"**Piggery batches:** {c['piggery_batches']}\n\n"
        f"**Poultry batches:** {c['poultry_batches']}\n\n"
        f"**Crop plantings:** {c['plantings']}\n\n"
        f"**Latest record date:** {data['latest_date']}\n\n"
        f"---\n*The sync is an idempotent reload with no write-timestamp log, "
        f"so \"latest record date\" (the newest real farm-data entry across "
        f"all domains) is the freshness indicator, not a separate sync-run "
        f"timestamp.*"
    )
    fig = charts.data_coverage_chart(c)
    return info, fig


def load_feeding():
    try:
        conn = _dashboard_conn()
        return charts.feed_cost_trend_chart(queries.fetch_feed_cost_by_month(conn))
    except Exception as e:
        return charts.empty_fig(f"Could not load: {str(e)[:150]}")


def load_health():
    try:
        conn = _dashboard_conn()
        chart = charts.health_cost_chart(queries.fetch_health_summary(conn))
        events = queries.fetch_recent_health_events(conn)
        rows = [[r["date"].isoformat(), r["domain"], r["batch_ref"], r["event_type"],
                  r["diagnosis"] or "-", float(r["cost"] or 0)] for r in events]
        return chart, rows
    except Exception as e:
        return charts.empty_fig(f"Could not load: {str(e)[:150]}"), []


def load_breeding():
    try:
        conn = _dashboard_conn()
        summary = queries.fetch_breeding_summary(conn)
    except Exception as e:
        return f"Could not load breeding data: {str(e)[:150]}", []

    info = (
        f"### Breeding Summary\n\n"
        f"**Completed litters:** {summary['total_litters']}\n\n"
        f"**Total piglets born alive:** {summary['total_born_alive']}\n\n"
        f"**Total weaned:** {summary['total_weaned']}"
    )
    rows = [
        [r["sow_tag"],
         r["service_date"].isoformat() if r["service_date"] else "-",
         r["farrow_date"].isoformat() if r["farrow_date"] else "Pending",
         r["born_alive"] if r["born_alive"] is not None else "-",
         r["stillborn"] if r["stillborn"] is not None else "-",
         r["weaned_count"] if r["weaned_count"] is not None else "-"]
        for r in summary["records"]
    ]
    return info, rows


def load_settings():
    try:
        conn = _dashboard_conn()
        profile = queries.fetch_farm_profile(conn)
    except Exception as e:
        return f"Could not load farm profile: {str(e)[:150]}"

    if not profile:
        return "No farm profile configured."

    modules = [name for name, active in (
        ("Piggery", profile["module_piggery_active"]),
        ("Poultry", profile["module_poultry_active"]),
        ("Crops", profile["module_crops_active"]),
    ) if active]

    return (
        f"### Farm Configuration\n\n"
        f"**Farm code:** {profile['farm_code']}\n\n"
        f"**Farm name:** {profile['farm_name']}\n\n"
        f"**Region:** {profile['region_district']}\n\n"
        f"**Currency:** {profile['currency']}\n\n"
        f"**Total area:** {profile['total_hectares']} ha\n\n"
        f"**Financial year start:** {profile['financial_year_start']}\n\n"
        f"**Active modules:** {', '.join(modules) if modules else 'None'}\n\n"
        f"---\n*This is a read-only view of the farm's configuration - there "
        f"is no editable settings system in this demo.*"
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
.gradio-container {
    font-family: 'Inter', 'Helvetica Neue', system-ui, sans-serif !important;
    width: 100% !important;
    max-width: 1600px !important;
    margin: 0 auto !important;
}
#slim-header {
    background: linear-gradient(90deg, #ffffff 0%, #eaf2ec 50%, #ffffff 100%);
    border-radius: 12px;
    border: 1px solid #e5e7eb;
    padding: 30px 36px;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 28px;
    position: relative;
    overflow: hidden;
}
/* A thin accent bar anchors the bar as one cohesive surface rather than
"two corners with dead space between" - same accent-gradient treatment
the original full-height hero header used. */
#slim-header::after {
    content: "";
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #2F6D3A 0%, #C9A227 50%, #2F6D3A 100%);
}
/* Only the logo itself gets bigger here (lengthwise, via height with the
source image's fixed ~1.78:1 aspect ratio auto-widening it) - the header
bar's own padding stays modest so the bar doesn't balloon along with it. */
#slim-header img.logo {
    height: 190px;
    width: auto;
    object-fit: contain;
    flex-shrink: 0;
}
#slim-header .brand-text {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    flex: 1 1 auto;
    max-width: 760px;
}
/* Hierarchy: the eyebrow label is now the dominant line (biggest, bold,
the gold/olive accent already used elsewhere), the farm name is the
medium second line, the domain tags are the smallest third line - and
the larger, wider-tracked type on line 1 is what actually carries the
block further right toward the logo, not a layout trick. */
#slim-header .brand-name {
    font-size: 2.1em;
    color: #C9A227;
    letter-spacing: 4px;
    font-weight: 800;
    text-transform: uppercase;
    line-height: 1.15;
    margin-bottom: 10px;
}
#slim-header .farm-name {
    font-size: 1.5em;
    color: #1B2A4E;
    font-weight: 700;
    line-height: 1.1;
    letter-spacing: -0.3px;
    margin-bottom: 10px;
}
#slim-header .domain-tags {
    display: flex;
    gap: 22px;
    font-size: 0.88em;
    color: #4b5563;
    font-weight: 500;
}
#sidebar-nav {
    background: linear-gradient(180deg, #14261A 0%, #1B3B25 100%);
    border-radius: 12px;
    padding: 28px 0 !important;
    min-width: 200px !important;
    max-width: 200px !important;
    align-self: stretch !important;
    justify-content: space-evenly !important;
}
/* "nav-btn" is a class on the <button> itself (Gradio's elem_classes
applies directly to the component), not a wrapper around one - an earlier
".nav-btn button" descendant-selector version of this never matched, which
is why each button kept Gradio's default white/boxed styling and the
column's default flex gap read as dark gaps between white pills. */
button.nav-btn {
    background: transparent !important;
    color: #cfe0d3 !important;
    border: none !important;
    box-shadow: none !important;
    text-align: left !important;
    justify-content: flex-start !important;
    padding: 13px 22px !important;
    font-size: 0.92em !important;
    font-weight: 500 !important;
    border-radius: 0 !important;
    border-left: 3px solid transparent !important;
    width: 100% !important;
    margin: 0 !important;
}
button.nav-btn:hover {
    background: rgba(255, 255, 255, 0.08) !important;
    color: white !important;
}
button.nav-btn-active {
    background: rgba(201, 162, 39, 0.18) !important;
    color: white !important;
    border-left: 3px solid #C9A227 !important;
    font-weight: 700 !important;
}
.stat-cards-row {
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    margin-bottom: 18px;
}
.stat-card {
    flex: 1 1 220px;
    background: white;
    border-radius: 12px;
    border: 1px solid #e5e7eb;
    padding: 16px 18px;
    display: flex;
    align-items: flex-start;
    gap: 12px;
}
.stat-icon {
    font-size: 1.8em;
    line-height: 1;
}
.stat-body { display: flex; flex-direction: column; }
.stat-value {
    font-size: 1.5em;
    font-weight: 800;
    color: #1B2A4E;
    line-height: 1.1;
}
.stat-label {
    font-size: 0.78em;
    color: #6b7280;
    margin-top: 2px;
}
.stat-change {
    font-size: 0.75em;
    font-weight: 700;
    margin-top: 5px;
}
.stat-up { color: #2F6D3A; }
.stat-down { color: #B23A2E; }
.stat-flat { color: #9ca3af; font-weight: 500; }
.sidebar-card {
    background: white;
    border-radius: 12px;
    padding: 16px;
    border: 1px solid #e5e7eb;
    margin-bottom: 12px;
}
.sidebar-card h3 {
    color: #2F6D3A;
    font-size: 0.78em;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin: 0 0 12px 0;
    font-weight: 700;
    border-left: 3px solid #C9A227;
    padding-left: 10px;
}
.finding-card {
    background: #fff9ec;
    border: 1px solid #e8dfc7;
    border-left: 4px solid #B23A2E;
    border-radius: 10px;
    padding: 16px 18px;
    margin-bottom: 14px;
}
.finding-title {
    font-weight: 700;
    color: #1B2A4E;
    margin-bottom: 6px;
    font-size: 1.02em;
}
.finding-body {
    color: #333;
    font-size: 0.95em;
    line-height: 1.5;
}
footer { display: none !important; }
"""

theme = gr.themes.Soft(
    primary_hue=gr.themes.colors.green,
    secondary_hue=gr.themes.colors.amber,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
).set(
    button_primary_background_fill="#2F6D3A",
    button_primary_background_fill_hover="#1F4A28",
    button_primary_text_color="white",
    body_background_fill="#F7F4EC",
    block_background_fill="white",
    block_border_color="#e5e7eb",
)

# (id, icon, label) - order fixed here and reused for both the sidebar
# buttons and the page columns they toggle. "Dashboard" is the landing
# page; "Chat" sits second, kept prominent per the redesign brief ("keep
# Chat accessible - first sidebar item or a floating button, your call").
NAV_ITEMS = [
    ("dashboard", "🏠", "Dashboard"),
    ("chat", "💬", "Chat"),
    ("herd", "🐷", "Herd & Flock"),
    ("feeding", "🧺", "Feeding"),
    ("health", "🏥", "Health"),
    ("breeding", "🍼", "Breeding"),
    ("finance", "💰", "Finance"),
    ("reports", "📊", "Reports"),
    ("settings", "⚙️", "Settings"),
]


def _make_nav_click(index, count):
    def _fn():
        page_updates = [gr.update(visible=(i == index)) for i in range(count)]
        btn_updates = [
            gr.update(elem_classes=["nav-btn", "nav-btn-active"] if i == index else ["nav-btn"])
            for i in range(count)
        ]
        return page_updates + btn_updates
    return _fn


def build_interface() -> gr.Blocks:
    # Gradio 6 moved theme/css from the Blocks constructor to .launch() -
    # both are applied where this is actually launched (see __main__ below).
    # fill_width=True - Gradio 6 defaults Blocks to shrink-wrap its content
    # instead of filling the viewport (root cause of an earlier layout bug).
    with gr.Blocks(title="Farm Intelligence", fill_width=True) as demo:
        logo_data_uri = _logo_data_uri()
        logo_img_html = (
            f'<img class="logo" src="{logo_data_uri}" alt="Netrisyl Insights"/>'
            if logo_data_uri else ""
        )
        gr.HTML(f"""
        <div id="slim-header">
            <div class="brand-text">
                <div class="brand-name">Farm Intelligence Platform</div>
                <div class="farm-name">Chiedza Mixed Farm</div>
                <div class="domain-tags">
                    <span>🐷 Piggery</span><span>🐔 Poultry</span><span>🌾 Crops</span>
                </div>
            </div>
            {logo_img_html}
        </div>
        """)

        nav_buttons = []
        pages = []

        with gr.Row():
            with gr.Column(scale=0, elem_id="sidebar-nav"):
                for i, (_id, icon, label) in enumerate(NAV_ITEMS):
                    classes = ["nav-btn", "nav-btn-active"] if i == 0 else ["nav-btn"]
                    nav_buttons.append(
                        gr.Button(f"{icon}  {label}", elem_classes=classes)
                    )

            with gr.Column(scale=1):
                # ---- Dashboard (landing page) ----------------------------
                with gr.Column(visible=True) as page_dashboard:
                    dashboard_stats_html = gr.HTML()
                    # Financial charts lead, operational charts follow.
                    with gr.Row():
                        cost_revenue_plot = gr.Plot(label="", show_label=False)
                        expense_breakdown_plot = gr.Plot(label="", show_label=False)
                    with gr.Row():
                        herd_growth_plot = gr.Plot(label="", show_label=False)
                        dash_fcr_plot = gr.Plot(label="", show_label=False)
                pages.append(page_dashboard)

                # ---- Chat --------------------------------------------------
                with gr.Column(visible=False) as page_chat:
                    gr.ChatInterface(
                        fn=_chat_fn,
                        title=None,
                        description="Ask a question about your farm's piggery, poultry, or crops data.",
                    )
                pages.append(page_chat)

                # ---- Herd & Flock -------------------------------------------
                with gr.Column(visible=False) as page_herd:
                    mortality_plot = gr.Plot(label="", show_label=False)
                    fcr_plot = gr.Plot(label="", show_label=False)
                    headcount_plot = gr.Plot(label="", show_label=False)
                pages.append(page_herd)

                # ---- Feeding -------------------------------------------------
                with gr.Column(visible=False) as page_feeding:
                    feeding_plot = gr.Plot(label="", show_label=False)
                pages.append(page_feeding)

                # ---- Health --------------------------------------------------
                with gr.Column(visible=False) as page_health:
                    health_plot = gr.Plot(label="", show_label=False)
                    gr.HTML('<div class="sidebar-card"><h3>Recent Health Events</h3></div>')
                    health_events_table = gr.Dataframe(
                        headers=["Date", "Domain", "Batch Ref", "Event Type",
                                 "Diagnosis", "Cost (USD)"],
                        label="", show_label=False,
                    )
                pages.append(page_health)

                # ---- Breeding ------------------------------------------------
                with gr.Column(visible=False) as page_breeding:
                    with gr.Row():
                        with gr.Column(scale=1):
                            with gr.Group(elem_classes=["sidebar-card"]):
                                breeding_info = gr.Markdown("Loading breeding data...")
                        with gr.Column(scale=2):
                            gr.HTML('<div class="sidebar-card"><h3>Farrowing Records</h3></div>')
                            breeding_table = gr.Dataframe(
                                headers=["Sow Tag", "Service Date", "Farrow Date",
                                         "Born Alive", "Stillborn", "Weaned"],
                                label="", show_label=False,
                            )
                pages.append(page_breeding)

                # ---- Finance -------------------------------------------------
                with gr.Column(visible=False) as page_finance:
                    trend_plot = gr.Plot(label="", show_label=False)
                    feed_split_plot = gr.Plot(label="", show_label=False)
                    gr.HTML('<div class="sidebar-card"><h3>Outstanding Payments</h3></div>')
                    debtors_table = gr.Dataframe(
                        headers=["Date", "Domain", "Product", "Buyer",
                                 "Amount (USD)", "Batch Ref"],
                        label="", show_label=False,
                    )
                pages.append(page_finance)

                # ---- Reports (Findings & Alerts + Data Coverage) -------------
                with gr.Column(visible=False) as page_reports:
                    gr.HTML('<div class="sidebar-card"><h3>Findings &amp; Alerts</h3></div>')
                    findings_html = gr.HTML()
                    gr.HTML('<div class="sidebar-card"><h3>Data Coverage</h3></div>')
                    with gr.Row():
                        with gr.Column(scale=1):
                            with gr.Group(elem_classes=["sidebar-card"]):
                                coverage_info = gr.Markdown("Loading data coverage...")
                        with gr.Column(scale=2):
                            coverage_plot = gr.Plot(label="", show_label=False)
                pages.append(page_reports)

                # ---- Settings ------------------------------------------------
                with gr.Column(visible=False) as page_settings:
                    with gr.Group(elem_classes=["sidebar-card"]):
                        settings_info = gr.Markdown("Loading farm configuration...")
                pages.append(page_settings)

        for i, btn in enumerate(nav_buttons):
            btn.click(_make_nav_click(i, len(NAV_ITEMS)), outputs=pages + nav_buttons)

        demo.load(load_dashboard_stats, outputs=[dashboard_stats_html])
        demo.load(load_dashboard_charts,
                  outputs=[herd_growth_plot, dash_fcr_plot, cost_revenue_plot,
                           expense_breakdown_plot])
        demo.load(load_herd_flock, outputs=[mortality_plot, fcr_plot, headcount_plot])
        demo.load(load_financials, outputs=[trend_plot, feed_split_plot, debtors_table])
        demo.load(load_findings, outputs=[findings_html])
        demo.load(load_data_coverage, outputs=[coverage_info, coverage_plot])
        demo.load(load_feeding, outputs=[feeding_plot])
        demo.load(load_health, outputs=[health_plot, health_events_table])
        demo.load(load_breeding, outputs=[breeding_info, breeding_table])
        demo.load(load_settings, outputs=[settings_info])

    return demo


def _load_local_dev_credentials() -> None:
    """Only for running this app directly on a dev machine (python
    ui/app.py) - never invoked when this module is imported under test or
    deployed to the live Render service (there, both env vars are provided
    by Render's environment variable settings already). Loads what's
    missing from the same local credential files the rest of this project
    already uses, so `python -m ui.app` works without the developer having
    to export anything by hand first."""
    if "OPENAI_API_KEY" not in os.environ:
        key_path = os.path.expanduser("~/.openai_api_key")
        if os.path.exists(key_path):
            with open(key_path) as f:
                os.environ["OPENAI_API_KEY"] = f.read().strip()

    if "FARM_INTELLIGENCE_DB_DSN" not in os.environ:
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env.supabase")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("SUPABASE_DB_DSN="):
                        os.environ["FARM_INTELLIGENCE_DB_DSN"] = line.strip().split("=", 1)[1]
                        break


if __name__ == "__main__":
    _load_local_dev_credentials()
    # Render (and similar PaaS hosts) assign the listen port via $PORT and
    # require binding all interfaces; local dev falls back to Gradio's
    # usual default port with the same 0.0.0.0 bind.
    build_interface().launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        theme=theme,
        css=CUSTOM_CSS,
    )
