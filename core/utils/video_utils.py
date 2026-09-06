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
