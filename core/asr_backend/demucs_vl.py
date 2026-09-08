import os
import torch
from rich.console import Console
from rich import print as rprint
from demucs.pretrained import get_model
from demucs.audio import save_audio
from torch.cuda import is_available as is_cuda_available
from typing import Optional
from demucs.api import Separator
from demucs.apply import BagOfModels
import gc
from core.utils.models import *
from translations.translations import translate as t

class PreloadedSeparator(Separator):
    def __init__(self, model: BagOfModels, shifts: int = 1, overlap: float = 0.25,
                 split: bool = True, segment: Optional[int] = None, jobs: int = 0):
        self._model, self._audio_channels, self._samplerate = model, model.audio_channels, model.samplerate
        device = "cuda" if is_cuda_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self.update_parameter(device=device, shifts=shifts, overlap=overlap, split=split,
                            segment=segment, jobs=jobs, progress=True, callback=None, callback_arg=None)

def demucs_audio(progress_callback=None):
    def _report(pct, key):
        if progress_callback:
            try:
                progress_callback(step="demucs", detail=t(key), percent=pct)
            except Exception:
                pass
    if os.path.exists(_VOCAL_AUDIO_FILE) and os.path.exists(_BACKGROUND_AUDIO_FILE):
        rprint(f"[yellow]⚠️ {_VOCAL_AUDIO_FILE} and {_BACKGROUND_AUDIO_FILE} {t('demucs_skip_suffix')}[/yellow]")
        _report(100, "asr_demucs")
        return
    
    console = Console()
    os.makedirs(_AUDIO_DIR, exist_ok=True)
    
    _report(5, "demucs_loading")
    console.print(f"🤖 {t('demucs_loading')}...")
    model = get_model('htdemucs')
    separator = PreloadedSeparator(model=model, shifts=0, overlap=0.25)
    
    _report(20, "demucs_separating")
    console.print(f"🎵 {t('demucs_separating')}...")
    _, outputs = separator.separate_audio_file(_RAW_AUDIO_FILE)
    
    kwargs = {"samplerate": model.samplerate, "bitrate": 128, "preset": 2, 
              "clip": "rescale", "as_float": False, "bits_per_sample": 16}
    
    _report(70, "demucs_saving_vocals")
    console.print(f"🎤 {t('demucs_saving_vocals')}...")
    save_audio(outputs['vocals'].cpu(), _VOCAL_AUDIO_FILE, **kwargs)
    
    _report(85, "demucs_saving_bg")
    console.print(f"🎹 {t('demucs_saving_bg')}...")
    background = sum(audio for source, audio in outputs.items() if source != 'vocals')
    save_audio(background.cpu(), _BACKGROUND_AUDIO_FILE, **kwargs)
    
    # Clean up memory
    del outputs, background, model, separator
    gc.collect()
    
    _report(100, "demucs_done")
    console.print(f"[green]✨ {t('demucs_done')}[/green]")

if __name__ == "__main__":
    demucs_audio()
