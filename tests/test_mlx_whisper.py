import mlx_whisper
import time
import sys
import os

def test_transcribe(audio_path):
    if not os.path.exists(audio_path):
        print(f"Error: {audio_path} not found.")
        return

    print(f"Testing MLX-Whisper with {audio_path}...")
    start_time = time.time()
    
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
        word_timestamps=True
    )
    
    end_time = time.time()
    print(f"Transcription completed in {end_time - start_time:.2f} seconds.")
    print(f"Detected Language: {result.get('language', 'unknown')}")
    
    # Check for word timestamps
    if 'segments' in result and len(result['segments']) > 0:
        if 'words' in result['segments'][0]:
            print("Successfully retrieved word-level timestamps.")
            print(f"First word: {result['segments'][0]['words'][0]}")
        else:
            print("Warning: Word-level timestamps NOT found in output.")
    else:
        print("Error: No segments found in output.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/test_mlx_whisper.py <audio_file_path>")
    else:
        test_transcribe(sys.argv[1])
