"""Locate the ffmpeg binary without depending on the parent shell's PATH.

On macOS Homebrew installs ffmpeg to /opt/homebrew/bin (Apple Silicon) or
/usr/local/bin (Intel), but GUI-launched terminals / non-login shells often
lack those dirs in PATH — so `shutil.which("ffmpeg")`, pydub and yt-dlp all
report ffmpeg as missing even though it is installed.
"""
import os
import shutil

_KNOWN_LOCATIONS = (
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
)


def find_ffmpeg():
    """Return the ffmpeg executable path, or None if not found."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in _KNOWN_LOCATIONS:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def ensure_ffmpeg_in_path():
    """Prepend ffmpeg's directory to PATH when missing.

    Returns the ffmpeg path, or None. Harmless to call at startup;
    makes every later bare-`ffmpeg` subprocess call (yt-dlp merge,
    pydub, x264 burns) resolve correctly.
    """
    found = find_ffmpeg()
    if found:
        bin_dir = os.path.dirname(found)
        if bin_dir and bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    return found
