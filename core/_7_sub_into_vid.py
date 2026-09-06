import os, subprocess, time
from core._1_ytdlp import find_video_files
import cv2
from core.utils import *
from translations.translations import translate as t

# Bilingual look (matches product style): top line = yellow on black box,
# larger; bottom line = white, smaller.
TOP_FONT_SIZE = 20
BOTTOM_FONT_SIZE = 15

def _pick_cjk_font():
    """Pick a Chinese-capable font that ffmpeg/libass can actually open.

    'PingFang SC' resolves via CoreText to the private Reserved/
    PingFangUI.ttc path, which libass fails to open ("Error opening
    font", then silent fallback). Prefer Hiragino Sans GB on macOS —
    same gothic look, opens cleanly. Other OSes get their local CJK font.
    """
    candidates = [
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", "Hiragino Sans GB"),
        ("/System/Library/Fonts/STHeiti Medium.ttc", "STHeiti"),
        ("/System/Library/Fonts/Supplemental/Songti.ttc", "Songti SC"),
        ("/Library/Fonts/Arial Unicode.ttf", "Arial Unicode MS"),
        ("C:/Windows/Fonts/msyh.ttc", "Microsoft YaHei"),
        ("C:/Windows/Fonts/simhei.ttf", "SimHei"),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "Noto Sans CJK SC"),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "WenQuanYi Micro Hei"),
    ]
    for path, family in candidates:
        if os.path.exists(path):
            return family
    return "sans-serif"

TOP_FONT_NAME = _pick_cjk_font()
BOTTOM_FONT_NAME = 'Arial Unicode MS'
# MarginV diff = line gap: TOP sits above BOTTOM by (TOP_MARGIN_V -
# BOTTOM_MARGIN_V - BOTTOM_FONT_SIZE). Keep a small gap (~8px in style
# units): 50 - 27 - 15 = 8, so lines are separated but not far apart.
TOP_MARGIN_V = 50
BOTTOM_MARGIN_V = 27

TOP_STYLE = (
    f"FontSize={TOP_FONT_SIZE},FontName={TOP_FONT_NAME},"
    f"PrimaryColour=&H00FFFF,OutlineColour=&H000000,OutlineWidth=1,"
    f"BackColour=&H1A000000,Alignment=2,MarginV={TOP_MARGIN_V},BorderStyle=4"
)
BOTTOM_STYLE = (
    f"FontSize={BOTTOM_FONT_SIZE},FontName={BOTTOM_FONT_NAME},"
    f"PrimaryColour=&HFFFFFF,OutlineColour=&H000000,OutlineWidth=1,"
    f"ShadowColour=&H80000000,BorderStyle=1,Alignment=2,MarginV={BOTTOM_MARGIN_V}"
)

OUTPUT_DIR = "output"
OUTPUT_VIDEO = f"{OUTPUT_DIR}/output_sub.mp4"
SRC_SRT = f"{OUTPUT_DIR}/src.srt"
TRANS_SRT = f"{OUTPUT_DIR}/trans.srt"
    
def check_gpu_available():
    ffmpeg_bin = _find_ffmpeg_for_gpu()
    try:
        result = subprocess.run([ffmpeg_bin, '-encoders'], capture_output=True, text=True)
        return 'videotoolbox' in result.stdout
    except:
        return False

def _find_ffmpeg_for_gpu():
    """Find an ffmpeg binary that supports VideoToolbox (system Homebrew build)."""
    for candidate in ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg']:
        try:
            r = subprocess.run([candidate, '-encoders'], capture_output=True, text=True)
            if 'videotoolbox' in r.stdout:
                return candidate
        except FileNotFoundError:
            continue
    return 'ffmpeg'  # fallback to PATH

def _build_encoder_cmd(ffmpeg_cmd, video_file):
    """Append VideoToolbox / software encoder flags to ffmpeg_cmd (mutates list)."""
    ffmpeg_gpu = load_key("ffmpeg_gpu")

    if ffmpeg_gpu:
        # Detect available VideoToolbox encoder (prefer H.265 for quality)
        ffmpeg_bin = _find_ffmpeg_for_gpu()
        result = subprocess.run([ffmpeg_bin, '-encoders'], capture_output=True, text=True)
        if 'hevc_videotoolbox' in result.stdout:
            vt_codec = 'hevc_videotoolbox'
            rprint("[bold green]🎬 Using GPU acceleration: VideoToolbox H.265.[/bold green]")
        elif 'h264_videotoolbox' in result.stdout:
            vt_codec = 'h264_videotoolbox'
            rprint("[bold green]🎬 Using GPU acceleration: VideoToolbox H.264.[/bold green]")
        else:
            vt_codec = None

        if vt_codec:
            ffmpeg_cmd[0] = ffmpeg_bin  # use system ffmpeg with VT support
            ffmpeg_cmd.extend(['-c:v', vt_codec])
            # VT quality: -q:v maps to 1-100 scale (lower = better); 60 ≈ good balance
            ffmpeg_cmd.extend(['-q:v', '60'])
            # Pixel format for hardware acceleration efficiency
            ffmpeg_cmd.extend(['-pix_fmt', 'nv12'])
            # VFR to match source
            ffmpeg_cmd.extend(['-r', '30000/1001'])
            # Color range
            ffmpeg_cmd.extend(['-color_range', 'tv'])
            return

    # Software fallback: H.264 High profile, CRF 18, slow preset
    ffmpeg_cmd.extend(['-c:v', 'libx264', '-crf', '18', '-preset', 'slow',
                        '-profile:v', 'high', '-level:v', '4.1'])

def _escape_sub_path(path: str) -> str:
    """Escape a subtitle path for use inside ffmpeg's subtitles filter."""
    return (path.replace('\\', '/').replace("'", r"\'")
                .replace(',', r'\,').replace('[', r'\[').replace(']', r'\]')
                .replace(';', r'\;').replace(':', r'\:'))


def _sub_filter(srt_path: str, style: str) -> str:
    return f"subtitles={_escape_sub_path(srt_path)}:force_style='{style}'"


def _write_srt(entries, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for i, (ts, text) in enumerate(entries, 1):
            f.write(f"{i}\n{ts}\n{text}\n\n")


def _split_bilingual_srt(path):
    """Split one SRT into top/bottom single-line SRTs.

    A bilingual entry (2 text lines) becomes line1 → top track (yellow box)
    and line2 → bottom track (white). A single-line file yields top only.
    Returns (top_path or None, bottom_path or None); temp files live in
    output/log/ and are overwritten on each burn.
    """
    with open(path, encoding="utf-8") as f:
        content = f.read().strip()
    tops, bottoms = [], []
    for block in content.split("\n\n"):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        ts, text = lines[1], [l.strip() for l in lines[2:] if l.strip()]
        if not text:
            continue
        tops.append((ts, text[0]))
        if len(text) > 1:
            bottoms.append((ts, text[1]))
    top_path, bottom_path = None, None
    if tops:
        top_path = os.path.join("output", "log", "_burn_top.srt")
        _write_srt(tops, top_path)
    if bottoms:
        bottom_path = os.path.join("output", "log", "_burn_bottom.srt")
        _write_srt(bottoms, bottom_path)
    rprint(f"[cyan]📝 Split {os.path.basename(path)} → "
           f"{len(tops)} top / {len(bottoms)} bottom lines[/cyan]")
    return top_path, bottom_path


def _parse_ffmpeg_time(t: str) -> float:
    """Parse ffmpeg out_time 'HH:MM:SS.mmm' (or microseconds int) to seconds."""
    t = t.strip()
    if not t or t in ('N/A', '-'):
        return 0.0
    if ':' not in t:
        try:
            return float(t) / 1_000_000  # out_time_ms
        except ValueError:
            return 0.0
    try:
        h, m, s = t.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    except ValueError:
        return 0.0


def merge_subtitles_to_video(tracks=None, log_callback=None):
    """Burn 1-2 subtitle tracks into the video.

    Args:
        tracks: list of 1-2 .srt paths. Track 1 uses the source (white)
            style, track 2 the translation (bottom, MarginV=27) style.
            Defaults to [output/src.srt, output/trans.srt].
        log_callback: optional progress_callback(step, detail, percent).
            With ffmpeg `-progress pipe:1` this streams real encode progress
            (percent + elapsed/total time).
    """
    from core._1_ytdlp import is_audio_only_input
    from core.utils.video_utils import get_media_duration
    if is_audio_only_input():
        rprint("[bold green]🎵 Audio-only input: skipping video merge. Subtitle files are ready in the `output` directory.[/bold green]")
        return

    video_file = find_video_files()
    os.makedirs(os.path.dirname(OUTPUT_VIDEO), exist_ok=True)

    # Check resolution
    if not load_key("burn_subtitles"):
        rprint("[bold yellow]Subtitles are not burned in. Skipping video generation. Use the SRT files directly.[/bold yellow]")
        return

    if tracks is None:
        tracks = [SRC_SRT, TRANS_SRT]
    tracks = [t for t in tracks if t]
    if not 1 <= len(tracks) <= 2:
        raise ValueError(f"Expected 1-2 subtitle tracks, got {len(tracks)}")
    for srt in tracks:
        if not os.path.exists(srt):
            rprint(f"[red]Subtitle file not found: {srt}[/red]")
            raise FileNotFoundError(srt)
    rprint(f"[bold green]🎬 Burning track(s): {', '.join(os.path.basename(t) for t in tracks)}[/bold green]")

    # Normalize to (top, bottom): a single bilingual file is split so line 1
    # gets the yellow-box style and line 2 the white style.
    if len(tracks) == 1:
        top_srt, bottom_srt = _split_bilingual_srt(tracks[0])
        if top_srt is None:
            raise ValueError(f"No usable subtitle entries in {tracks[0]}")
    else:
        top_srt, bottom_srt = tracks[0], tracks[1]

    video = cv2.VideoCapture(video_file)
    TARGET_WIDTH = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    TARGET_HEIGHT = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video.release()
    rprint(f"[bold green]Video resolution: {TARGET_WIDTH}x{TARGET_HEIGHT}[/bold green]")

    vf_parts = [
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease:flags=bicubic",
        f"pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2",
    ]
    if top_srt:
        vf_parts.append(_sub_filter(top_srt, TOP_STYLE))
    if bottom_srt:
        vf_parts.append(_sub_filter(bottom_srt, BOTTOM_STYLE))
    ffmpeg_cmd = ['ffmpeg', '-hide_banner', '-nostats', '-i', video_file, '-vf', ','.join(vf_parts)]

    # Build encoder flags (VideoToolbox or software fallback)
    _build_encoder_cmd(ffmpeg_cmd, video_file)

    ffmpeg_cmd.extend(['-y', OUTPUT_VIDEO])

    rprint(f"[bold blue]Executing FFmpeg command:[/bold blue] {' '.join(ffmpeg_cmd)}")

    rprint("🎬 Start merging subtitles to video...")
    start_time = time.time()

    total_dur = get_media_duration(video_file)
    if total_dur > 0:
        rprint(f"[cyan]⏱️ Source duration: {total_dur:.1f}s[/cyan]")

    def _report(detail, percent=None):
        if log_callback:
            log_callback(step="burn", detail=detail, percent=percent)

    _NOISY_PREFIXES = ('out_time_ms=', 'out_time=', 'progress=', 'frame=',
                       'Press [q]', 'Stream mapping', '  Stream #')
    _ERROR_KEYWORDS = ('error', 'failed', 'invalid', 'unable to', 'no such',
                       'not found', 'denied', 'permission', 'conversion failed',
                       'nothing was written', 'incorrect parameters')

    def _is_noisy(line):
        return line.startswith(_NOISY_PREFIXES)

    def _is_error_line(line):
        low = line.lower()
        return any(k in low for k in _ERROR_KEYWORDS)

    def _is_font_noise(line):
        # libass font fallback chatter (e.g. "Error opening font", fontselect
        # lines): non-fatal, encode continues with a fallback font. Keep in
        # terminal/log, but don't push to the UI progress slot.
        low = line.lower()
        return 'font' in low or 'glyph' in low or 'fontselect' in low

    # Always capture full ffmpeg output so failures are diagnosable.
    cmd = list(ffmpeg_cmd)
    use_progress = bool(log_callback and total_dur > 0)
    if use_progress:
        cmd += ['-progress', 'pipe:1']
    cmd[1:1] = ['-nostdin']  # never block on interactive stdin
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL,
                               text=True, bufsize=1)
    captured = []
    last_pct = -1
    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            captured.append(line)
            del captured[:-200]
            if line.startswith('out_time_ms=') or line.startswith('out_time='):
                if not use_progress:
                    continue
                cur = _parse_ffmpeg_time(line.split('=', 1)[1])
                pct = min(100.0, cur / total_dur * 100)
                if pct - last_pct >= 2 or pct >= 100:
                    last_pct = pct
                    _report(t("burn_progress_fmt").format(
                        pct=f"{pct:.0f}", cur=f"{cur:.0f}",
                        total=f"{total_dur:.0f}",
                        el=f"{time.time() - start_time:.0f}"), pct)
            elif line.startswith('progress=end'):
                _report(t("burn_progress_fmt").format(
                    pct="100", cur=f"{total_dur:.0f}",
                    total=f"{total_dur:.0f}",
                    el=f"{time.time() - start_time:.0f}"), 100)
            elif _is_error_line(line) and not _is_noisy(line) and not _is_font_noise(line):
                _report(f"⚠️ ffmpeg: {line[:300]}")
            elif not use_progress and not _is_noisy(line):
                # Batch/CLI path: keep ffmpeg output visible in terminal
                rprint(line)
        process.wait()
    except Exception as e:
        rprint(f"\n❌ Error occurred: {e}")
        if process.poll() is None:
            process.kill()
        raise

    if process.returncode == 0:
        rprint(f"\n✅ Done! Time taken: {time.time() - start_time:.2f} seconds")
        _report(t("burn_done_fmt").format(
            t=f"{time.time() - start_time:.1f}", out=OUTPUT_VIDEO), 100)
    else:
        tail = [l for l in captured[-40:] if not _is_noisy(l)]
        rprint(f"\n❌ FFmpeg exited with code {process.returncode}. Last output:")
        for l in tail:
            rprint(f"    {l[:300]}")
        try:
            os.makedirs("output/log", exist_ok=True)
            with open("output/log/ffmpeg_burn_last.log", "w", encoding="utf-8") as f:
                f.write(' '.join(cmd) + "\n\n" + "\n".join(captured))
            rprint("[yellow]Full ffmpeg output saved to output/log/ffmpeg_burn_last.log[/yellow]")
            _report(t("burn_fail_saved").format(
                path="output/log/ffmpeg_burn_last.log"))
            for l in tail:
                _report(f"  ffmpeg: {l[:300]}")
        except Exception:
            pass
        raise RuntimeError(f"FFmpeg exited with code {process.returncode}")

if __name__ == "__main__":
    merge_subtitles_to_video()