from core.utils import *
from core.asr_backend.demucs_vl import demucs_audio
from core.asr_backend.audio_preprocess import process_transcription, convert_video_to_audio, prepare_audio_for_asr, split_audio, save_results, normalize_audio_volume
from core._1_ytdlp import find_media_file
from core.utils.models import *
from translations.translations import translate as t

@check_file_exists(_2_CLEANED_CHUNKS)
def transcribe(progress_callback=None):
    # 1. prepare audio
    if progress_callback:
        progress_callback(step="prepare", detail=t("asr_prepare"), percent=0)
    media_file, media_type = find_media_file()
    if media_type == "video":
        convert_video_to_audio(media_file)
    else:
        prepare_audio_for_asr(media_file)

    # 2. Demucs vocal separation:
    if load_key("demucs"):
        if progress_callback:
            progress_callback(step="demucs", detail=t("asr_demucs"), percent=10)
        def _demucs_sub(step=None, detail=None, percent=None):
            if progress_callback:
                if percent is None:
                    progress_callback(step=step or "demucs", detail=detail or t("asr_demucs"), percent=None)
                else:
                    # Demucs occupies the 10-20 slice of the ASR 0-100 range.
                    progress_callback(step=step or "demucs", detail=detail or t("asr_demucs"),
                                      percent=10 + float(percent) * 10 / 100.0)
        demucs_audio(progress_callback=_demucs_sub)
        vocal_audio = normalize_audio_volume(_VOCAL_AUDIO_FILE, _VOCAL_AUDIO_FILE, format="mp3")
    else:
        vocal_audio = _RAW_AUDIO_FILE

    # 3. Extract audio
    if progress_callback:
        progress_callback(step="split", detail=t("asr_split"), percent=20)
    segments = split_audio(_RAW_AUDIO_FILE)
    
    # 4. Transcribe audio by clips
    all_results = []
    runtime = load_key("whisper.runtime")
    if runtime == "mlx":
        from core.asr_backend.mlx_whisper_local import transcribe_audio as ts, load_whisper_model
        rprint("[cyan]🎤 Transcribing audio with MLX-Whisper (Mac Optimized)...[/cyan]")
        whisper_model_name = load_key("whisper.model")
        load_whisper_model(whisper_model_name)
    elif runtime == "elevenlabs":
        from core.asr_backend.elevenlabs_asr import transcribe_audio_elevenlabs as ts
        rprint("[cyan]🎤 Transcribing audio with ElevenLabs API...[/cyan]")
    else:
        # Fallback to MLX if specified runtime is missing or legacy
        from core.asr_backend.mlx_whisper_local import transcribe_audio as ts, load_whisper_model
        rprint(f"[yellow]⚠️ Runtime '{runtime}' is no longer supported on this Mac-optimized version. Falling back to MLX...[/yellow]")
        whisper_model_name = load_key("whisper.model")
        load_whisper_model(whisper_model_name)

    total_segments = len(segments)
    for i, (start, end) in enumerate(segments):
        if progress_callback:
            pct = 25 + int((i / total_segments) * 55)
            progress_callback(step="transcribe", detail=t("asr_transcribe_fmt").format(
                i=i+1, n=total_segments, s=f"{start:.1f}", e=f"{end:.1f}"), percent=pct)
        result = ts(_RAW_AUDIO_FILE, vocal_audio, start, end)
        all_results.append(result)
    
    # 5. Combine results
    if progress_callback:
        progress_callback(step="combine", detail=t("asr_combine"), percent=85)
    combined_result = {'segments': []}
    for result in all_results:
        combined_result['segments'].extend(result['segments'])
    
    # 6. Process df
    if progress_callback:
        progress_callback(step="process", detail=t("asr_process"), percent=90)
    df = process_transcription(combined_result)
    save_results(df)
    if progress_callback:
        progress_callback(step="done", detail=t("asr_done"), percent=100)
        
if __name__ == "__main__":
    transcribe()