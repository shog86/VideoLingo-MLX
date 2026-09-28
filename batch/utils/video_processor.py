import os
from core.st_utils.imports_and_utils import *
from core.utils.onekeycleanup import cleanup
from core.utils import load_key
from core.pipeline import get_steps
from translations.translations import translate as t
import shutil
from functools import partial
from rich.panel import Panel
from rich.console import Console
from core import *

console = Console()

INPUT_DIR = 'batch/input'
OUTPUT_DIR = 'output'
SAVE_DIR = 'batch/output'
ERROR_OUTPUT_DIR = 'batch/output/ERROR'
YTB_RESOLUTION_KEY = "ytb_resolution"
INPUT_STEP_LABEL = "🎥 Processing input file"  # 批处理独有的输入准备步骤标签（非翻译 key）
MAX_ATTEMPTS = 3  # 每个步骤的最大重试次数

def process_video(file, dubbing=False, is_retry=False):
    """批处理单个视频：复用 core.pipeline 的统一步骤定义，逐步骤带重试执行。

    Args:
        file: batch/input 下的文件名，或 HTTP(S) 视频/音频链接。
        dubbing: 是否在字幕之后继续执行配音步骤。
        is_retry: True 表示重试既有任务，保留 output/ 内容；否则先清空。
    Returns:
        (ok, error_step, error_message)：成功时 (True, "", "")。
    """
    if not is_retry:
        prepare_output_folder(OUTPUT_DIR)

    # 输入准备是批处理独有的步骤；其余步骤与 UI / API 共用同一份定义，
    # 避免步骤清单分叉（例如 gen_source_srt 之前只存在于 UI 侧）。
    steps = [(INPUT_STEP_LABEL, partial(process_input_file, file))]
    steps.extend(get_steps("all", dubbing=bool(dubbing), burn=True))

    console.print(f"[cyan][batch] 构建执行计划：{len(steps)} 个步骤，dubbing={bool(dubbing)}[/cyan]")
    current_step = ""
    for label, step_func in steps:
        # 输入准备用自带的 emoji 标签，pipeline 步骤的标签是翻译 key
        step_name = label if label == INPUT_STEP_LABEL else t(label)
        current_step = step_name
        for attempt in range(MAX_ATTEMPTS):
            try:
                console.print(Panel(
                    f"[bold green]{step_name}[/]",
                    subtitle=f"Attempt {attempt + 1}/{MAX_ATTEMPTS}" if attempt > 0 else None,
                    border_style="blue"
                ))
                result = step_func()
                if result is not None:
                    globals().update(result)
                console.print(f"[cyan][batch] 步骤完成：{step_name}[/cyan]")
                break
            except Exception as e:
                console.print(f"[yellow][batch] 步骤失败（第 {attempt + 1}/{MAX_ATTEMPTS} 次）：{step_name} - {e}[/yellow]")
                if attempt == MAX_ATTEMPTS - 1:
                    error_panel = Panel(
                        f"[bold red]Error in step '{current_step}':[/]\n{str(e)}",
                        border_style="red"
                    )
                    console.print(error_panel)
                    cleanup(ERROR_OUTPUT_DIR)
                    return False, current_step, str(e)
                console.print(Panel(
                    f"[yellow]Attempt {attempt + 1} failed. Retrying...[/]",
                    border_style="yellow"
                ))

    console.print(Panel("[bold green]All steps completed successfully! 🎉[/]", border_style="green"))
    cleanup(SAVE_DIR)
    return True, "", ""

def prepare_output_folder(output_folder):
    """清空并重建输出目录（非重试任务开始前调用）。"""
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)
    os.makedirs(output_folder)

def process_input_file(file):
    """把批处理输入准备到 output/：支持 URL 下载与本地文件拷贝。"""
    if file.startswith('http'):
        _1_ytdlp.download_video_ytdlp(file, resolution=load_key(YTB_RESOLUTION_KEY))
        video_file = _1_ytdlp.find_video_files()
    else:
        input_file = os.path.join('batch', 'input', file)
        output_file = os.path.join(OUTPUT_DIR, file)
        shutil.copy(input_file, output_file)
        video_file = output_file
    console.print(f"[cyan][batch] 输入已准备：{video_file}[/cyan]")
    return {'video_file': video_file}
