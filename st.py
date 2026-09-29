import streamlit as st
import os, sys, html, io, threading
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

# Managed FFmpeg/ffprobe (static-ffmpeg, fetched by install.py) takes priority:
# it prepends the bundled binaries dir to PATH so every later bare-`ffmpeg`
# subprocess (yt-dlp, pydub, burns) resolves. Missing runtime (direct source
# launch before install) is non-fatal here; install run FFmpeg prepare it.
from runtime_libraries import configure_ffmpeg
configure_ffmpeg(required=False)

from core.st_utils.imports_and_utils import *
from core.st_utils.i18n_widgets import section_expander
from core.st_utils.theme import THEME_CSS
from core import *
from core.task_runner import TaskRunner
from core.pipeline import get_steps, burn_subtitles

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

# ── 后台任务基础设施（工作线程写状态，UI 用 fragment 轮询读） ──────────────
# 工作线程不能安全访问 st.session_state，所以进度与日志放在模块级字典里。
_RUN_STATE = {}
_RUN_LOCK = threading.Lock()


class _RunLog(io.TextIOBase):
    """把工作线程里 core 的输出按行收集到列表，供 UI 轮询展示。"""

    def __init__(self, state):
        self._state = state
        self._buf = ""

    def write(self, text):
        if not text:
            return 0
        self._buf += text.replace("\r", "\n")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                with _RUN_LOCK:
                    self._state["log"].append(line)
        return len(text)

    def flush(self):
        pass


def _run_state(key):
    """取得（必要时创建）某个任务 key 的进度/日志状态。"""
    with _RUN_LOCK:
        return _RUN_STATE.setdefault(key, {"detail": "", "percent": None, "log": []})


def _get_runner(key):
    """从 session_state 取任务执行器；每个阶段一个独立实例。"""
    if key not in st.session_state:
        st.session_state[key] = TaskRunner()
    return st.session_state[key]


def _progress_cb(key):
    """构造进度回调：把 core 的分步进度写入该 key 的状态字典。"""
    state = _run_state(key)

    def _cb(step=None, detail=None, percent=None):
        if detail:
            state["detail"] = detail
        if isinstance(percent, (int, float)):
            state["percent"] = float(percent)

    return _cb


def _start_task(key, steps, log_title):
    """在后台线程启动任务：重定向 core 输出到日志，再交给 TaskRunner 执行。"""
    state = _run_state(key)
    state["detail"] = log_title
    state["percent"] = None
    state["log"].clear()
    log = _RunLog(state)

    def _wrap(label, func):
        def _run():
            log.write(f"=== {t(label)} ===\n")
            with redirect_stdout(log), redirect_stderr(log):
                func()
        return (label, _run)

    _get_runner(key).start([_wrap(label, fn) for label, fn in steps])


def _pill(text):
    """渲染仿主按钮的深色进度条（markdown，运行中可自由重绘）。"""
    return (f"<div style='background:#1c1917;color:#fff;border-radius:10px;"
            f"padding:0.55em 1em;text-align:center;font-size:14px;"
            f"font-weight:600;'>{html.escape(text)}</div>")


@st.fragment(run_every=1)
def _task_panel(key):
    """轮询后台任务状态，渲染进度、暂停/继续/停止按钮与运行日志。

    任务本身跑在后台线程，这里每秒重绘一次（只读状态），因此不会重现历史上
    “长时间任务 + 碎片 Stop”导致的 RuntimeError。
    """
    runner = _get_runner(key)
    if runner.state == "idle":
        return
    state = _run_state(key)
    detail = state.get("detail") or ""
    percent = state.get("percent")
    pct = f" {percent:.0f}%" if isinstance(percent, (int, float)) else ""

    if runner.state in ("running", "paused", "stopping"):
        if runner.state == "paused":
            head = f"⏸️ {t('Paused')}"
        elif runner.state == "stopping":
            head = f"⏹️ {t('Stopping...')}"
        else:
            head = f"⏳ {t('Running...')}"
        st.markdown(_pill(f"{head} {detail}{pct}".strip()), unsafe_allow_html=True)
        st.progress(min(max(runner.progress, 0.0), 1.0))
        if runner.pause_message:
            st.info(t(runner.pause_message))
        col1, col2 = st.columns(2)
        with col1:
            if runner.state == "paused":
                if st.button(f"▶️ {t('Resume')}", key=f"{key}_resume", use_container_width=True):
                    runner.resume()
                    st.rerun()
            elif st.button(f"⏸️ {t('Pause')}", key=f"{key}_pause", use_container_width=True,
                           disabled=runner.state != "running"):
                runner.pause()
                st.rerun()
        with col2:
            if st.button(f"⏹️ {t('Stop')}", key=f"{key}_stop", use_container_width=True, type="primary"):
                runner.stop()
                st.rerun()
        with st.expander(t("run_log"), expanded=False):
            st.code("\n".join(state.get("log", [])[-300:]), language="text")
    elif runner.state == "completed":
        st.session_state[f"{key}_log"] = list(state.get("log", []))
        runner.reset()
        st.rerun(scope="app")
    elif runner.state == "stopped":
        st.warning(t("Task stopped"))
        if st.button(t("OK"), key=f"{key}_ack_stop", use_container_width=True):
            runner.reset()
            st.rerun(scope="app")
    elif runner.state == "error":
        st.error(f"{t('Task error')}: {runner.error_msg}")
        if st.button(t("OK"), key=f"{key}_ack_error", use_container_width=True):
            runner.reset()
            st.rerun(scope="app")


def phase3_burn(slot, tracks):
    """Step 4 (Burn): burn one subtitle file. Progress renders where the CTA was
    (markdown pill mimicking the dark button — buttons can't re-render
    mid-run without DuplicateWidgetID); the full ffmpeg log stays in the
    terminal (and in output/log on failure)."""
    def _cb(step=None, detail=None, percent=None):
        if detail:
            cta_progress(slot, detail)
    cta_progress(slot, t("phase3_starting"))
    burn_subtitles(tracks=tracks, log_callback=_cb)

# 长时间任务现在跑在后台线程（见 _start_task / _task_panel），页面只保留一个
# 每秒轮询的 fragment 做进度与控制，因此不再需要历史上“禁止 fragment”的规避。
def text_processing_section():
    with st.container():
        # ── Step 2: Transcribe ──
        anchor("anchor-phase1")
        st.header(t("section_transcribe"))
        phase1_done = os.path.exists(SRC_SRT) and os.path.exists(TRANS_SRT)

        if not phase1_done:
            runner = _get_runner("phase1")
            has_media = _has_media()
            if not has_media:
                st.caption(t("need_media_first"))
            if runner.state == "idle":
                if st.button(t("start_transcribe"), key="phase1_button",
                             use_container_width=True, type="primary",
                             disabled=not has_media):
                    st.session_state.pop("phase1_log", None)
                    _start_task("phase1",
                                get_steps("subtitles", progress_callback=_progress_cb("phase1")),
                                t("start_transcribe"))
                    st.rerun()
            else:
                # 后台任务在独立线程执行，这里轮询进度并渲染暂停/停止控制
                _task_panel("phase1")
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
            runner = _get_runner("dubbing")
            if runner.state == "idle":
                if st.button(t("Start Audio Processing"), key="audio_processing_button",
                             use_container_width=True, type="primary"):
                    _start_task("dubbing",
                                get_steps("dubbing", progress_callback=_progress_cb("dubbing")),
                                t("Start Audio Processing"))
                    st.rerun()
            else:
                # 后台任务在独立线程执行，这里轮询进度并渲染暂停/停止控制
                _task_panel("dubbing")
                _stored_log_box("dubbing_log")
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
            _stored_log_box("dubbing_log")

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
