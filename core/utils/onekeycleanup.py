import os
import glob
from core._1_ytdlp import find_video_files, find_audio_files
import shutil

def cleanup(history_dir="history", media_file=None):
    """把 output/ 的产品归档到 history/<媒体名>/。

    Args:
        history_dir: 归档根目录。
        media_file: 用于命名归档目录的媒体路径；缺省时按视频查找，视频不存在
            时回退到音频（音频输入没有视频文件，find_video_files 会抛错）。
            音频 fallback 排除了生成的配音产物，避免误用 dub.mp3 命名。
    """
    if media_file is None:
        media_file = _find_media_for_archive()
    video_name = _media_stem(media_file)

    # Create required folders
    os.makedirs(history_dir, exist_ok=True)
    video_history_dir = os.path.join(history_dir, video_name)
    log_dir = os.path.join(video_history_dir, "log")
    gpt_log_dir = os.path.join(video_history_dir, "gpt_log")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(gpt_log_dir, exist_ok=True)

    # Move non-log files
    for file in glob.glob("output/*"):
        if not file.endswith(('log', 'gpt_log')):
            move_file(file, video_history_dir)

    # Move log files
    for file in glob.glob("output/log/*"):
        move_file(file, log_dir)

    # Move gpt_log files
    for file in glob.glob("output/gpt_log/*"):
        move_file(file, gpt_log_dir)

    # Delete empty output directories
    try:
        os.rmdir("output/log")
        os.rmdir("output/gpt_log")
        os.rmdir("output")
    except OSError:
        pass  # Ignore errors when deleting directories


def _find_media_for_archive():
    """取一个用于命名归档目录的媒体路径；视频优先，音频兜底。

    两者都找不到时（例如云端产物已无源文件），回退到一个带随机后缀的
    唯一名，避免多次兜底归档都落到同一个 history/unknown 而互相覆盖。
    """
    try:
        return find_video_files()
    except Exception:
        try:
            return find_audio_files()
        except Exception:
            return os.path.join("output", f"unknown_{os.urandom(8).hex()}")


def _media_stem(media_file):
    """从媒体路径取去掉扩展名的基准名，用于归档目录命名。"""
    name = media_file.replace("\\", "/")
    name = os.path.basename(name)
    return sanitize_filename(os.path.splitext(name)[0])

def move_file(src, dst):
    try:
        # Get the source file name
        src_filename = os.path.basename(src)
        # Use os.path.join to ensure correct path and include file name
        dst = os.path.join(dst, sanitize_filename(src_filename))
        
        if os.path.exists(dst):
            if os.path.isdir(dst):
                # If destination is a folder, try to delete its contents
                shutil.rmtree(dst, ignore_errors=True)
            else:
                # If destination is a file, try to delete it
                os.remove(dst)
        
        shutil.move(src, dst, copy_function=shutil.copy2)
        print(f"✅ Moved: {src} -> {dst}")
    except PermissionError:
        print(f"⚠️ Permission error: Cannot delete {dst}, attempting to overwrite")
        try:
            shutil.copy2(src, dst)
            os.remove(src)
            print(f"✅ Copied and deleted source file: {src} -> {dst}")
        except Exception as e:
            print(f"❌ Move failed: {src} -> {dst}")
            print(f"Error message: {str(e)}")
    except Exception as e:
        print(f"❌ Move failed: {src} -> {dst}")
        print(f"Error message: {str(e)}")

def sanitize_filename(filename):
    # Remove or replace disallowed characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename

if __name__ == "__main__":
    cleanup()