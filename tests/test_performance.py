
import time
import os
import sys
import mlx_whisper
# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.asr_backend.mlx_whisper_local import transcribe_audio, load_whisper_model
from core.utils import load_key

def test_performance(audio_path):
    if not os.path.exists(audio_path):
        print(f"Error: {audio_path} not found.")
        return

    model_name = load_key("whisper.model")
    print(f"Testing performance for model: {model_name}")
    
    print("\n--- Phase 1: With word_timestamps=True (Baseline) ---")
    start_t = time.time()
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=model_name,
        word_timestamps=True,
        clip_timestamps="0,60"
    )
    duration = time.time() - start_t
    print(f"Transcription with word_timestamps=True (60s) took {duration:.2f}s")
    
    print("\n--- Phase 3: With whisper-tiny (word_timestamps=False) ---")
    start_t = time.time()
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo="mlx-community/whisper-tiny",
        word_timestamps=False,
        clip_timestamps="0,60"
    )
    duration = time.time() - start_t
    print(f"Transcription with whisper-tiny (60s) took {duration:.2f}s")

    print("\n--- Phase 4: librosa load vs direct path (whisper-tiny) ---")
    import librosa
    start_t = time.time()
    audio_np, _ = librosa.load(audio_path, sr=16000, offset=0, duration=60)
    result = mlx_whisper.transcribe(
        audio_np,
        path_or_hf_repo="mlx-community/whisper-tiny",
        word_timestamps=False,
    )
    duration_np = time.time() - start_t
    print(f"Transcription with librosa+numpy took {duration_np:.2f}s")
    
    start_t = time.time()
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo="mlx-community/whisper-tiny",
        word_timestamps=False,
        clip_timestamps="0,60"
    )
    duration_path = time.time() - start_t
    print(f"Transcription with direct path took {duration_path:.2f}s")

if __name__ == "__main__":
    audio = "/Users/bytedance/VideoLingo/output/raw.mp3"
    test_performance(audio)
