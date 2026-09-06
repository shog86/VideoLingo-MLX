from pyannote.audio import Pipeline
import torch
import time
import sys
import os
import yaml

def load_token():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    return config.get("api", {}).get("huggingface_token", "")

def test_diarization(audio_path):
    token = load_token()
    if not token or "YOUR_HF_TOKEN" in token:
        print("Error: HuggingFace token not found or not set in config.yaml.")
        return

    if not os.path.exists(audio_path):
        print(f"Error: {audio_path} not found.")
        return

    print(f"Testing Pyannote Diarization with {audio_path}...")
    start_time = time.time()
    
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token
        )
        
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        print(f"Using device: {device}")
        pipeline.to(device)
        
        diarization = pipeline(audio_path)
        
        end_time = time.time()
        print(f"Diarization completed in {end_time - start_time:.2f} seconds.")
        
        for turn, _, speaker in diarization.speaker_diarization.itertracks(yield_label=True):
            print(f"start={turn.start:.1f}s stop={turn.end:.1f}s speaker_{speaker}")
            # Just print first few for testing
            if turn.start > 60:
                print("...")
                break
                
    except Exception as e:
        print(f"Error during diarization: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/test_diarization.py <audio_file_path>")
    else:
        test_diarization(sys.argv[1])
