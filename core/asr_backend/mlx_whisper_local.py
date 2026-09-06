import os
import time
import torch
import mlx_whisper
from pyannote.audio import Pipeline
from rich import print as rprint
from core.utils import *
import numpy as np
import librosa
from translations.translations import translate as t

# Load Hugging Face token from config
HF_TOKEN = load_key("api.huggingface_token")
MODEL_DIR = load_key("model_dir")

# Global model cache (internal to mlx-whisper, but we can trigger it)
def load_whisper_model(model_name):
    """Trigger MLX-Whisper's internal ModelHolder cache."""
    rprint(f"[cyan]📥 Ensuring MLX-Whisper model is loaded: {model_name}...[/cyan]")
    # We use transcribe with a tiny bit of silence to trigger the internal ModelHolder cache
    # This is a bit of a hack but ensures the model is in memory for subsequent calls.
    # Alternatively, we just rely on the first call of transcribe_audio to do it.
    pass

def transcribe_audio(raw_audio_file, vocal_audio_file, start, end, model=None, progress_callback=None):
    """
    Transcribe audio using MLX-Whisper and diarize using pyannote-audio.
    """
    rprint(f"[cyan]🚀 Starting MLX-Whisper + Pyannote for segment {start:.2f}s to {end:.2f}s...[/cyan]")
    
    # 1. Load MLX-Whisper model
    # Note: MLX-Whisper uses the model name directly, it handles Apple Silicon optimization.
    whisper_model_name = load_key("whisper.model")
    if load_key("whisper.language") == 'zh':
        # For Chinese, we might want a specific model, but large-v3-turbo / large-v3 usually works well in MLX
        pass 
    
    # Transcription
    transcribe_start_time = time.time()
    
    # Load audio segment for MLX
    audio_segment, _ = librosa.load(raw_audio_file, sr=16000, offset=start, duration=end - start)
    
    rprint("[bold green]🎤 Transcribing with MLX-Whisper...[/bold green]")
    if progress_callback:
        progress_callback(step="whisper", detail=t("mlx_whisper"))
    
    # MLX-Whisper's internal ModelHolder will handle caching the model weights 
    # based on the whisper_model_name string.

    result = mlx_whisper.transcribe(
        audio_segment,
        path_or_hf_repo=whisper_model_name,
        word_timestamps=True,
        verbose=False
    )
    
    transcribe_time = time.time() - transcribe_start_time
    rprint(f"[cyan]⏱️ Transcription time:[/cyan] {transcribe_time:.2f}s")

    # 2. Diarization with Pyannote
    diarization_start_time = time.time()
    rprint("[bold green]👥 Diarizing with Pyannote-audio...[/bold green]")
    if progress_callback:
        progress_callback(step="diarize", detail=t("mlx_diarize"))
    
    try:
        # pyannote.audio >= 4.0 renamed `use_auth_token` to `token`
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                token=HF_TOKEN
            )
        except TypeError:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=HF_TOKEN
            )
        # Move to GPU if available (Metal for Mac is usually handled via 'cpu' or auto in pyannote, 
        # but pyannote 3.1 often prefers torch device)
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        pipeline.to(device)
        
        # Diarize
        # We need to save the segment to a temporary file because pyannote expects a file path or dict
        # or we can pass the waveform directly
        waveform = torch.from_numpy(audio_segment).unsqueeze(0)
        diarization = pipeline({"waveform": waveform, "sample_rate": 16000})
        
        diarization_time = time.time() - diarization_start_time
        rprint(f"[cyan]⏱️ Diarization time:[/cyan] {diarization_time:.2f}s")
        
        # 3. Assign Speakers to Segments
        # Mapping: for each segment/word in whisper result, find the majority speaker
        for segment in result['segments']:
            seg_start = segment['start']
            seg_end = segment['end']
            
            # Find speakers in this time range
            speakers_in_range = []
            for turn, _, speaker in diarization.speaker_diarization.itertracks(yield_label=True):
                # Check overlap
                overlap_start = max(seg_start, turn.start)
                overlap_end = min(seg_end, turn.end)
                if overlap_end > overlap_start:
                    speakers_in_range.append((speaker, overlap_end - overlap_start))
            
            if speakers_in_range:
                # Majority vote
                speaker_durations = {}
                for spk, dur in speakers_in_range:
                    speaker_durations[spk] = speaker_durations.get(spk, 0) + dur
                best_speaker = max(speaker_durations, key=speaker_durations.get)
                segment['speaker_id'] = best_speaker
            else:
                segment['speaker_id'] = "UNKNOWN"
                
    except Exception as e:
        rprint(f"[red]⚠️ Diarization failed or skipped: {e}[/red]")
        for segment in result['segments']:
            segment['speaker_id'] = "SPEAKER_00"

    # 4. Adjust timestamps to global timeline
    for segment in result['segments']:
        segment['start'] += start
        segment['end'] += start
        if 'words' in segment:
            for word in segment['words']:
                word['start'] += start
                word['end'] += start
                
    return result
