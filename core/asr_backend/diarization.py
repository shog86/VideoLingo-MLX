"""Pyannote speaker diarization, shared across ASR backends.

The MLX-Whisper backend embeds diarization inside mlx_whisper_local. Upstream
Qwen3-ASR does not diarize by default, so this helper is called from _2_asr to
keep speaker_id when the local backend is qwen. The pyannote pipeline instance
is cached at module scope to avoid re-creating (and re-downloading) it per clip.

Time line convention: `segments` carry GLOBAL timestamps (already offset by the
clip start). Each segment is mapped by its global [start, end) minus the clip's
`local_offset` onto the per-clip waveform decoded here.
"""

import subprocess
import time

import numpy as np
import torch
from rich import print as rprint

from core.utils import load_key

SAMPLE_RATE = 16000
_DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
_PIPELINE = None


def _get_pipeline():
    """Return a cached, device-placed pyannote pipeline (singleton)."""
    global _PIPELINE
    if _PIPELINE is None:
        from pyannote.audio import Pipeline

        token = load_key("api.huggingface_token")
        # pyannote.audio >= 4.0 renamed `use_auth_token` to `token`.
        try:
            pipeline = Pipeline.from_pretrained(_DIARIZATION_MODEL, token=token)
        except TypeError:
            pipeline = Pipeline.from_pretrained(_DIARIZATION_MODEL, use_auth_token=token)
        # Metal for Mac is handled via 'mps'; fall back to CPU otherwise.
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        pipeline.to(device)
        _PIPELINE = pipeline
    return _PIPELINE


def _decode_audio_mono(path, offset=0.0, duration=None):
    """Decode [offset, offset+duration) to 16 kHz mono float32 via the FFmpeg CLI.

    Same approach as the Qwen backend: avoids librosa's deadlock inside
    Streamlit's ScriptRunner thread and is robust to the video format quirks.
    """
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-ss", str(offset), "-i", str(path)]
    if duration is not None and duration > 0:
        cmd += ["-t", str(duration)]  # bound output length (after -i)
    cmd += ["-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"FFmpeg could not decode {path}: {stderr or f'exit code {proc.returncode}'}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def _best_speaker(diarization, seg_start, seg_end):
    """Majority-vote speaker over [seg_start, seg_end), or None if no overlap."""
    speakers = {}
    for turn, _, speaker in diarization.speaker_diarization.itertracks(yield_label=True):
        overlap_start = max(seg_start, turn.start)
        overlap_end = min(seg_end, turn.end)
        if overlap_end > overlap_start:
            speakers[speaker] = speakers.get(speaker, 0.0) + (overlap_end - overlap_start)
    if not speakers:
        return None
    return max(speakers, key=speakers.get)


def attach_speakers_to_segments(waveform, segments, local_offset=0.0):
    """Assign each global-time segment a speaker_id using the given waveform.

    `local_offset` is the clip's start second; segment times are global, so each
    is compared at (start - local_offset, end - local_offset). On any failure all
    segments fall back to SPEAKER_00 (mirrors mlx_whisper_local behavior).
    """
    default_id = "SPEAKER_00"
    try:
        diarization = _get_pipeline()(
            {"waveform": torch.from_numpy(waveform).unsqueeze(0), "sample_rate": SAMPLE_RATE}
        )
    except Exception as e:
        rprint(f"[red]⚠️ Diarization failed or skipped: {e}[/red]")
    else:
        for segment in segments:
            speaker = _best_speaker(
                diarization,
                segment.get("start", 0.0) - local_offset,
                segment.get("end", 0.0) - local_offset,
            )
            segment["speaker_id"] = speaker if speaker else "UNKNOWN"
        return segments

    for segment in segments:
        segment["speaker_id"] = default_id
    return segments


def diarize_file_segments(audio_file, offset, segments):
    """Decode [offset, end-of-clip) and attach speakers to global-time segments.

    Used by the qwen backend path to keep speaker_id without WhisperX. Returns
    segments (with speaker_id) unchanged; never raises diarization errors.
    """
    t0 = time.time()
    try:
        duration = 0.0
        # Recover clip end from the last segment for a bounded decode.
        if segments:
            duration = max(seg.get("end", 0.0) for seg in segments) - offset
        waveform = _decode_audio_mono(audio_file, offset=offset, duration=max(duration, 0.0))
        segments = attach_speakers_to_segments(waveform, segments, local_offset=offset)
    except Exception as e:
        rprint(f"[red]⚠️ Diarization failed or skipped: {e}[/red]")
        for segment in segments:
            segment["speaker_id"] = "SPEAKER_00"
    rprint(f"[cyan]⏱️ Diarization time:[/cyan] {time.time() - t0:.2f}s")
    return segments