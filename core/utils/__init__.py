# use try-except to avoid error when installing
try:
    from .ask_gpt import ask_gpt
    from .decorator import except_handler, check_file_exists
    from .config_utils import load_key, load_key_or, update_key, get_joiner
    from .video_utils import get_video_info, get_video_resolution, effective_max_sub_length, build_ass_styles
    from .ffmpeg_utils import find_ffmpeg, ensure_ffmpeg_in_path
    from rich import print as rprint
except ImportError:
    import traceback
    traceback.print_exc()


def check_cancel():
    """协作式取消钩子，供 core 内部的长循环调用。

    转发到 :class:`core.task_runner.TaskRunner`：暂停时阻塞等待，停止时抛出
    ``StopTask``。没有活动执行器时（命令行直接跑 core 脚本）是空操作。
    这里用延迟导入避免与 core.utils 包初始化产生循环依赖。
    """
    from core.task_runner import TaskRunner
    TaskRunner.check_cancel()


__all__ = ["ask_gpt", "except_handler", "check_file_exists", "load_key", "load_key_or", "update_key", "rprint", "get_joiner", "get_video_info", "get_video_resolution", "effective_max_sub_length", "build_ass_styles", "find_ffmpeg", "ensure_ffmpeg_in_path", "check_cancel"]