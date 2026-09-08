import streamlit as st
import os, sys, html
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime

os.environ["TORCHAUDIO_USE_BACKEND_DISPATCHER"] = "1"

# ffmpeg often lives outside the parent shell's PATH on macOS (Homebrew).
# Patch PATH inline here (before any core import pulls in pydub) so no
# module ever observes a PATH without ffmpeg; core code additionally uses
# core.utils.ffmpeg_utils for direct binary lookup.
for _bin in ("/opt/homebrew/bin", "/usr/local/bin"):
    if os.path.isdir(_bin) and _bin not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = _bin + os.pathsep + os.environ.get("PATH", "")

from core.st_utils.imports_and_utils import *
from core.st_utils.ui_log import UILog
from core.st_utils.i18n_widgets import section_expander
from core.st_utils.theme import THEME_CSS
from core import *

current_dir = os.path.dirname(os.path.abspath(__file__))
os.environ['PATH'] += os.pathsep + current_dir
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="VideoLingo-MLX", page_icon="docs/logo.svg")

SUB_VIDEO = "output/output_sub.mp4"
DUB_VIDEO = "output/output_dub.mp4"

# Intermediate file paths for phase detection
SRC_SRT = "output/src.srt"
TRANS_SRT = "output/trans.srt"
SRC_TRANS_SRT = "output/src_trans.srt"
TRANS_SRC_SRT = "output/trans_src.srt"
ALL_SRTS = [SRC_SRT, TRANS_SRT, SRC_TRANS_SRT, TRANS_SRC_SRT]
TRANSLATION_XLSX = "output/log/translation_results.xlsx"
SPLIT_SUB_XLSX = "output/log/translation_results_for_subtitles.xlsx"
CLEANED_CHUNKS_XLSX = "output/log/cleaned_chunks.xlsx"
TERMINOLOGY_JSON = "output/log/terminology.json"

# Shared subtitle options: (i18n label key, filename)
SUBTITLE_OPTIONS = [
    ("sub_label_source", "src.srt"),
    ("sub_label_trans", "trans.srt"),
    ("sub_label_src_trans", "src_trans.srt"),
    ("sub_label_trans_src", "trans_src.srt"),
]

def _has_media():
    try:
        from core._1_ytdlp import find_media_file
        find_media_file()
        return True
    except Exception:
        return False

# Anchor ids for the four pipeline sections (stepper links jump here,
# and the app auto-scrolls here when the active step changes).
STEP_ANCHORS = ["anchor-download", "anchor-phase1", "anchor-phase2", "anchor-phase3"]

def pipeline_status():
    """(steps, active_idx): file-on-disk derived pipeline state."""
    steps = [
        ("step_download", _has_media()),
        ("step_transcribe", os.path.exists(SRC_SRT) and os.path.exists(TRANS_SRT)),
        ("step_review", any(os.path.exists(p) for p in ALL_SRTS)),
        ("step_burn", os.path.exists(SUB_VIDEO)),
    ]
    # first incomplete step is the active one
    active_idx = next((i for i, (_, done) in enumerate(steps) if not done), len(steps))
    return steps, active_idx

def anchor(name):
    st.markdown(f"<div id='{name}' style='scroll-margin-top:190px;'></div>",
                unsafe_allow_html=True)

def maybe_autoscroll(active_idx):
    """Scroll the page to the active step's section, once per step change.

    Only fires when the active step actually advanced/completed (tracked in
    session state), so free browsing is never yanked around. No-op on first
    load and when the target section isn't rendered yet.
    """
    target = STEP_ANCHORS[min(active_idx, len(STEP_ANCHORS) - 1)]
    last = st.session_state.get("_last_active_step")
    st.session_state["_last_active_step"] = active_idx
    if last is None or last == active_idx:
        return
    import streamlit.components.v1 as components
    components.html(
        "<script>"
        f"var el = window.parent.document.getElementById('{target}');"
        "if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }"
        "</script>",
        height=0)

def render_stepper(steps, active_idx):
    """Slim 4-step pipeline status bar; each pill links to its section."""
    items = []
    for i, (key, done) in enumerate(steps):
        if done:
            bg, fg, mark = "#e7e5e4", "#1c1917", "✓"
        elif i == active_idx:
            bg, fg, mark = "#1c1917", "#ffffff", "●"
        else:
            bg, fg, mark = "transparent", "#a8a29e", "○"
        items.append(
            f"<a href='#{STEP_ANCHORS[i]}' style='flex:1;text-decoration:none;'>"
            f"<div style='text-align:center;background:{bg};color:{fg};"
            f"border-radius:10px;padding:8px 4px;font-size:14px;font-weight:600;'>"
            f"{mark} {t(key)}</div></a>")
        if i < len(steps) - 1:
            items.append("<div style='align-self:center;color:#a8a29e;padding:0 4px;'>→</div>")
    st.markdown(f"<div class='stepper-sticky' style='display:flex;align-items:stretch;margin:4px 0 12px 0;'>"
                f"{''.join(items)}</div>", unsafe_allow_html=True)

def _srt_mtime_label(path):
    mtime = os.path.getmtime(path)
    size = os.path.getsize(path)
    return datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M") + f" · {size/1024:.0f}KB"

def _stored_log_box(session_key):
    """Collapsed expander showing the previous run's log, if any."""
    lines = st.session_state.get(session_key)
    if lines:
        with st.expander(t("run_log"), expanded=False):
            st.code("\n".join(lines[-300:]), language="text")

def phase1_transcribe(log, progress_callback=None):
    """Step 2 (Transcribe): Transcription + NLP split + meaning split + summarize + translate + generate SRTs."""
    cb = progress_callback or log.progress_callback
    with redirect_stdout(log), redirect_stderr(log):
        log.log(f"=== {t('section_transcribe')} ===")
        _2_asr.transcribe(progress_callback=cb)

        log.log(t("ph_nlp"))
        _3_1_split_nlp.split_by_spacy()

        log.log(t("ph_meaning"))
        _3_2_split_meaning.split_sentences_by_meaning()

        log.log(t("ph_src_srt"))
        _gen_source_srt.gen_source_srt()

        log.log(t("ph_sum"))
        _4_1_summarize.get_summary()

        if load_key("pause_before_translate"):
            log.log("⚠️ pause_before_translate is ON: edit output/log/terminology.json in the next run "
                    "before translating. Continuing with current terminology this time.")

        log.log(t("ph_trans"))
        _4_2_translate.translate_all(progress_callback=cb)

        log.log(t("ph_split"))
        _5_split_sub.split_for_sub_main()

        log.log(t("ph_gen"))
        _6_gen_sub.align_timestamp_main()

        log.log(f"=== {t('phase1_done_summary')} ===")
    log.flush()

def phase3_burn(slot, tracks):
    """Step 4 (Burn): burn one subtitle file. Progress renders where the CTA was
    (markdown pill mimicking the dark button — buttons can't re-render
    mid-run without DuplicateWidgetID); the full ffmpeg log stays in the
    terminal (and in output/log on failure)."""
    def _cb(step=None, detail=None, percent=None):
        if detail:
            cta_progress(slot, detail)
    cta_progress(slot, t("phase3_starting"))
    _7_sub_into_vid.merge_subtitles_to_video(tracks=tracks, log_callback=_cb)

@st.fragment
def text_processing_section():
    with st.container():
        # ── Step 2: Transcribe ──
        anchor("anchor-phase1")
        st.header(t("section_transcribe"))
        phase1_done = os.path.exists(SRC_SRT) and os.path.exists(TRANS_SRT)

        if not phase1_done:
            slot1 = st.empty()
            has_media = _has_media()
            if not has_media:
                st.caption(t("need_media_first"))
            if slot1.button(t("start_transcribe"), key="phase1_button",
                            use_container_width=True, type="primary",
                            disabled=not has_media):
                st.session_state["running_phase1"] = True
                st.session_state.pop("phase1_log", None)
                # Live log stays collapsed by default (and tees to the
                # terminal) — the page only keeps the progress pill on top.
                log_expander = st.expander(t("run_log"), expanded=False)
                log = UILog(log_expander.empty(), title=f"🚀 {t('start_transcribe')}…")

                def _cb1(step=None, detail=None, percent=None):
                    if detail:
                        pct = f" {percent:.0f}%" if isinstance(percent, (int, float)) else ""
                        cta_progress(slot1, f"{detail}{pct}")
                    log.progress_callback(step, detail, percent)

                try:
                    phase1_transcribe(log, progress_callback=_cb1)
                except Exception as e:
                    log.log(f"❌ {t('section_transcribe')} failed: {e}")
                    log.flush()
                    st.session_state["phase1_log"] = list(log.lines)
                    st.session_state["running_phase1"] = False
                    st.error(f"{t('section_transcribe')} failed: {e}")
                else:
                    st.session_state["phase1_log"] = list(log.lines)
                    st.session_state["running_phase1"] = False
                    st.rerun()
        else:
            st.success(f"{t('phase1_done_summary')} · {len([p for p in ALL_SRTS if os.path.exists(p)])} SRT")
            with section_expander(t("subtitle_files"), "phase1_files", default=False):
                for label_key, fn in SUBTITLE_OPTIONS:
                    path = os.path.join("output", fn)
                    if not os.path.exists(path):
                        continue
                    c1, c2, c3 = st.columns([3, 2, 1])
                    with c1:
                        st.write(t(label_key))
                    with c2:
                        st.caption(_srt_mtime_label(path))
                    with c3:
                        with open(path, "r", encoding="utf-8") as f:
                            st.download_button(t("download"), f.read(), file_name=fn,
                                               mime="text/plain", key=f"dl_{fn}")
        _stored_log_box("phase1_log")

        # ── Step 3: Review (upload kept, single slot) ──
        if phase1_done:
            st.markdown("---")
            anchor("anchor-phase2")
            st.header(t("section_review"))
            st.info(t("phase2_hint"))
            existing = [(label_key, fn) for label_key, fn in SUBTITLE_OPTIONS
                        if os.path.exists(os.path.join("output", fn))]
            labels = [t(k) for k, _ in existing]
            pick = st.selectbox(t("phase2_pick"), options=labels, key="phase2_pick_sel")
            chosen_fn = dict(zip(labels, [fn for _, fn in existing]))[pick]
            _upload_srt_slot(chosen_fn)

        # ── Step 4: Burn ──
        if phase1_done:
            st.markdown("---")
            anchor("anchor-phase3")
            st.header(t("section_burn"))
            phase3_done = os.path.exists(SUB_VIDEO)

            if not phase3_done:
                if load_key("burn_subtitles"):
                    opts = [(label_key, fn) for label_key, fn in SUBTITLE_OPTIONS
                            if os.path.exists(os.path.join("output", fn))]
                    if not opts:
                        st.warning(t("phase3_no_srt"))
                    else:
                        labels = [t(k) for k, _ in opts]
                        choice = st.radio(t("phase3_pick"), options=labels,
                                          horizontal=True, key="burn_choice")
                        chosen_fn = dict(zip(labels, [fn for _, fn in opts]))[choice]
                        tracks = [os.path.join("output", chosen_fn)]

                        _render_subtitle_preview(chosen_fn)

                        slot3 = st.empty()
                        if slot3.button(t("start_burn"), key="phase3_button",
                                        use_container_width=True, type="primary"):
                            try:
                                phase3_burn(slot3, tracks)
                            except Exception as e:
                                st.error(f"{t('section_burn')} failed: {e}")
                            else:
                                st.rerun()
                else:
                    st.info(t("phase3_disabled"))
            else:
                st.video(SUB_VIDEO)
                download_subtitle_zip_button(text=t("Download All Srt Files"))
                if st.button(t("Archive to 'history'"), key="cleanup_in_text_processing"):
                    cleanup()
                    st.rerun()

def _upload_srt_slot(filename):
    """Single upload slot for the selected SRT file, with persistent confirmation."""
    path = os.path.join("output", filename)
    flag_key = f"uploaded_ok_{filename}"
    nonce_key = f"uploader_nonce_{filename}"
    if nonce_key not in st.session_state:
        st.session_state[nonce_key] = 0

    uploaded = localized_uploader(key=f"ul_{filename}_{st.session_state[nonce_key]}",
                                    file_types=["srt"])
    st.caption(f"{t('upload_edited_file')} · {t('uploader_limit_srt')}")
    if uploaded is not None:
        try:
            content = uploaded.read().decode("utf-8")
        except UnicodeDecodeError:
            st.error(t("upload_not_utf8"))
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        st.session_state[flag_key] = datetime.now().strftime("%m-%d %H:%M")
        st.session_state[nonce_key] += 1  # rotate key so the widget clears
        st.rerun()

    if os.path.exists(path):
        if flag_key in st.session_state:
            st.success(f"{t('uploaded_will_use')} {st.session_state[flag_key]}")
        else:
            st.caption(f"{t('on_disk')}: {_srt_mtime_label(path)}")

def _parse_first_srt_lines(path):
    """Return the text lines of the first subtitle entry in an SRT file."""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read().strip()
    except Exception:
        return []
    if not content:
        return []
    blocks = [b for b in content.split("\n\n") if b.strip()]
    if not blocks:
        return []
    lines = [ln for ln in blocks[0].splitlines() if ln.strip()]
    text = [ln for ln in lines if "-->" not in ln and not ln.strip().isdigit()]
    return text if text else lines

def _render_subtitle_preview(srt_filename):
    """Preview that mirrors the actual burn styles in _7_sub_into_vid.

    Top line = yellow on semi-opaque black box (BorderStyle=4),
    bottom line = white with outline+shadow, no box (BorderStyle=1).
    Sizes and the inter-line gap are derived from the same
    TOP_/BOTTOM_ constants the burner uses, so overlap/gap shows up here.
    """
    from core._7_sub_into_vid import (
        TOP_FONT_SIZE_BASE as TOP_FONT_SIZE,
        BOTTOM_FONT_SIZE_BASE as BOTTOM_FONT_SIZE,
        TOP_MARGIN_V_BASE as TOP_MARGIN_V,
        BOTTOM_MARGIN_V_BASE as BOTTOM_MARGIN_V,
        TOP_FONT_NAME,
    )
    path = os.path.join("output", srt_filename)
    text_lines = _parse_first_srt_lines(path)
    if not text_lines:
        st.warning(f"{srt_filename} {t('preview_empty')}")
        return

    # Real burn gap in style units: top baseline offset minus bottom
    # offset minus bottom line height. Clamp so preview never overlaps
    # differently from the burn.
    gap_px = max(4, TOP_MARGIN_V - BOTTOM_MARGIN_V - BOTTOM_FONT_SIZE)
    outline = "-1px 0 0 #000, 1px 0 0 #000, 0 -1px 0 #000, 0 1px 0 #000, 1px 1px 2px rgba(0,0,0,0.8)"
    rendered = []
    first = html.escape(text_lines[0].strip())
    rendered.append(
        f"<div style=\"display:inline-block;background:rgba(0,0,0,0.9);padding:2px 12px;"
        f"font-family:'{TOP_FONT_NAME}','Hiragino Sans GB','PingFang SC','Arial Unicode MS',sans-serif;"
        f"font-size:{TOP_FONT_SIZE}px;color:#FFFF00;text-shadow:{outline};"
        f"line-height:1.25;\">{first}</div>")
    if len(text_lines) > 1:
        second = html.escape(text_lines[1].strip())
        rendered.append(
            f"<div style=\"font-family:'Arial Unicode MS',sans-serif;"
            f"font-size:{BOTTOM_FONT_SIZE}px;color:#FFFFFF;text-shadow:{outline};"
            f"line-height:1.25;margin-top:{gap_px}px;\">{second}</div>")

    st.markdown(
        "<div style=\"max-width:560px;background:#3a3a3a;border-radius:8px;"
        "padding:28px 16px 12px 16px;text-align:center;\">"
        f"{''.join(rendered)}</div>",
        unsafe_allow_html=True)
    st.caption(t("preview_caption"))

def audio_processing_section():
    with st.container():
        st.markdown(f"""
        <p>
        {t("This stage includes the following steps:")}
        <p>
            1. {t("Generate audio tasks and chunks")}<br>
            2. {t("Extract reference audio")}<br>
            3. {t("Generate and merge audio files")}<br>
            4. {t("Merge final audio into video")}
        """, unsafe_allow_html=True)
        if not os.path.exists(DUB_VIDEO):
            if st.button(t("Start Audio Processing"), key="audio_processing_button",
                         use_container_width=True, type="primary"):
                process_audio()
                st.rerun()
        else:
            st.success(t("Audio processing is complete! You can check the audio files in the `output` folder."))
            if load_key("burn_subtitles"):
                st.video(DUB_VIDEO) 
            if st.button(t("Delete dubbing files"), key="delete_dubbing_files"):
                delete_dubbing_files()
                st.rerun()
            if st.button(t("Archive to 'history'"), key="cleanup_in_audio_processing"):
                cleanup()
                st.rerun()

def process_audio():
    with st.spinner(t("Generate audio tasks")): 
        _8_1_audio_task.gen_audio_task_main()
        _8_2_dub_chunks.gen_dub_chunks()
    with st.spinner(t("Extract refer audio")):
        _9_refer_audio.extract_refer_audio_main()
    with st.spinner(t("Generate all audio")):
        _10_gen_audio.gen_audio()
    with st.spinner(t("Merge full audio")):
        _11_merge_audio.merge_full_audio()
    with st.spinner(t("Merge dubbing to the video")):
        _12_dub_to_vid.merge_video_audio()
    
    st.success(t("Audio processing complete! 🎇"))
    st.balloons()

def main():
    logo_col, _ = st.columns([1,1])
    with logo_col:
        st.image("docs/logo.png", use_column_width=True)
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    welcome_text = t("Hello, welcome to VideoLingo-MLX. If you encounter any issues, please report them via GitHub Issues.")
    st.markdown(f"<p style='color: #78716c;'>{welcome_text}</p>", unsafe_allow_html=True)
    with st.sidebar:
        page_setting()
        st.markdown(give_star_button, unsafe_allow_html=True)

    st.markdown(uploader_i18n_css(), unsafe_allow_html=True)

    tab_sub, tab_dub = st.tabs([t("tab_subtitles"), t("tab_dubbing")])
    with tab_sub:
        steps, active_idx = pipeline_status()
        render_stepper(steps, active_idx)
        maybe_autoscroll(active_idx)
        anchor("anchor-download")
        download_video_section()
        text_processing_section()
    with tab_dub:
        audio_processing_section()

if __name__ == "__main__":
    main()
