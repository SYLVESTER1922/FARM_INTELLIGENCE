"""
Gradio app for the Farm Intelligence platform: the existing Chat tab (thin
wrapper over chatbot.engine.answer_question - untouched by the dashboard
work below) plus four dashboard tabs (Herd & Flock Overview, Financials,
Findings & Alerts, Data Coverage) reading real data via ui/queries.py and
charting it via ui/charts.py.

Layout/styling pattern (hero header, sidebar-card CSS, gr.themes.Soft,
Plotly-in-gr.Plot) follows the Lobels Stores Intelligence reference app
(github.com/SYLVESTER1922/stores-intelligence-assistant), adapted with farm
branding and farm data - not copied verbatim.
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
# Chat tab - unchanged chat/answer-engine wiring
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
# Dashboard tabs - data + chart wiring
# ---------------------------------------------------------------------------
def _dashboard_conn():
    """A fresh connection for dashboard queries, same DSN/credential pattern
    handle_message already uses. Raises if the DSN is missing/unreachable -
    each load_* function below catches that and degrades to an empty state
    rather than crashing the whole page."""
    dsn = os.environ["FARM_INTELLIGENCE_DB_DSN"]
    return psycopg.connect(dsn, autocommit=True)


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


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
.gradio-container {
    font-family: 'Inter', 'Helvetica Neue', system-ui, sans-serif !important;
    width: 100% !important;
    max-width: 1500px !important;
    margin: 0 auto !important;
}
#farm-hero {
    background: linear-gradient(135deg, #2F6D3A 0%, #1F4A28 100%);
    border-radius: 16px;
    padding: 24px 32px;
    margin-bottom: 18px;
    color: white;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    box-shadow: 0 8px 24px rgba(47, 109, 58, 0.18);
    position: relative;
    overflow: hidden;
}
#farm-hero::after {
    content: "";
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, #C9A227 0%, #E4CC8E 50%, #C9A227 100%);
}
#farm-hero img.logo {
    height: 140px;
    width: auto;
    background: white;
    border-radius: 10px;
    padding: 10px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18);
    flex-shrink: 0;
    object-fit: contain;
}
#farm-hero .titles h1 {
    font-size: 1.8em !important;
    font-weight: 700 !important;
    margin: 0 0 4px 0 !important;
    color: white !important;
    letter-spacing: -0.5px;
}
#farm-hero .titles .brand-name {
    font-size: 0.82em;
    color: #C9A227;
    letter-spacing: 3px;
    font-weight: 600;
    margin-bottom: 6px;
    text-transform: uppercase;
}
#farm-hero .titles .tagline {
    font-size: 0.92em;
    color: #d7e5d9;
    margin: 0;
}
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


def build_interface() -> gr.Blocks:
    # Gradio 6 moved theme/css from the Blocks constructor to .launch() -
    # both are applied where this is actually launched (see __main__ below).
    # fill_width=True - Gradio 6 defaults Blocks to shrink-wrap its content
    # instead of filling the viewport, which was the main cause of the
    # cramped/overlapping chart layout (narrow ~490px container even at a
    # 1400px viewport width).
    with gr.Blocks(title="Farm Intelligence", fill_width=True) as demo:
        logo_data_uri = _logo_data_uri()
        logo_img_html = (
            f'<img class="logo" src="{logo_data_uri}" alt="Netrisyl Insights"/>'
            if logo_data_uri else ""
        )
        gr.HTML(f"""
        <div id="farm-hero">
            <div class="titles">
                <div class="brand-name">Farm Intelligence Platform</div>
                <h1>Chiedza Mixed Farm</h1>
                <p class="tagline">Piggery &middot; Poultry &middot; Crops &middot; Real-time farm data</p>
            </div>
            {logo_img_html}
        </div>
        """)

        with gr.Tabs():
            with gr.Tab("💬 Chat"):
                gr.ChatInterface(
                    fn=_chat_fn,
                    title=None,
                    description="Ask a question about your farm's piggery, poultry, or crops data.",
                )

            with gr.Tab("🐷 Herd & Flock Overview"):
                mortality_plot = gr.Plot(label="", show_label=False)
                fcr_plot = gr.Plot(label="", show_label=False)
                headcount_plot = gr.Plot(label="", show_label=False)

            with gr.Tab("💰 Financials"):
                trend_plot = gr.Plot(label="", show_label=False)
                feed_split_plot = gr.Plot(label="", show_label=False)
                gr.HTML('<div class="sidebar-card"><h3>Outstanding Payments</h3></div>')
                debtors_table = gr.Dataframe(
                    headers=["Date", "Domain", "Product", "Buyer",
                             "Amount (USD)", "Batch Ref"],
                    label="", show_label=False,
                )

            with gr.Tab("🚨 Findings & Alerts"):
                findings_html = gr.HTML()

            with gr.Tab("📋 Data Coverage"):
                with gr.Row():
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["sidebar-card"]):
                            coverage_info = gr.Markdown("Loading data coverage...")
                    with gr.Column(scale=2):
                        coverage_plot = gr.Plot(label="", show_label=False)

        demo.load(load_herd_flock, outputs=[mortality_plot, fcr_plot, headcount_plot])
        demo.load(load_financials, outputs=[trend_plot, feed_split_plot, debtors_table])
        demo.load(load_findings, outputs=[findings_html])
        demo.load(load_data_coverage, outputs=[coverage_info, coverage_plot])

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
