<div align="center">

<img src="/docs/logo.png" alt="VideoLingo Logo" height="140">

# 连接世界每一帧

<a href="https://trendshift.io/repositories/12200" target="_blank"><img src="https://trendshift.io/api/badge/repositories/12200" alt="Huanshere%2FVideoLingo | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

[**English**](/README.md)｜[**简体中文**](/translations/README.zh.md)｜[**繁體中文**](/translations/README.zh-TW.md)｜[**日本語**](/translations/README.ja.md)｜[**Español**](/translations/README.es.md)｜[**Русский**](/translations/README.ru.md)｜[**Français**](/translations/README.fr.md)

**QQ群：875297969**

</div>

## 🌟 简介（[在线体验！](https://videolingo.io)）

VideoLingo 是一站式视频翻译本地化配音工具，能够一键生成 Netflix 级别的高质量字幕，告别生硬机翻，告别多行字幕，还能加上高质量的克隆配音，让全世界的知识能够跨越语言的障碍共享。

主要特点和功能：
- 🎥 使用 yt-dlp 从 Youtube 链接下载视频

- **🎙️ 使用 MLX-Whisper (Mac) 或 WhisperX 进行单词级和低幻觉字幕识别**

- **📝 使用 NLP 和 AI 进行字幕分割**

- **📚 自定义 + AI 生成术语库，保证翻译连贯性**

- **🔄 三步直译、反思、意译，实现影视级翻译质量**

- **✅ 按照 Netflix 标准检查单行长度，绝无双行字幕**

- **🗣️ 支持 GPT-SoVITS、Azure、OpenAI 等多种配音方案**

- 🚀 一键启动，在 streamlit 中一键出片

- 🌍 多语言支持就绪的 streamlit UI

- 📝 详细记录每步操作日志，支持随时中断和恢复进度

与同类项目相比的优势：**绝无多行字幕，最佳的翻译质量，无缝的配音体验**

## 🎥 演示

<table>
<tr>
<td width="33%">

### 双语字幕
---
https://github.com/user-attachments/assets/a5c3d8d1-2b29-4ba9-b0d0-25896829d951

</td>
<td width="33%">

### Cosy2 声音克隆
---
https://github.com/user-attachments/assets/e065fe4c-3694-477f-b4d6-316917df7c0a

</td>
<td width="33%">

### GPT-SoVITS 配音
---
https://github.com/user-attachments/assets/47d965b2-b4ab-4a0b-9d08-b49a7bf3508c

</td>
</tr>
</table>

### 语言支持

**输入语言支持：**

🇺🇸 英语 🤩  |  🇷🇺 俄语 😊  |  🇫🇷 法语 🤩  |  🇩🇪 德语 🤩  |  🇮🇹 意大利语 🤩  |  🇪🇸 西班牙语 🤩  |  🇯🇵 日语 😐  |  🇨🇳 中文* 😊

> *中文使用单独的标点增强后的 whisper 模型

**翻译语言支持所有语言，配音语言取决于选取的TTS。**

## 🔄 最近更新

- **Mac 优化**：全面迁移至 MLX-Whisper 和 Pyannote-audio 3.1，在苹果芯片（Apple Silicon）上速度极快。
- **口癖过滤**：转录时通过引导词（Initial Prompt）自动识别并过滤“嗯”、“就是”、“那个”等啰嗦词汇。
- **一键运行**：新增 Mac/Linux 端一键启动脚本 `OneKeyStart.sh`。
- **安装增强**：`install.py` 现已支持在安装阶段预下载重型 AI 模型。
- **兼容性修复**：全面支持 Python 3.13 并修复了 Demucs/Spacy 的安装冲突。

## 安装

遇到问题？在[**这里**](https://share.fastgpt.in/chat/share?shareId=066w11n3r9aq6879r4z0v9rh)与我们的免费在线AI助手交流获取帮助。

> **注意:** 在 Windows 上使用 NVIDIA GPU 加速需要先完成以下步骤:
> 1. 安装 [CUDA Toolkit 12.6](https://developer.download.nvidia.com/compute/cuda/12.6.0/local_installers/cuda_12.6.0_560.76_windows.exe)
> 2. 安装 [CUDNN 9.3.0](https://developer.download.nvidia.com/compute/cudnn/9.3.0/local_installers/cudnn_9.3.0_windows.exe)
> 3. 将 `C:\Program Files\NVIDIA\CUDNN\v9.3\bin\12.6` 添加到系统环境变量 PATH 中
> 4. 重启电脑

> **注意:** FFmpeg 是必需的，请通过包管理器安装：
> - Windows：```choco install ffmpeg```（通过 [Chocolatey](https://chocolatey.org/)）
> - macOS：```brew install ffmpeg```（通过 [Homebrew](https://brew.sh/)）
> - Linux：```sudo apt install ffmpeg```（Debian/Ubuntu）

1. 克隆仓库

```bash
git clone https://github.com/Huanshere/VideoLingo.git
cd VideoLingo
```

2. 安装依赖（需要 `python>=3.10`）

```bash
conda create -n videolingo python=3.13 -y
conda activate videolingo
python install.py   # 现已支持可选的模型预下载！
```

3. 启动应用
- Mac/Linux 用户：
```bash
./OneKeyStart.sh
```
- 或手动启动：
```bash
streamlit run st.py
```

### Docker
还可以选择使用 Docker（要求 CUDA 12.4 和 NVIDIA Driver 版本 >550），详见[Docker文档](/docs/pages/docs/docker.zh-CN.md)：

```bash
docker build -t videolingo .
docker run -d -p 8501:8501 --gpus all videolingo
```

## API
本项目支持 OpenAI-Like 格式的 api 和多种配音接口：
- LLM: `claude-3-5-sonnet`, `gpt-4.1`, `deepseek-v3`, `gemini-2.0-flash`, ...（按效果排序）
- Whisper: 在 Mac 上推荐使用本地 MLX-Whisper，或使用 ElevenLabs ASR API
- TTS: `azure-tts`, `openai-tts`, `siliconflow-fishtts`, **`fish-tts`**, `GPT-SoVITS`, `edge-tts`, `*custom-tts`(你可以在 custom_tts.py 中自定义 TTS!)

> **注意：** VideoLingo 现已与 **[302.ai](https://gpt302.saaslink.net/C2oHR9)** 集成，**一个 API KEY** 即可同时支持 LLM、WhisperX 和 TTS！同时也支持完全本地部署，使用 Ollama 作为 LLM 和 Edge-TTS 作为配音，无需云端 API！

> **重要：** 为了进行多角色识别，你必须：
> 1. 创建一个 [Hugging Face Access Token](https://hf.co/settings/tokens)。
> 2. 在 [pyannote/speaker-diarization-3.1](https://hf.co/pyannote/speaker-diarization-3.1) 和 [pyannote/segmentation-3.0](https://hf.co/pyannote/segmentation-3.0) 页面接受许可协议。
> 3. 在 Streamlit 侧边栏或 `config.yaml` 中输入你的 token。

详细的安装、API 配置、批量说明可以参见文档：[English](/docs/pages/docs/start.en-US.md) | [简体中文](/docs/pages/docs/start.zh-CN.md)

## 当前限制
1. Whisper 转录效果可能受到视频背景声影响。对于背景音乐较大的视频，请开启人声分离增强。
2. 使用较弱模型时容易在中间过程报错，这是因为对响应的 json 格式要求较为严格。如果出现此错误，请删除 `output` 文件夹后更换 llm 重试。
3. 配音功能由于不同语言的语速和语调差异，可能不能 100% 完美。
4. **多角色配音支持**：现已支持通过 Pyannote 进行多角色识别（实验性）。

## 📄 许可证

本项目采用 Apache 2.0 许可证，衷心感谢以下开源项目的贡献：

[whisperX](https://github.com/m-bain/whisperX), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [json_repair](https://github.com/mangiucugna/json_repair), [BELLE](https://github.com/LianjiaTech/BELLE)

## 📬 联系

- 加入 QQ 群寻求解答：875297969
- 在 GitHub 上提交 [Issues](https://github.com/Huanshere/VideoLingo/issues) 或 [Pull Requests](https://github.com/Huanshere/VideoLingo/pulls)
- 关注我的 Twitter：[@Huanshere](https://twitter.com/Huanshere)
- 联系邮箱：team@videolingo.io

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Huanshere/VideoLingo&type=Timeline)](https://star-history.com/#Huanshere/VideoLingo&Timeline)