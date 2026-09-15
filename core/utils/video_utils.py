import subprocess
import json

def get_media_duration(media_path):
    """Get media duration in seconds via ffprobe (format level)."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'json', media_path],
            capture_output=True, text=True, check=True, timeout=30)
        return float(json.loads(result.stdout)['format']['duration'])
    except Exception:
        pass
    # Fallback: derive from video stream frame count / fps
    try:
        import cv2
        cap = cv2.VideoCapture(media_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        cap.release()
        if fps > 0 and frames > 0:
            return frames / fps
    except Exception:
        pass
    return 0.0

def get_video_resolution(video_path):
    """Get (width, height) via cv2. Falls back to (1920, 1080) on failure."""
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    return 1920, 1080


def effective_max_sub_length(base_length, video_width, video_height=None):
    """Scale subtitle max_length by video shape, not by raw resolution.

    - Landscape (width >= height): return base directly. A compressed /
      low-res landscape copy (e.g. 640x360 of a 2K source) must not force
      denser splitting; burn-time wrapping + adaptive fonts already handle it.
    - Portrait (height > width): scale linearly with width so a single line
      never gets too long on a narrow screen:
        1080-wide portrait -> ~42, 720-wide portrait -> ~35 (base 75).
      Clamped to [35, base] (floor follows base when base < 35).
    - height unknown (legacy caller): fall back to the old width scaling.
    """
    try:
        base = int(base_length)
    except Exception:
        return int(base_length)
    if video_height is not None:
        try:
            if float(video_width) >= float(video_height):
                return base
        except Exception:
            return base
    try:
        scaled = round(float(base) * float(video_width) / 1920.0)
    except Exception:
        return base
    floor = min(base, 35)
    return max(floor, min(base, scaled))


def build_ass_styles(width, height, top_font_name, bottom_font_name,
                     top_base_fs=20, bottom_base_fs=15,
                     top_base_mv=50, bottom_base_mv=27):
    """Build libass force_style strings adaptive to resolution.

    - PlayResX/Y = actual video size so FontSize/Margins map 1:1 to pixels.
    - WrapStyle=0 (smart wrapping) + MarginL/R = 5% width reserves side
      padding so long lines wrap instead of overflowing the screen.
    - FontSize scales with min(width, height)/1080 so 720p gets smaller
      fonts; MarginV scales with height/1080 to keep bottom position.
    """
    font_scale = min(width, height) / 1080.0
    font_scale = max(0.6, min(1.2, font_scale))
    top_fs = max(11, round(top_base_fs * font_scale))
    bottom_fs = max(9, round(bottom_base_fs * font_scale))

    h_scale = height / 1080.0
    top_mv = max(12, round(top_base_mv * h_scale))
    bottom_mv = max(8, round(bottom_base_mv * h_scale))
    side = max(10, int(width * 0.05))

    top_style = (
        f"FontSize={top_fs},FontName={top_font_name},"
        f"PrimaryColour=&H00FFFF,OutlineColour=&H000000,OutlineWidth=1,"
        f"BackColour=&H1A000000,Alignment=2,MarginL={side},MarginR={side},MarginV={top_mv},"
        f"BorderStyle=4,WrapStyle=0,PlayResX={width},PlayResY={height}"
    )
    bottom_style = (
        f"FontSize={bottom_fs},FontName={bottom_font_name},"
        f"PrimaryColour=&HFFFFFF,OutlineColour=&H000000,OutlineWidth=1,"
        f"ShadowColour=&H80000000,BorderStyle=1,Alignment=2,"
        f"MarginL={side},MarginR={side},MarginV={bottom_mv},"
        f"WrapStyle=0,PlayResX={width},PlayResY={height}"
    )
    return top_style, bottom_style, top_fs, bottom_fs


def get_video_info(video_path):
    """Get video information using ffprobe"""
    cmd = [
        'ffprobe', '-v', 'error', 
        '-select_streams', 'v:0', 
        '-show_entries', 'stream=bit_rate,pix_fmt,r_frame_rate', 
        '-of', 'json', video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        stream = info['streams'][0]
        
        # bit_rate might be missing in some containers, try format
        if 'bit_rate' not in stream:
            cmd_fmt = [
                'ffprobe', '-v', 'error', 
                '-show_entries', 'format=bit_rate', 
                '-of', 'json', video_path
            ]
            result_fmt = subprocess.run(cmd_fmt, capture_output=True, text=True, check=True)
            info_fmt = json.loads(result_fmt.stdout)
            bitrate = info_fmt.get('format', {}).get('bit_rate')
        else:
            bitrate = stream['bit_rate']
            
        return {
            'bitrate': bitrate,
            'pix_fmt': stream.get('pix_fmt'),
            'fps': stream.get('r_frame_rate')
        }
    except Exception as e:
        print(f"Error probing video info: {e}")
        return {}
