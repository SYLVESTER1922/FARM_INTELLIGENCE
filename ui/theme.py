"""
Navy-and-gold theme for the Chat page, recreated from
github.com/SYLVESTER1922/Devreotes--GraphRag's app.py (read directly, not
assumed) - same palette (#050d1a navy background, #c9a84c gold), same
Palatino-serif-title-over-Lato-body pairing, same gradient header with a
gold bottom border.

Deliberately scoped under `#np-chat` rather than the reference's own
`body, .gradio-container` selectors, which would recolor the whole app -
every other page (Dashboard, Herd & Flock, Finance, ...) keeps its
existing green/white theme (see CUSTOM_CSS in ui/app.py); only the Chat
page's own wrapping column opts into navy-and-gold.
"""

CHAT_NAVY_CSS = """
#np-chat {
    background: #050d1a !important;
    font-family: 'Lato', sans-serif !important;
    color: #ffffff !important;
    border-radius: 0 0 12px 12px;
    padding: 16px !important;
}

#np-chat p, #np-chat span, #np-chat div, #np-chat label, #np-chat li,
#np-chat td, #np-chat th, #np-chat dt, #np-chat dd,
#np-chat .prose, #np-chat .markdown-text, #np-chat .label-wrap,
#np-chat input, #np-chat textarea, #np-chat select, #np-chat option,
#np-chat [data-testid] span, #np-chat [data-testid] label,
#np-chat [data-testid] p, #np-chat [data-testid] div {
    color: #ffffff !important;
}

#np-chat h1, #np-chat h2, #np-chat h3, #np-chat h4, #np-chat h5, #np-chat h6,
#np-chat strong, #np-chat b {
    color: #c9a84c !important;
    font-family: 'Palatino Linotype', 'Book Antiqua', Palatino, Georgia, serif !important;
}

#np-chat .eyebrow {
    color: #c9a84c; font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 2px; margin: 18px 0 8px 0;
}

/* Chat bubbles */
#np-chat .message.user > div, #np-chat div[class*="message"][class*="user"] > div:last-child {
    background: linear-gradient(135deg, #0d2147, #162d5a) !important;
    color: #ffffff !important;
    border: 1px solid rgba(201,168,76,0.15) !important;
    border-radius: 16px 16px 4px 16px !important;
    padding: 12px 16px !important;
}
#np-chat .message.bot > div, #np-chat .message.assistant > div,
#np-chat div[class*="message"][class*="bot"] > div:last-child,
#np-chat div[class*="message"][class*="assistant"] > div:last-child {
    background: linear-gradient(135deg, #091428, #0d1b2e) !important;
    color: #ffffff !important;
    border: 1px solid rgba(201,168,76,0.1) !important;
    border-radius: 16px 16px 16px 4px !important;
    padding: 12px 16px !important;
}
#np-chat .message strong, #np-chat div[class*="message"] strong { color: #c9a84c !important; }
#np-chat a, #np-chat .message a { color: #e8d48b !important; text-decoration: underline !important; }
#np-chat .chatbot, #np-chat div[class*="chatbot"] {
    background: #070e1a !important;
    border: 1px solid rgba(201,168,76,0.1) !important;
    border-radius: 16px !important;
}

/* Inputs */
#np-chat input, #np-chat textarea, #np-chat .textbox textarea {
    background: #0a1628 !important;
    color: #ffffff !important;
    border: 1px solid rgba(201,168,76,0.2) !important;
    border-radius: 10px !important;
}

/* Buttons */
#np-chat button.secondary, #np-chat button[class*="secondary"] {
    background: linear-gradient(135deg, #0d1b2e, #162640) !important;
    color: #c9a84c !important;
    border: 1px solid rgba(201,168,76,0.2) !important;
    border-radius: 8px !important;
}
#np-chat button.secondary:hover, #np-chat button[class*="secondary"]:hover {
    border-color: #c9a84c !important;
}
#np-chat button.primary, #np-chat button[class*="primary"] {
    background: linear-gradient(135deg, #8a6d1b, #c9a84c) !important;
    color: #0c1a2e !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
}
#np-chat button svg { color: #8a9bb8 !important; fill: #8a9bb8 !important; }
#np-chat button:hover svg { color: #c9a84c !important; fill: #c9a84c !important; }

/* Force dark backgrounds on every Gradio container inside the chat page */
#np-chat .gr-box, #np-chat .gr-panel, #np-chat .gr-form, #np-chat .gr-block,
#np-chat .gr-padded, #np-chat .contain, #np-chat .gap, #np-chat .form,
#np-chat [class*="block"], #np-chat [class*="panel"], #np-chat [class*="form"],
#np-chat [class*="group"], #np-chat [class*="wrap"], #np-chat [class*="container"],
#np-chat [class*="dropdown"], #np-chat [class*="audio"], #np-chat [class*="accordion"],
#np-chat .secondary-wrap, #np-chat .primary-wrap {
    background: #050d1a !important;
}

/* Dropdown menu items (Recent Searches) */
#np-chat [class*="dropdown"] ul, #np-chat [class*="dropdown"] li,
#np-chat [class*="dropdown"] option, #np-chat [role="listbox"],
#np-chat [role="option"] {
    background: #0a1628 !important;
    color: #ffffff !important;
}

/* Microphone / audio component */
#np-chat [class*="audio"] *, #np-chat [data-testid*="audio"] * { color: #ffffff !important; }
#np-chat [class*="audio"] button { color: #c9a84c !important; background: #0a1628 !important; }

/* Cards used by the left/right sidebars */
#np-chat .np-card {
    background: linear-gradient(135deg, #0f1c30, #162640);
    border: 1px solid rgba(201,168,76,0.15);
    border-radius: 12px;
    padding: 14px 16px;
    font-size: 12px;
    color: #8a9bb8;
    line-height: 1.7;
}
#np-chat .np-alert {
    background: #0d1b2e;
    border: 1px solid rgba(201,168,76,0.15);
    border-left: 3px solid #c9a84c;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 8px;
    font-size: 12px;
    color: #dce4ef;
}

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: #c9a84c; border-radius: 4px; }
"""


def chat_header_html(logo_data_uri: str) -> str:
    """The gradient header: Palatino-serif gold title, gold bottom border,
    NI_logo.png on the left (base64-embedded, same inline-not-linked
    reasoning as ui/app.py's own logo helper) - blank string degrades to no
    image rather than a broken page."""
    logo_img = (
        f'<img src="{logo_data_uri}" alt="Netrisyl Insights" '
        f'style="height:56px; width:auto; object-fit:contain; position:relative;"/>'
        if logo_data_uri else ""
    )
    return f"""
    <div style="background: linear-gradient(135deg, #0c1a2e 0%, #1a2d4a 30%, #243b5c 60%, #0c1a2e 100%);
                padding: 24px 32px; border-radius: 12px 12px 0 0; border-bottom: 3px solid #c9a84c;
                display: flex; align-items: center; justify-content: center; gap: 20px;
                position: relative; overflow: hidden;">
        <div style="position:absolute; top:0; left:0; right:0; bottom:0;
                    background: radial-gradient(ellipse at 30% 50%, rgba(201,168,76,0.06) 0%, transparent 60%),
                                radial-gradient(ellipse at 70% 50%, rgba(201,168,76,0.04) 0%, transparent 50%);
                    pointer-events: none;"></div>
        {logo_img}
        <div style="position: relative; text-align: center;">
            <div style="font-size: 26px; font-weight: 700; color: #c9a84c;
                        letter-spacing: 0.5px; font-family: 'Palatino Linotype', 'Book Antiqua', Palatino, Georgia, serif;">
                Netrisyl Farm Intelligence &middot; Chat</div>
            <div style="font-size: 11px; color: #c9a84c; font-weight: 600;
                        letter-spacing: 2px; margin-top: 4px; text-transform: uppercase;">
                Piggery &middot; Poultry &middot; Crops</div>
            <div style="font-size: 10px; color: #8a9bb8; margin-top: 5px; letter-spacing: 0.5px;">
                🎤 Voice input available &middot; Ask anything about your farm's real data</div>
        </div>
    </div>
    """
