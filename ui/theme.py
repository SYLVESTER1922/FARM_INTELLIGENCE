"""
Light theme for the Chat page, sharing the Dashboard's palette.

The colours live as CSS variables on `:root` (defined at the top of
`CUSTOM_CSS` in ui/app.py - cream background, deep green, gold, navy text), and
this stylesheet only reads them, so the two pages cannot drift apart.

Everything is scoped under `#np-chat`; no other page is touched. This file
holds CSS and markup only - no behaviour.

Spacing uses 8px steps (--fi-s1 .. --fi-s4), type uses three sizes
(--fi-fs-sm 13px, --fi-fs-md 15px, --fi-fs-lg 20px).
"""

CHAT_CSS = """
#np-chat {
    --fi-s1: 8px; --fi-s2: 16px; --fi-s3: 24px; --fi-s4: 32px;
    --fi-fs-sm: 13px; --fi-fs-md: 15px; --fi-fs-lg: 20px;
    font-family: 'Plus Jakarta Sans', 'Helvetica Neue', system-ui, sans-serif;
    color: var(--fi-text);
    background: transparent !important;
    padding: 0 !important;
    gap: var(--fi-s2) !important;
    min-width: 0;
}
#np-chat, #np-chat * { box-sizing: border-box; }
#np-chat .prose, #np-chat label, #np-chat p, #np-chat span { color: inherit; }

/* ---- Header ---------------------------------------------------------- */
#np-chat .np-head {
    display: flex; flex-direction: column; gap: 4px;
    padding: var(--fi-s2) var(--fi-s3);
    background: var(--fi-card);
    border: 1px solid var(--fi-border);
    border-bottom: 3px solid var(--fi-gold);
    border-radius: var(--fi-radius);
    box-shadow: var(--fi-shadow);
}
#np-chat .np-head-title {
    font-size: var(--fi-fs-lg); font-weight: 800; color: var(--fi-gold-text);
    letter-spacing: 0.3px; line-height: 1.2;
}
#np-chat .np-head-sub { font-size: var(--fi-fs-sm); color: var(--fi-muted); }

/* ---- Layout: centred chat + slim side panel ---------------------------- */
#np-chat .np-layout { gap: var(--fi-s3) !important; align-items: flex-start; flex-wrap: wrap !important; }
#np-chat #np-main { flex: 3 1 480px !important; min-width: 0 !important; max-width: 880px; margin: 0 auto; gap: var(--fi-s2) !important; }
#np-chat #np-side { flex: 1 1 260px !important; min-width: 240px !important; max-width: 340px; gap: var(--fi-s1) !important; }
@media (max-width: 900px) {
    #np-chat #np-main, #np-chat #np-side { flex-basis: 100% !important; max-width: 100%; }
}

/* ---- Snapshot chips ------------------------------------------------------ */
#np-chat .np-chips { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--fi-s1); }
@media (max-width: 700px) { #np-chat .np-chips { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
#np-chat .np-chip {
    background: var(--fi-card); border: 1px solid var(--fi-border);
    border-radius: 12px; padding: 8px 16px; box-shadow: var(--fi-shadow);
    display: flex; flex-direction: column; min-width: 0;
}
#np-chat .np-chip-value { font-size: var(--fi-fs-lg); font-weight: 800; color: var(--fi-green); line-height: 1.2; }
#np-chat .np-chip-label {
    font-size: var(--fi-fs-sm); color: var(--fi-muted); line-height: 1.3;
    overflow-wrap: anywhere;
}

/* ---- Toolbar (icon buttons) -------------------------------------------------- */
#np-chat #np-toolbar { justify-content: flex-end; gap: var(--fi-s1) !important; flex-wrap: nowrap !important; }
#np-chat #np-toolbar > * { flex: 0 0 auto !important; min-width: 0 !important; }
#np-chat #np-toolbar button, #np-chat .np-tool {
    width: auto !important; min-width: 0 !important; padding: 4px 16px !important;
    font-size: var(--fi-fs-sm) !important; border-radius: 999px !important;
}
#np-chat .np-report-panel {
    padding: var(--fi-s2) !important; gap: var(--fi-s1) !important;
    background: var(--fi-card) !important; border: 1px solid var(--fi-border) !important;
    border-radius: var(--fi-radius) !important; box-shadow: var(--fi-shadow);
}
#np-chat .np-report-panel > *, #np-chat .np-report-panel .block, #np-chat .np-report-panel .form {
    background: transparent !important; border: none !important; box-shadow: none !important;
}
#np-chat .np-report-panel textarea { border: 1px solid var(--fi-border) !important; }
#np-chat .np-report-panel button { border: 1px solid var(--fi-border) !important; }

/* ---- Chat window -------------------------------------------------------------- */
#np-chat #np-chatbot {
    background: var(--fi-card) !important;
    border: 1px solid var(--fi-border) !important;
    border-radius: var(--fi-radius) !important;
    box-shadow: var(--fi-shadow);
}
#np-chat #np-chatbot .bubble-wrap, #np-chat #np-chatbot .message-wrap { background: transparent !important; }
#np-chat #np-chatbot .message-wrap { gap: var(--fi-s2) !important; padding: var(--fi-s2) !important; }
#np-chat #np-chatbot .message {
    font-size: var(--fi-fs-md) !important; line-height: 1.6;
    color: var(--fi-text) !important;
    border-radius: 16px !important;
    padding: 12px 16px !important;
    box-shadow: var(--fi-shadow);
    border: 1px solid var(--fi-border) !important;
}
#np-chat #np-chatbot .message *, #np-chat #np-chatbot .message { color: var(--fi-text); }
#np-chat #np-chatbot .user .message, #np-chat #np-chatbot .message.user {
    background: var(--fi-green-tint) !important; border-color: #cfe0d3 !important;
}
#np-chat #np-chatbot .bot .message, #np-chat #np-chatbot .message.bot,
#np-chat #np-chatbot .assistant .message, #np-chat #np-chatbot .message.assistant {
    background: #ffffff !important;
}
/* Gradio nests a second .message inside the bubble: style only the outer one. */
#np-chat #np-chatbot .message .message {
    background: transparent !important; border: none !important; box-shadow: none !important;
    padding: 0 !important; border-radius: 0 !important;
}
#np-chat #np-chatbot .message strong { color: var(--fi-green); }
#np-chat #np-chatbot .message a { color: var(--fi-green); text-decoration: underline; }
#np-chat #np-chatbot .placeholder-content, #np-chat #np-chatbot .placeholder { padding: var(--fi-s2) var(--fi-s3) !important; text-align: center; }
#np-chat #np-chatbot .placeholder-content, #np-chat #np-chatbot .placeholder { color: var(--fi-text) !important; }
#np-chat #np-chatbot .placeholder .prose, #np-chat #np-chatbot .placeholder h3 {
    font-size: var(--fi-fs-lg); color: var(--fi-green) !important;
}
#np-chat #np-chatbot .example, #np-chat #np-chatbot button.example {
    background: var(--fi-card) !important; color: var(--fi-green) !important;
    border: 1px solid var(--fi-border) !important; border-radius: 999px !important;
    font-size: var(--fi-fs-sm) !important; padding: 8px 16px !important;
    box-shadow: var(--fi-shadow);
}
#np-chat #np-chatbot .example:hover { border-color: var(--fi-gold) !important; background: #fff9ec !important; }
#np-chat #np-chatbot .example * { color: var(--fi-green) !important; }
#np-chat #np-chatbot .example-text, #np-chat #np-chatbot .example-text-content { color: var(--fi-green) !important; }

/* ---- Composer: one row, text box + mic + send ---------------------------------- */
#np-chat #np-composer {
    background: var(--fi-card) !important; border: 1px solid var(--fi-border);
    border-radius: var(--fi-radius); padding: var(--fi-s1) !important;
    box-shadow: var(--fi-shadow);
    flex-wrap: nowrap !important; align-items: center !important; gap: var(--fi-s1) !important;
}
#np-chat #np-composer > * { min-width: 0 !important; }
#np-chat #np-composer #np-msg { flex: 1 1 auto !important; }
#np-chat #np-composer #np-msg, #np-chat #np-composer #np-msg > label,
#np-chat #np-composer #np-msg .container { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
#np-chat #np-composer textarea {
    background: var(--fi-bg) !important; color: var(--fi-text) !important;
    border: 1px solid var(--fi-border) !important; border-radius: 12px !important;
    font-size: var(--fi-fs-md) !important; padding: 12px 16px !important;
}
#np-chat #np-composer textarea:focus { border-color: var(--fi-green) !important; outline: none; box-shadow: 0 0 0 3px rgba(47,109,58,0.15) !important; }
#np-chat #np-composer #np-mic { flex: 0 0 auto !important; width: auto !important; max-width: none; }
#np-chat #np-send { flex: 0 0 auto !important; width: auto !important; min-width: 88px !important; }
#np-chat #np-send, #np-chat #np-send button {
    background: var(--fi-green) !important; color: #ffffff !important; border: none !important;
    border-radius: 12px !important; font-weight: 700 !important; font-size: var(--fi-fs-md) !important;
    height: 44px; padding: 0 24px !important;
}
#np-chat #np-send:hover { background: var(--fi-green-dark) !important; }

/* Compact microphone: one line, label hidden, recording state inline. */
#np-chat #np-mic, #np-chat #np-mic .block, #np-chat #np-mic .component-wrap {
    background: transparent !important; border: none !important; box-shadow: none !important;
    padding: 0 !important; margin: 0 !important; min-height: 0 !important;
}
#np-chat #np-mic [data-testid="block-label"], #np-chat #np-mic label > span:first-child,
#np-chat #np-mic .label-wrap, #np-chat #np-mic .empty, #np-chat #np-mic .icon-button-wrapper { display: none !important; }
#np-chat #np-mic .audio-container, #np-chat #np-mic .mic-wrap, #np-chat #np-mic .controls {
    display: flex; align-items: center; gap: var(--fi-s1); background: transparent !important;
    padding: 0 !important; height: 44px;
}
#np-chat #np-mic button {
    background: var(--fi-card) !important; color: var(--fi-green) !important;
    border: 1px solid var(--fi-border) !important; border-radius: 12px !important;
    height: 44px; min-width: 44px; padding: 0 16px !important; font-size: var(--fi-fs-sm) !important;
    white-space: nowrap;
}
#np-chat #np-mic button:hover { border-color: var(--fi-green) !important; }
#np-chat #np-mic button * { color: var(--fi-green) !important; }
#np-chat #np-mic .component-wrapper, #np-chat #np-mic .controls .wrapper {
    height: 44px !important; min-height: 0 !important; padding: 0 !important; margin: 0 !important;
    display: flex; align-items: center; background: transparent !important;
}
#np-chat #np-mic .controls { width: auto !important; }
#np-chat #np-mic .controls .wrapper { flex-wrap: nowrap !important; gap: var(--fi-s1) !important; }
#np-chat #np-mic .stop-button, #np-chat #np-mic .stop-button-paused, #np-chat #np-mic .record-button {
    width: auto !important; flex: 0 0 auto; overflow: visible !important; align-items: center; gap: var(--fi-s1);
}
#np-chat #np-mic .pause-button, #np-chat #np-mic .resume-button {
    width: 44px !important; height: 44px !important; padding: 0 !important; flex: 0 0 auto;
}
#np-chat #np-mic .pause-button svg { width: 20px; height: 20px; }
#np-chat #np-mic .timestamps { display: flex; gap: 0; }
#np-chat #np-mic .timestamps > div { display: none !important; }
#np-chat #np-mic .component-wrapper { width: auto !important; gap: var(--fi-s1); }
#np-chat #np-mic .timestamps, #np-chat #np-mic .time { margin: 0 !important; padding: 0 !important; width: auto !important; }
#np-chat #np-mic .record, #np-chat #np-mic .stop-button, #np-chat #np-mic .stop-button-paused { gap: var(--fi-s1); }
#np-chat #np-mic .dot, #np-chat #np-mic .pause-button { flex: 0 0 auto; }
#np-chat #np-mic .time, #np-chat #np-mic .timestamps { font-size: var(--fi-fs-sm); color: var(--fi-muted) !important; }
#np-chat #np-mic .waveform-container, #np-chat #np-mic .microphone, #np-chat #np-mic [data-testid="waveform-mic"] { display: none !important; }
#np-chat #np-mic select, #np-chat #np-mic .select-wrap { display: none !important; }

@media (max-width: 600px) {
    #np-chat #np-composer { flex-wrap: wrap !important; }
    #np-chat #np-composer #np-msg { flex: 1 1 100% !important; }
    #np-chat #np-composer #np-mic { flex: 1 1 auto !important; max-width: none; }
    #np-chat #np-send { flex: 1 1 auto !important; }
}

/* ---- Follow-up chips ------------------------------------------------------------- */
#np-chat .np-fup-label { font-size: var(--fi-fs-sm); color: var(--fi-muted); margin: 0; }
#np-chat #np-followups { flex-wrap: wrap !important; gap: var(--fi-s1) !important; }
#np-chat #np-followups > * { flex: 0 1 auto !important; min-width: 0 !important; width: auto !important; max-width: 100% !important; }
#np-chat #np-followups button {
    background: var(--fi-card) !important; color: var(--fi-green) !important;
    border: 1px solid var(--fi-border) !important; border-radius: 999px !important;
    font-size: var(--fi-fs-sm) !important; font-weight: 600 !important;
    padding: 8px 16px !important; width: auto !important; max-width: 100% !important;
    white-space: normal; text-align: left;
    box-shadow: var(--fi-shadow); line-height: 1.3;
}
#np-chat #np-followups button:hover { border-color: var(--fi-gold) !important; background: #fff9ec !important; }

/* ---- Side panel: alerts + collapsible sections --------------------------------------- */
#np-chat .np-side-title {
    font-size: var(--fi-fs-sm); font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
    color: var(--fi-green); border-left: 3px solid var(--fi-gold); padding-left: var(--fi-s1); margin: 0;
}
#np-chat .np-alert {
    background: #fff9ec; border: 1px solid #e8dfc7; border-left: 4px solid var(--fi-red);
    border-radius: 10px; padding: 8px 16px; margin-bottom: 8px;
    font-size: var(--fi-fs-sm); line-height: 1.4; color: var(--fi-text);
}
#np-chat .np-alert b { color: var(--fi-text); }
#np-chat .np-card {
    background: var(--fi-card); border: 1px solid var(--fi-border); border-radius: 12px;
    padding: 16px; font-size: var(--fi-fs-sm); line-height: 1.6; color: var(--fi-text);
}
#np-chat .np-card strong { color: var(--fi-green); }
#np-chat .np-side-acc, #np-chat #np-side .accordion, #np-chat #np-side details {
    background: var(--fi-card) !important; border: 1px solid var(--fi-border) !important;
    border-radius: 12px !important; box-shadow: var(--fi-shadow);
}
#np-chat #np-side .label-wrap, #np-chat #np-side .label-wrap span {
    font-size: var(--fi-fs-sm) !important; font-weight: 700 !important; color: var(--fi-green) !important;
    padding: 4px 16px !important;
}

/* Quick Lookup radios: labelled, wrapped, never clipped */
#np-chat #np-side fieldset, #np-chat #np-side .wrap { gap: var(--fi-s1) !important; flex-wrap: wrap !important; }
#np-chat #np-side label.svelte-1ipelgc, #np-chat #np-side [data-testid="radio-label"],
#np-chat #np-side .radio-group label, #np-chat #np-side label:has(input[type="radio"]) {
    background: var(--fi-card) !important; color: var(--fi-text) !important;
    border: 1px solid var(--fi-border) !important; border-radius: 999px !important;
    padding: 4px 16px !important; font-size: var(--fi-fs-sm) !important; min-width: 0 !important;
    width: auto !important; overflow: visible !important;
}
#np-chat #np-side label:has(input[type="radio"]:checked) {
    background: var(--fi-green) !important; border-color: var(--fi-green) !important; color: #ffffff !important;
}
#np-chat #np-side label:has(input[type="radio"]) span { color: inherit !important; }

/* ---- Generic controls on the light page -------------------------------------------------- */
#np-chat input[type="text"], #np-chat textarea, #np-chat select {
    background: var(--fi-bg) !important; color: var(--fi-text) !important;
    border: 1px solid var(--fi-border) !important; border-radius: 10px !important;
    font-size: var(--fi-fs-sm);
}
#np-chat button.secondary {
    background: var(--fi-card) !important; color: var(--fi-green) !important;
    border: 1px solid var(--fi-border) !important; border-radius: 10px !important;
    font-weight: 600 !important;
}
#np-chat button.secondary:hover { border-color: var(--fi-green) !important; }
#np-chat button.primary { background: var(--fi-green) !important; color: #ffffff !important; border: none !important; }
#np-chat [role="listbox"], #np-chat [role="option"] { background: var(--fi-card) !important; color: var(--fi-text) !important; }
#np-chat .block { border-color: var(--fi-border); }
"""


def chat_header_html(logo_data_uri: str = "") -> str:
    """The compact Chat header. The brand logo already sits in the app-wide
    header above every page, so it is not repeated here (the argument is kept
    so existing callers keep working)."""
    return """
    <div class="np-head">
        <div class="np-head-title">Chat</div>
        <div class="np-head-sub">Ask anything about your farm's real data &middot; Piggery &middot; Poultry &middot; Crops &middot; voice input available</div>
    </div>
    """
