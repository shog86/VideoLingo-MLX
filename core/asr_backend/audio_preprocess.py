import os, re, subprocess
import pandas as pd
from typing import Dict, List, Tuple
from pydub import AudioSegment
from core.utils import *
from core.utils.models import *
from pydub import AudioSegment
from pydub.silence import detect_silence
from pydub.utils import mediainfo
from rich import print as rprint

def _ffmpeg_has_encoder(encoder_name: str) -> bool:
    """Check if the current ffmpeg installation supports a given audio encoder."""
    try:
        result = subprocess.run(
            ['ffmpeg', '-encoders'], capture_output=True, text=True, timeout=10
        )
        return encoder_name in result.stdout
    except Exception:
        return False

def normalize_audio_volume(audio_path, output_path, target_db = -20.0, format = "wav"):
    audio = AudioSegment.from_file(audio_path)
    change_in_dBFS = target_db - audio.dBFS
    normalized_audio = audio.apply_gain(change_in_dBFS)
    normalized_audio.export(output_path, format=format)
    rprint(f"[green]✅ Audio normalized from {audio.dBFS:.1f}dB to {target_db:.1f}dB[/green]")
    return output_path

def convert_video_to_audio(video_file: str):
    os.makedirs(_AUDIO_DIR, exist_ok=True)
    if not os.path.exists(_RAW_AUDIO_FILE):
        rprint(f"[blue]🎬➡️🎵 Converting to high quality audio with FFmpeg ......[/blue]")
        if _ffmpeg_has_encoder('libmp3lame'):
            cmd = [
                'ffmpeg', '-y', '-i', video_file, '-vn',
                '-c:a', 'libmp3lame', '-b:a', '32k',
                '-ar', '16000', '-ac', '1',
                '-metadata', 'encoding=UTF-8', _RAW_AUDIO_FILE
            ]
        else:
            # Fallback: conda-forge ffmpeg often lacks libmp3lame.
            # Output as WAV (PCM) which all ffmpeg builds support.
            # Downstream readers (pydub, librosa) detect format by
            # file header, not extension, so .mp3 path with WAV content works.
            rprint("[yellow]⚠️ libmp3lame not found in ffmpeg, falling back to WAV (PCM) encoding[/yellow]")
            cmd = [
                'ffmpeg', '-y', '-i', video_file, '-vn',
                '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                '-f', 'wav', _RAW_AUDIO_FILE
            ]
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
        rprint(f"[green]🎬➡️🎵 Converted <{video_file}> to <{_RAW_AUDIO_FILE}> with FFmpeg\n[/green]")

def prepare_audio_for_asr(audio_file: str):
    os.makedirs(_AUDIO_DIR, exist_ok=True)
    if not os.path.exists(_RAW_AUDIO_FILE):
        rprint(f"[blue]🎵 Preparing uploaded audio for ASR with FFmpeg ......[/blue]")
        if _ffmpeg_has_encoder('libmp3lame'):
            cmd = [
                'ffmpeg', '-y', '-i', audio_file, '-vn',
                '-c:a', 'libmp3lame', '-b:a', '32k',
                '-ar', '16000', '-ac', '1',
                '-metadata', 'encoding=UTF-8', _RAW_AUDIO_FILE
            ]
        else:
            rprint("[yellow]⚠️ libmp3lame not found in ffmpeg, falling back to WAV (PCM) encoding[/yellow]")
            cmd = [
                'ffmpeg', '-y', '-i', audio_file, '-vn',
                '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                '-f', 'wav', _RAW_AUDIO_FILE
            ]
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
        rprint(f"[green]🎵 Prepared <{audio_file}> as <{_RAW_AUDIO_FILE}>\n[/green]")

def get_audio_duration(audio_file: str) -> float:
    """Get the duration of an audio file using ffmpeg."""
    cmd = ['ffmpeg', '-i', audio_file]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr = process.communicate()
    output = stderr.decode('utf-8', errors='ignore')
    
    try:
        duration_str = [line for line in output.split('\n') if 'Duration' in line][0]
        duration_parts = duration_str.split('Duration: ')[1].split(',')[0].split(':')
        duration = float(duration_parts[0])*3600 + float(duration_parts[1])*60 + float(duration_parts[2])
    except Exception as e:
        print(f"[red]❌ Error: Failed to get audio duration: {e}[/red]")
        duration = 0
    return duration

def split_audio(audio_file: str, target_len: float = 30*60, win: float = 60) -> List[Tuple[float, float]]:
    ## 在 [target_len-win, target_len+win] 区间内用 pydub 检测静默，切分音频
    rprint(f"[blue]🎙️ Starting audio segmentation {audio_file} {target_len} {win}[/blue]")
    audio = AudioSegment.from_file(audio_file)
    duration = float(mediainfo(audio_file)["duration"])
    if duration <= target_len + win:
        return [(0, duration)]
    segments, pos = [], 0.0
    safe_margin = 0.5  # 静默点前后安全边界，单位秒

    while pos < duration:
        if duration - pos <= target_len:
            segments.append((pos, duration)); break

        threshold = pos + target_len
        ws, we = int((threshold - win) * 1000), int((threshold + win) * 1000)
        
        # 获取完整的静默区域
        silence_regions = detect_silence(audio[ws:we], min_silence_len=int(safe_margin*1000), silence_thresh=-30)
        silence_regions = [(s/1000 + (threshold - win), e/1000 + (threshold - win)) for s, e in silence_regions]
        # 筛选长度足够（至少1秒）且位置适合的静默区域
        valid_regions = [
            (start, end) for start, end in silence_regions 
            if (end - start) >= (safe_margin * 2) and threshold <= start + safe_margin <= threshold + win
        ]
        
        if valid_regions:
            start, end = valid_regions[0]
            split_at = start + safe_margin  # 在静默区域起始点后0.5秒处切分
        else:
            rprint(f"[yellow]⚠️ No valid silence regions found for {audio_file} at {threshold}s, using threshold[/yellow]")
            split_at = threshold
            
        segments.append((pos, split_at)); pos = split_at

    rprint(f"[green]🎙️ Audio split completed {len(segments)} segments[/green]")
    return segments

def normalize_spacing(text: str) -> str:
    """Collapse all whitespace runs (2+/4+ spaces, tabs, etc.) to a single space.

    Whisper word-level output carries leading spaces (e.g. " hello"); naive
    joining then produces double/quadruple spaces in the final subtitles.
    Safe for CJK too: single spaces are preserved, runs are collapsed.
    """
    if not isinstance(text, str):
        return text
    return re.sub(r'\s+', ' ', text).strip()


# ---------------------------------------------------------------------------
# English transcription cleanup: filler words + broken hyphenated words
# e.g. "you know", "um", "uh" and "e -commerce" -> "e-commerce"
# ---------------------------------------------------------------------------

# Single-token fillers (interjections). Matched case-insensitively after
# stripping surrounding punctuation, e.g. "Um," -> "um" -> dropped.
FILLER_SINGLE = frozenset({
    'um', 'umm', 'ummm', 'uhm', 'uh', 'uhh', 'uhhh',
    'ah', 'er', 'erm', 'err', 'hmm', 'hm', 'mm', 'mhm',
})

# Multi-word discourse fillers handled as token sequences.
# "you know" / "i mean" are only dropped in filler position (comma-adjacent
# or clause boundary) so meaningful uses like "you know the answer" survive.
FILLER_PHRASES = (
    ('you', 'know'),
    ('i', 'mean'),
)

_PUNCT_RE = re.compile(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$')


def _stripped_lower(token: str) -> str:
    return _PUNCT_RE.sub('', token or '').lower()


def _has_attached_punct(token: str) -> bool:
    """True if token carries leading/trailing punctuation (e.g. 'know,')."""
    t = token or ''
    return bool(re.search(r'^[^A-Za-z0-9]|[^A-Za-z0-9]$', t.strip()))


def _is_english_transcription() -> bool:
    try:
        lang = load_key("whisper.language")
        if lang == 'auto':
            lang = load_key("whisper.detected_language")
        return (lang or '').lower().startswith('en')
    except Exception:
        return True  # fail-open: cleanup regexes are en-specific anyway


def fix_hyphen_spacing(text: str) -> str:
    """Repair Whisper word-join artefacts like 'e -commerce' -> 'e-commerce'.

    Only fixes unambiguous cases (space on ONE side of the hyphen, or a
    single-letter prefix like 'e - commerce'), leaving spaced dashes
    ('hello - world') untouched.
    """
    if not isinstance(text, str) or '-' not in text:
        return text
    # "e -commerce" / "well -known" (space before only)
    text = re.sub(r'(\w)\s+-(?=\w)', r'\1-', text)
    # "e- commerce" / "well- known" (space after only)
    text = re.sub(r'(?<=\w)-\s+(\w)', r'-\1', text)
    # single-letter prefix with spaces both sides: "e - commerce"
    text = re.sub(r'\b([A-Za-z])\s+-\s+([A-Za-z])', r'\1-\2', text)
    return text


def clean_text_fillers(text: str) -> str:
    """Text-level filler cleanup (safety net for segment-level ASR output).

    Removes comma-parenthesised fillers: ', um,', ', you know,', leading
    'You know, ' / 'Um, ' and trailing ', um'. Conservative by design.
    """
    if not isinstance(text, str) or not text.strip():
        return text
    single = '|'.join(sorted(FILLER_SINGLE, key=len, reverse=True))
    # ", um," / ", uh," -> ","  (also with periods)
    text = re.sub(r',\s*(?:' + single + r')\s*,', ',', text, flags=re.IGNORECASE)
    # ", you know," / ", i mean," -> ","
    text = re.sub(r',\s*you\s+know\s*,', ',', text, flags=re.IGNORECASE)
    text = re.sub(r',\s*i\s+mean\s*,', ',', text, flags=re.IGNORECASE)
    # leading "You know, " / "Um, " / "Uh, "
    text = re.sub(r'^(?:you\s+know|i\s+mean|' + single + r')\s*,\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^(?:you\s+know|i\s+mean|' + single + r')\s+', '', text, flags=re.IGNORECASE)
    # trailing ", you know" / ", um" (+ optional period)
    text = re.sub(r',\s*(?:you\s+know|i\s+mean|' + single + r')\s*([.?!]?)$', r'\1', text, flags=re.IGNORECASE)
    # leftover double commas / stray spaces
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    text = re.sub(r'\s+([,.?!])', r'\1', text)
    return text


def merge_hyphenated_words(df: pd.DataFrame) -> pd.DataFrame:
    """Merge word-rows split at hyphens: ['e','-','commerce'] -> ['e-commerce'].

    Timestamps span the merged tokens (start of first, end of last).
    Em/en dashes (—, –, spaced ' - ') are left alone.
    """
    if df is None or df.empty:
        return df
    rows = df.to_dict('records')
    merged = []
    i = 0
    n_merged = 0
    while i < len(rows):
        cur_raw = str(rows[i].get('text', '')).strip()
        cur_stripped = cur_raw.strip('"\'')

        # Case A: standalone "-" row between two word rows -> join all three
        if cur_stripped == '-' and merged and i + 1 < len(rows):
            nxt_raw = str(rows[i + 1].get('text', '')).strip().strip('"\'')
            prev = merged[-1]
            prev_raw = str(prev.get('text', '')).strip().strip('"\'')
            if prev_raw and nxt_raw and re.search(r'\w$', prev_raw) and re.search(r'^\w', nxt_raw):
                prev['text'] = f"{prev_raw}-{nxt_raw}"
                prev['end'] = rows[i + 1].get('end', prev.get('end'))
                n_merged += 1
                i += 2
                continue

        # Case B: hyphen attached on one side, e.g. "-commerce" or "well-"
        if cur_stripped.startswith('-') and len(cur_stripped) > 1 and merged:
            prev = merged[-1]
            prev_raw = str(prev.get('text', '')).strip().strip('"\'')
            tail = cur_stripped[1:]
            if prev_raw and re.search(r'\w$', prev_raw) and re.match(r'^\w', tail):
                prev['text'] = f"{prev_raw}-{tail}"
                prev['end'] = rows[i].get('end', prev.get('end'))
                n_merged += 1
                i += 1
                continue
        if cur_stripped.endswith('-') and len(cur_stripped) > 1 and i + 1 < len(rows):
            nxt_raw = str(rows[i + 1].get('text', '')).strip().strip('"\'')
            head = cur_stripped[:-1]
            if head and re.search(r'\w$', head) and nxt_raw and re.match(r'^\w', nxt_raw):
                rows[i] = {**rows[i], 'text': f"{head}-{nxt_raw}",
                           'end': rows[i + 1].get('end', rows[i].get('end'))}
                merged.append(rows[i])
                n_merged += 1
                i += 2
                continue

        merged.append(rows[i])
        i += 1

    if n_merged:
        rprint(f"[blue]🔗 Merged {n_merged} hyphen-split word(s) (e.g. 'e -commerce' → 'e-commerce').[/blue]")
    return pd.DataFrame(merged) if merged else df.iloc[0:0].copy()


def remove_filler_words_df(df: pd.DataFrame) -> pd.DataFrame:
    """Drop English filler word-rows (um/uh/you-know/…) while keeping timestamps.

    - Single fillers (um, uh, …) are dropped wherever they appear standalone.
    - 'you know' / 'i mean' are dropped only in filler position, i.e. when
      adjacent to punctuation or at a clause boundary, so that meaningful
      uses ('you know the answer') survive.
    Returns a new DataFrame (order preserved).
    """
    if df is None or df.empty:
        return df
    texts = df['text'].astype(str).tolist()
    stripped = [_stripped_lower(t.strip().strip('"')) for t in texts]
    drop = [False] * len(texts)

    for idx, s in enumerate(stripped):
        if s in FILLER_SINGLE:
            drop[idx] = True

    for idx in range(len(texts) - 1):
        if drop[idx] or drop[idx + 1]:
            continue
        if (stripped[idx], stripped[idx + 1]) not in FILLER_PHRASES:
            continue
        left_tok = texts[idx].strip().strip('"')
        right_tok = texts[idx + 1].strip().strip('"')
        # Only drop in filler position: adjacent to punctuation (", you know,",
        # "You know, ...", "..., you know.", "I mean, ..."). A bare
        # "you know the answer" (no commas) is meaningful and must survive.
        comma_context = (
            _has_attached_punct(left_tok) or _has_attached_punct(right_tok)
            or (idx > 0 and _has_attached_punct(texts[idx - 1].strip().strip('"')))
            or (idx + 2 < len(texts) and _has_attached_punct(texts[idx + 2].strip().strip('"')))
        )
        if comma_context:
            drop[idx] = True
            drop[idx + 1] = True

    n_dropped = sum(drop)
    if n_dropped:
        dropped_preview = [texts[k].strip().strip('"') for k, d in enumerate(drop) if d][:8]
        rprint(f"[blue]🧹 Removed {n_dropped} filler word(s): {dropped_preview}…[/blue]")
        df = df.loc[[not d for d in drop]].reset_index(drop=True)
    return df


def process_transcription(result: Dict) -> pd.DataFrame:
    all_words = []
    expect_capital = True
    for segment in result['segments']:
        # Get speaker_id, if not exists, set to None
        speaker_id = segment.get('speaker_id', None)

        words = segment.get('words')
        if not words:
            # Some ASR backends (e.g. ElevenLabs without word-level timestamps)
            # return segments without per-word entries. Synthesize a single
            # word from the segment text so downstream alignment still works.
            seg_text = (segment.get('text') or '').strip()
            if not seg_text:
                continue
            words = [{
                'word': seg_text,
                'start': segment.get('start'),
                'end': segment.get('end'),
            }]

        for word in words:
            # Check word length
            if len(word["word"]) > 30:
                rprint(f"[yellow]⚠️ Warning: Detected word longer than 30 characters, skipping: {word['word']}[/yellow]")
                continue
                
            # ! For French, we need to convert guillemets to empty strings
            word["word"] = word["word"].replace('»', '').replace('«', '')

            # Enforce sentence case: capitalize first letter if previous ended with punctuation
            # Check for leading space which is common in Whisper output
            curr_text = word["word"]
            clean_text = curr_text.lstrip()
            if clean_text and expect_capital:
                # Calculate leading whitespace
                leading_space = curr_text[:len(curr_text)-len(clean_text)]
                word["word"] = leading_space + clean_text[0].upper() + clean_text[1:]
            
            # Update expectation for next word
            # Check if current word ends with basic sentence delimiters
            if clean_text.strip().endswith(('.', '?', '!')):
                expect_capital = True
            else:
                expect_capital = False
            
            if 'start' not in word and 'end' not in word:
                if all_words:
                    # Assign the end time of the previous word as the start and end time of the current word
                    word_dict = {
                        'text': word["word"],
                        'start': all_words[-1]['end'],
                        'end': all_words[-1]['end'],
                        'speaker_id': speaker_id
                    }
                    all_words.append(word_dict)
                else:
                    # If it's the first word, look next for a timestamp then assign it to the current word
                    next_word = next((w for w in words if 'start' in w and 'end' in w), None)
                    if next_word:
                        word_dict = {
                            'text': word["word"],
                            'start': next_word["start"],
                            'end': next_word["end"],
                            'speaker_id': speaker_id
                        }
                        all_words.append(word_dict)
                    else:
                        raise Exception(f"No next word with timestamp found for the current word : {word}")
            else:
                # Normal case, with start and end times
                word_dict = {
                    'text': f'{word["word"]}',
                    'start': word.get('start', all_words[-1]['end'] if all_words else 0),
                    'end': word['end'],
                    'speaker_id': speaker_id
                }
                
                all_words.append(word_dict)
    
    return pd.DataFrame(all_words)

def save_results(df: pd.DataFrame):
    os.makedirs('output/log', exist_ok=True)

    # 1. Remove rows where 'text' is empty or just whitespace
    initial_rows = len(df)
    df = df[df['text'].str.strip().str.len() > 0]

    # 1b. Normalize spacing FIRST (before length filters): collapse 2+/4+
    #     whitespace runs to a single space so padded words aren't misjudged.
    before_spacing = df['text'].tolist()
    df['text'] = df['text'].apply(normalize_spacing)
    n_fixed = sum(1 for a, b in zip(before_spacing, df['text']) if a != b)
    if n_fixed:
        rprint(f"[blue]ℹ️ Normalized spacing in {n_fixed} word(s) (collapsed multi-space runs).[/blue]")

    # 1c. English-only cleanup: merge hyphen-split words + drop filler words.
    #     Must run BEFORE junk filters so "e -commerce" isn't misjudged and
    #     filler tokens don't shift downstream alignment.
    if _is_english_transcription():
        before_rows = len(df)
        df = merge_hyphenated_words(df)
        # Text-level safety net per row (fixes "-commerce", "e -" leftovers)
        df['text'] = df['text'].apply(lambda x: normalize_spacing(fix_hyphen_spacing(x)) if isinstance(x, str) else x)
        df = remove_filler_words_df(df)
        # Segment-level ASR (no word timestamps) packs a whole sentence into
        # one row — run the text-level filler regex as well.
        df['text'] = df['text'].apply(lambda x: normalize_spacing(clean_text_fillers(x)) if isinstance(x, str) else x)
        # Rows emptied by filler cleanup (e.g. a lone "Um,") are junk.
        df = df[df['text'].str.strip().str.len() > 0]
        if len(df) != before_rows:
            rprint(f"[blue]ℹ️ Transcription cleanup: {before_rows} → {len(df)} word row(s).[/blue]")
    
    # 2. Filter out common ASR hallucinations (e.g., repetitive characters)
    # Repetitive characters filter: if a single character is repeated more than 3 times
    def is_repetitive(text):
        text = text.strip()
        if len(text) > 3 and len(set(text)) == 1:
            return True
        return False
    
    df = df[~df['text'].apply(is_repetitive)]

    # 3. Filter out rows where start == end (usually hallucinations)
    df = df[df['start'] != df['end']]

    removed_rows = initial_rows - len(df)
    if removed_rows > 0:
        rprint(f"[blue]ℹ️ Removed {removed_rows} row(s) of empty or junk text.[/blue]")
    
    # 4. Check for and remove words longer than 30 characters
    long_words = df[df['text'].str.len() > 30]
    if not long_words.empty:
        rprint(f"[yellow]⚠️ Warning: Detected {len(long_words)} word(s) longer than 30 characters. These will be removed.[/yellow]")
        df = df[df['text'].str.len() <= 30]
    
    df['text'] = df['text'].apply(lambda x: f'"{x}"')

    # 5. Final validation: no 2+ consecutive spaces may remain.
    bad = int(df['text'].str.contains(r'\s{2,}', regex=True).sum())
    if bad:
        rprint(f"[yellow]⚠️ Validation: {bad} row(s) still contain 2+ consecutive spaces after normalization.[/yellow]")
    else:
        rprint("[green]✅ Spacing validation passed: no multi-space runs remain.[/green]")

    df.to_excel(_2_CLEANED_CHUNKS, index=False)
    rprint(f"[green]📊 Excel file saved to {_2_CLEANED_CHUNKS}[/green]")

def save_language(language: str):
    update_key("whisper.detected_language", language)