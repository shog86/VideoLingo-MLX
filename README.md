<div align="center">

<img src="/docs/logo.png" alt="VideoLingo-MLX Logo" height="140">

# Connect the World, Frame by Frame

<a href="https://trendshift.io/repositories/12200" target="_blank"><img src="https://trendshift.io/api/badge/repositories/12200" alt="Huanshere%2FVideoLingo | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

[**English**](/README.md)｜[**简体中文**](/translations/README.zh.md)｜[**繁體中文**](/translations/README.zh-TW.md)｜[**日本語**](/translations/README.ja.md)｜[**Español**](/translations/README.es.md)｜[**Русский**](/translations/README.ru.md)｜[**Français**](/translations/README.fr.md)

</div>

> **ℹ️ VideoLingo-MLX** is a fork of [**Huanshere/VideoLingo**](https://github.com/Huanshere/VideoLingo) (Apache 2.0), focused on **Apple Silicon (MLX) optimization**. Upstream features are fully preserved, and our local optimizations are listed in [VideoLingo-MLX Optimizations](#-videolingo-mlx-optimizations).

## 🌟 Overview

VideoLingo-MLX is a Mac (Apple Silicon / MLX) optimized fork of VideoLingo, an all-in-one video translation, localization, and dubbing tool aimed at generating Netflix-quality subtitles. It eliminates stiff machine translations and multi-line subtitles while adding high-quality dubbing, enabling global knowledge sharing across language barriers.

Key features:
- 🎥 YouTube video download via yt-dlp

- **🎙️ Word-level and Low-illusion subtitle recognition with MLX-Whisper (Mac) or WhisperX**

- **📝 NLP and AI-powered subtitle segmentation**

- **📚 Custom + AI-generated terminology for coherent translation**

- **🔄 3-step Translate-Reflect-Adaptation for cinematic quality**

- **✅ Netflix-standard, Single-line subtitles Only**

- **🗣️ Dubbing with GPT-SoVITS, Azure, OpenAI, and more**

- 🚀 One-click startup and processing in Streamlit

- 🌍 Multi-language support in Streamlit UI

- 📝 Detailed logging with progress resumption

- 🎵 Enhanced audio processing with pydub for better audio splitting

Difference from similar projects: **Single-line subtitles only, superior translation quality, seamless dubbing experience**

## 🎥 Demo

<table>
<tr>
<td width="33%">

### Dual Subtitles
---
https://github.com/user-attachments/assets/a5c3d8d1-2b29-4ba9-b0d0-25896829d951

</td>
<td width="33%">

### Cosy2 Voice Clone
---
https://github.com/user-attachments/assets/e065fe4c-3694-477f-b4d6-316917df7c0a

</td>
<td width="33%">

### GPT-SoVITS with my voice
---
https://github.com/user-attachments/assets/47d965b2-b4ab-4a0b-9d08-b49a7bf3508c

</td>
</tr>
</table>

### Language Support

**Input Language Support(more to come):**

🇺🇸 English 🤩 | 🇷🇺 Russian 😊 | 🇫🇷 French 🤩 | 🇩🇪 German 🤩 | 🇮🇹 Italian 🤩 | 🇪🇸 Spanish 🤩 | 🇯🇵 Japanese 😐 | 🇨🇳 Chinese* 😊

> *Chinese uses a separate punctuation-enhanced whisper model, for now...

**Translation supports all languages, while dubbing language depends on the chosen TTS method.**

## 🔄 Recent Updates

- **Improved Installation**: Added error handling to prevent initialization failures on first install
- **Better Unicode Support**: Fixed Chinese and other non-ASCII character handling in translation prompts
- **Enhanced Term Extraction**: Improved proper noun translation accuracy
- **Audio Processing**: Upgraded to pydub for more reliable audio splitting
- **Mac Optimization**: Migrated to MLX-Whisper and Pyannote-audio for significantly faster performance on Apple Silicon.
- **Filler Word Removal**: Automatically recognizes and filters verbal tics like "um", "uh", "right" in transcriptions.
- **UI Improvements**: Added JSON format support toggle in LLM settings and one-click startup scripts.

## ⚡ VideoLingo-MLX Optimizations

Local changes on top of the upstream [Huanshere/VideoLingo](https://github.com/Huanshere/VideoLingo) repository:

- **MLX-Whisper local backend**: New `core/asr_backend/mlx_whisper_local.py` with a local MLX-Whisper ASR pipeline (`tests/test_mlx_whisper.py`), avoiding cloud dependency on Apple Silicon.
- **uv-based installer**: Switched to `uv` for dependency management (`uv.lock`, `run_installer.sh`, `OneKeyStart.sh`) with a streamlined `install.py`; removed the old Docker/launcher paths.
- **Rewritten Streamlit entry**: `st.py` reworked with pydub-based audio handling, phase progress resume, and dual-tab (subtitles / dubbing) layout.
- **Extra verification suites**: `tests/test_diarization.py`, `tests/test_fix_translation_again.py`, `tests/test_performance.py`, `tests/verify_video_params.py`.
- **i18n rework**: refreshed translation tables (`translations/*.json`, `translations/translations.py`) and zh-TW support.

## Installation

> **Note:** FFmpeg is required. Please install it via Homebrew:
> - macOS: ```brew install ffmpeg``` (via [Homebrew](https://brew.sh/))

1. Clone the repository

```bash
git clone https://github.com/shog86/VideoLingo-MLX.git
cd VideoLingo-MLX
```

2. Install dependencies (requires `conda`)

```bash
bash run_installer.sh
```

3. Start the application
```bash
streamlit run st.py
```

## APIs
VideoLingo-MLX supports OpenAI-Like API format and various TTS interfaces:
- LLM: `claude-3-5-sonnet`, `gpt-4.1`, `deepseek-v3`, `gemini-2.0-flash`, ... (sorted by performance, be cautious with gemini-2.5-flash...)
- Whisper: Run MLX-Whisper locally (recommended for Mac), or use ElevenLabs ASR API.
- TTS: `azure-tts`, `openai-tts`, `siliconflow-fishtts`, **`fish-tts`**, `GPT-SoVITS`, `edge-tts`, `*custom-tts`(You can modify your own TTS in custom_tts.py!)

> **Note:** VideoLingo-MLX works with **[302.ai](https://gpt302.saaslink.net/C2oHR9)** - one API key for all services (LLM, WhisperX, TTS). Or run locally with Ollama and Edge-TTS for free, no API needed!

> **Important:** For multi-character diarization, you must:
> 1. Create a [Hugging Face Access Token](https://hf.co/settings/tokens).
> 2. Accept terms for [pyannote/speaker-diarization-3.1](https://hf.co/pyannote/speaker-diarization-3.1) and [pyannote/segmentation-3.0](https://hf.co/pyannote/segmentation-3.0).
> 3. Enter your token in the Streamlit sidebar or `config.yaml`.

For detailed installation, API configuration, and batch mode instructions, please refer to the documentation: [English](/docs/pages/docs/start.en-US.md) | [中文](/docs/pages/docs/start.zh-CN.md)

## Current Limitations

1. Whisper transcription performance may be affected by video background noise. For videos with loud background music, please enable Voice Separation Enhancement.

2. Using weaker models can lead to errors during processes due to strict JSON format requirements for responses (tried my best to prompt llm😊). If this error occurs, please delete the `output` folder and retry with a different LLM.

3. The dubbing feature may not be 100% perfect due to differences in speech rates and intonation between languages.

4. **Multi-character dubbing** is now supported via Pyannote diarization (experimental).

## 📄 License

This project is licensed under the Apache 2.0 License. Special thanks to the following open source projects for their contributions:

[MLX-Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper), [pyannote-audio](https://github.com/pyannote/pyannote-audio), [whisperX](https://github.com/m-bain/whisperX), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [json_repair](https://github.com/mangiucugna/json_repair), [BELLE](https://github.com/LianjiaTech/BELLE)

## 📬 Contact Me

- Submit [Issues](https://github.com/shog86/VideoLingo-MLX/issues) or [Pull Requests](https://github.com/shog86/VideoLingo-MLX/pulls) on GitHub
- Upstream project: [Huanshere/VideoLingo](https://github.com/Huanshere/VideoLingo)

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=shog86/VideoLingo-MLX&type=Timeline)](https://star-history.com/#shog86/VideoLingo-MLX&Timeline)

---

<p align="center">If you find VideoLingo-MLX helpful, please give us a ⭐️!</p>
