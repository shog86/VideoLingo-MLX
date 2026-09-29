"""本地单用户 HTTP API，从仓库根目录用 ``python api.py`` 启动（默认 127.0.0.1:8000）。

设计取舍：与 UI 共用同一份 ``core.pipeline`` 步骤定义和 ``core.task_runner``
执行器，因此同一时刻只允许一个操作；状态保存在内存中，``output/`` 里的产物
在服务重启后依然存在。
"""
import shutil
import sys
from pathlib import Path
from threading import Lock
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field


def _configure_utf8_console():
    """让 Rich 与后台线程在 Windows 上也能打印 Unicode。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_console()

from core.pipeline import get_steps
from core.task_runner import TaskRunner
from core.utils.config_utils import load_key, update_key

app = FastAPI(title="VideoLingo-MLX", description="One operation at a time, using config.yaml and output/.")
runner = TaskRunner()
operation_lock = Lock()
OUTPUT = Path("output")


class InputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, description="本地文件路径或 HTTP(S) 视频/音频 URL")
    existing: Literal["reject", "archive", "replace"] = "reject"


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: Literal["transcribe", "subtitles", "dubbing", "all"] = "all"
    dubbing: bool = False
    target_language: str | None = Field(default=None, min_length=1)
    source_language: str | None = Field(default=None, min_length=1)


def require_idle():
    """确认当前没有活动任务，否则返回 409。"""
    if runner.is_active:
        raise HTTPException(409, "An operation is active; wait for /status before continuing.")


def archive_output():
    """把 output/ 归档到 history/，归档不干净时抛错提示人工检查。"""
    from core.utils.onekeycleanup import cleanup
    cleanup()
    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        raise RuntimeError("Some output files could not be archived; inspect output/ before retrying.")


def _api_progress_cb(step=None, detail=None, percent=None):
    """把 pipeline 归一化后的整体 0-100 进度写入 runner，供 /status 读取。

    没有回报百分比的调用（如纯提示文字）会忽略，保持上一次的整体进度，
    避免覆盖已上报的精确进度。
    """
    if isinstance(percent, (int, float)):
        runner.set_progress(float(percent) / 100.0)


def prepare_input(source: str, existing: str):
    """把外部输入（URL 或本地文件）准备到 output/ 并写入 manifest。"""
    from core._1_ytdlp import (download_video_ytdlp, write_input_manifest,
                              sanitize_filename, GENERATED_AUDIO_NAMES)
    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        if existing == "archive":
            archive_output()
        elif existing == "replace":
            shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(exist_ok=True)
    if urlparse(source).scheme in {"http", "https"}:
        download_video_ytdlp(source, resolution=load_key("ytb_resolution"))
    else:
        src = Path(source)
        name = sanitize_filename(src.stem) + src.suffix.lower()
        # 避免生成的配音产物名与输入重名，被后续 find_audio_files 误认
        if name.lower() in GENERATED_AUDIO_NAMES:
            name = "input_" + name
        destination = OUTPUT / name
        shutil.copy2(src, destination)
        kind = "video" if src.suffix.lower()[1:] in load_key("allowed_video_formats") else "audio"
        write_input_manifest(str(destination), kind)


@app.post("/input", status_code=202)
def set_input(request: InputRequest):
    """在后台准备输入；先轮询 /status 再 POST /run。"""
    with operation_lock:
        require_idle()
        parsed = urlparse(request.source)
        if parsed.scheme in {"http", "https"}:
            if not parsed.netloc:
                raise HTTPException(422, "Invalid URL")
            source = request.source
        else:
            source = Path(request.source).resolve()
            if not source.is_file():
                raise HTTPException(422, "Source file does not exist")
            if source.is_relative_to(OUTPUT.resolve()):
                raise HTTPException(422, "Source must be outside output/; use /run for an existing input.")
            formats = load_key("allowed_video_formats") + load_key("allowed_audio_formats")
            if source.suffix.lower()[1:] not in formats:
                raise HTTPException(422, "Unsupported media format")
            source = str(source)
        if OUTPUT.exists() and any(OUTPUT.iterdir()) and request.existing == "reject":
            raise HTTPException(409, "output/ is not empty; explicitly choose archive or replace.")
        runner.start([("Prepare input", lambda: prepare_input(source, request.existing))])
        return {"accepted": True}


@app.post("/run", status_code=202)
def run(request: RunRequest):
    """运行或重试共享流水线；请求里的语言参数会写回 config.yaml。"""
    with operation_lock:
        require_idle()
        from core._1_ytdlp import find_media_file
        try:
            _, kind = find_media_file()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        needs_dubbing = request.stage == "dubbing" or (request.stage == "all" and request.dubbing)
        if needs_dubbing and kind == "audio":
            raise HTTPException(422, "Input without a video supports subtitles only, as in the UI.")
        if request.stage == "dubbing" and not all((OUTPUT / name).exists() for name in ("src.srt", "trans.srt")):
            raise HTTPException(409, "Generate subtitles before starting dubbing.")
        if request.target_language is not None:
            update_key("target_language", request.target_language)
        if request.source_language is not None:
            update_key("whisper.language", request.source_language)
        burn = bool(load_key("burn_subtitles")) and request.stage in {"subtitles", "all"}
        runner.start(get_steps(request.stage, dubbing=request.dubbing, burn=burn,
                               progress_callback=_api_progress_cb))
        return {"accepted": True}


@app.get("/status")
def status():
    """返回内存中的执行状态；产物文件在服务重启后依旧存在。"""
    files = sorted(p.name for p in OUTPUT.glob("*") if p.is_file() and not p.name.startswith('.'))
    return {
        "state": runner.state,
        "active": runner.is_active,
        "step": runner.current_label or None,
        "step_index": runner.current_step,
        "total_steps": runner.total_steps,
        "progress": runner.progress,
        "error": runner.error_msg or None,
        "pause_message": runner.pause_message or None,
        "files": files,
    }


@app.post("/pause")
def pause():
    """暂停当前任务；对应检查点处的“暂停等待确认”。"""
    with operation_lock:
        if runner.state != "running":
            raise HTTPException(409, "No running task to pause.")
        runner.pause()
        return {"state": runner.state}


@app.post("/resume")
def resume():
    """继续被暂停的任务，例如 pause_before_translate / pause_after_translate 检查点。"""
    with operation_lock:
        if runner.state != "paused":
            raise HTTPException(409, "No task is paused.")
        runner.resume()
        return {"state": runner.state}


@app.post("/stop")
def stop():
    """协作式停止：等到 active=false 后再发起下一个操作。"""
    with operation_lock:
        runner.stop()
        return {"state": runner.state}


@app.get("/files/{name}")
def file(name: str):
    """下载 output/ 下的产物文件。"""
    path = (OUTPUT / name).resolve()
    if path.parent != OUTPUT.resolve() or name.startswith('.') or not path.is_file():
        raise HTTPException(404, "Output file not found")
    return FileResponse(path, filename=path.name)


@app.post("/archive", status_code=202)
def archive():
    """把 output/ 归档到 history/。"""
    with operation_lock:
        require_idle()
        if not OUTPUT.exists() or not any(OUTPUT.iterdir()):
            raise HTTPException(409, "No output to archive")
        runner.start([("Archive output", archive_output)])
        return {"accepted": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
