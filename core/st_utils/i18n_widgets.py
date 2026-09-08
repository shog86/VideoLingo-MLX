"""Localized wrappers around Streamlit built-ins whose copy is hardcoded
in English in the Streamlit frontend (no Python-side locale API).

Currently: file_uploader ("Drag and drop file here", "Browse files",
"Limit ..."). Copy itself lives in translations/*.json; this module only
hides the English DOM nodes and re-injects the translated strings via CSS.
If a future Streamlit changes the DOM, the selectors silently stop matching
and the English originals show — nothing breaks.
"""
import html
from contextlib import contextmanager

import streamlit as st
from core.utils.config_utils import load_key
from translations.translations import translate as t


def cta_progress(slot, text):
    """Render live progress where the CTA button was.

    MUST be markdown, not st.button: buttons are registered widgets and
    re-creating one mid-run (even with a different key, even inside a
    placeholder) raises DuplicateWidgetID. Markdown re-renders freely.
    Styled to mimic the dark primary CTA.
    """
    safe = html.escape(text)
    slot.markdown(
        f"<div style='background:#1c1917;color:#fff;border-radius:10px;"
        f"padding:0.55em 1em;text-align:center;"
        f"font-size:14px;font-weight:600;'>{safe}</div>",
        unsafe_allow_html=True)


@contextmanager
def section_expander(label, ui_key, default=False):
    """Native expander whose initial open/close state comes from config.yaml.

    Single click to open/close (Streamlit keeps the toggled state for the
    rest of the session). Replaces the old checkbox-driven collapsible,
    whose manual widget-state/config sync could desync and needed an extra
    click to collapse.
    """
    try:
        saved = bool(load_key(f"ui.{ui_key}"))
    except KeyError:
        saved = default
    with st.expander(label, expanded=saved):
        yield


def uploader_i18n_css():
    browse = t("uploader_browse").replace('"', "'")
    return f"""<style>
/* hide "Drag and drop file(s) here" + "Limit ..." text, keep the icon */
[data-testid="stFileUploaderDropzoneInstructions"] > div:nth-child(2) {{
    display: none !important;
}}
/* relabel the Browse button (scoped to the dropzone so the row delete button is untouched) */
[data-testid="stFileUploaderDropzone"] button:not([data-testid="stFileUploaderDeleteBtn"]) {{
    font-size: 0 !important;
}}
[data-testid="stFileUploaderDropzone"] button:not([data-testid="stFileUploaderDeleteBtn"])::after {{
    content: "{browse}";
    font-size: 14px;
}}
</style>"""


def localized_uploader(key, file_types):
    """file_uploader with collapsed label; call sites add Chinese captions
    above/below, and uploader_i18n_css() relabels the Browse button."""
    return st.file_uploader("uploader", type=file_types, key=key,
                            label_visibility="collapsed")
