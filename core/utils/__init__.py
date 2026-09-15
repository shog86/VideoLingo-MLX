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
    """Cooperative cancellation hook for long-running core loops.

    In this MLX-optimized build the task runner is not present, so this is a
    no-op. It is kept to stay API-compatible with upstream cancellation points.
    """
    return


__all__ = ["ask_gpt", "except_handler", "check_file_exists", "load_key", "load_key_or", "update_key", "rprint", "get_joiner", "get_video_info", "get_video_resolution", "effective_max_sub_length", "build_ass_styles", "find_ffmpeg", "ensure_ffmpeg_in_path", "check_cancel"]