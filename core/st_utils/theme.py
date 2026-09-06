"""Product theme: warm-neutral (stone) light theme, unified typography.

Applied once from st.main(). Complements .streamlit/config.toml (which sets
the base palette + kills the red toggle accent). All selectors use stable
data-testid hooks verified against streamlit==1.38 (uv.lock).
"""

THEME_CSS = """<style>
/* ---------- typography: one stack, one scale ---------- */
.stApp {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC",
                 "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    font-size: 15px;
    color: #1c1917;
}
.stApp h1 { font-size: 26px !important; font-weight: 700 !important; }
.stApp h2 { font-size: 20px !important; font-weight: 700 !important; }
.stApp h3 { font-size: 17px !important; font-weight: 600 !important; }

/* widget labels */
[data-testid="stWidgetLabel"] p {
    font-size: 14px !important;
    font-weight: 500 !important;
    color: #1c1917 !important;
}
/* captions (st.caption renders a plain <small>; rarely used otherwise) */
div[data-testid="stMarkdownContainer"] small {
    font-size: 12.5px !important;
    color: #78716c !important;
}

/* ---------- buttons: native kinds, one radius + text scale ----------
   Hierarchy via Streamlit's own system: primary (dark fill) for CTAs,
   secondary (subtle outline) for the rest. No per-kind overrides: the
   button kind does not reach the DOM on this Streamlit version. */
div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button {
    border-radius: 10px !important;
    font-size: 14px !important;
    font-weight: 600 !important;
}
div[data-testid="stDownloadButton"] > button {
    font-size: 13px !important;
    padding: 0.35em 0.9em !important;
}

/* ---------- inputs ---------- */
div[data-testid="stTextInput"] input,
div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
div[data-testid="stTextArea"] textarea {
    border-radius: 10px !important;
}

/* ---------- feedback boxes: keep semantics, soften shape ---------- */
div[data-testid="stAlert"] {
    border-radius: 10px !important;
    font-size: 14px !important;
}

/* ---------- section headers (the only checkboxes app-wide) ---------- */
div[data-testid="stCheckbox"] label p {
    font-size: 15px !important;
    font-weight: 700 !important;
    color: #1c1917 !important;
}

/* ---------- tabs ---------- */
button[data-testid="stTab"] p {
    font-size: 15px !important;
    font-weight: 600 !important;
}

/* ---------- code / log blocks ---------- */
div[data-testid="stCode"] {
    border-radius: 10px !important;
}
div[data-testid="stCode"] code {
    font-size: 12.5px !important;
}

/* ---------- file uploader dropzone: subtle dashed target ---------- */
section[data-testid="stFileUploaderDropzone"] {
    border-radius: 10px !important;
}

/* ---------- sidebar ---------- */
section[data-testid="stSidebar"] {
    background: #fafaf9 !important;
}
section[data-testid="stSidebar"] h3 {
    font-size: 15px !important;
}
</style>"""
