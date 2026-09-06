import sys
import subprocess
from unittest.mock import MagicMock, patch

# Define the mock behaviors before importing the modules
def mock_load_key(key):
    if key == "ffmpeg_gpu":
        return False
    if key == "burn_subtitles":
        return True
    return MagicMock()

# Setup mocks to allow importing core modules
sys.modules['cv2'] = MagicMock()
sys.modules['numpy'] = MagicMock()

# Import the actual modules
import core.utils
core.utils.load_key = mock_load_key
core.utils.rprint = MagicMock()

from core import _7_sub_into_vid
from core import _12_dub_to_vid

def test_sub_into_vid():
    print("Testing core/_7_sub_into_vid.py...")
    with patch('subprocess.Popen') as mock_popen, \
         patch('core._7_sub_into_vid.find_video_files', return_value='test.mp4'), \
         patch('core._7_sub_into_vid.load_key', side_effect=mock_load_key):
        
        # CPU path
        _7_sub_into_vid.merge_subtitles_to_video()
        cmd = mock_popen.call_args[0][0]
        cmd_str = ' '.join(str(arg) for arg in cmd)
        print(f"  CMD: {cmd_str}")
        assert '-crf 18' in cmd_str
        assert '-preset slow' in cmd_str
        assert 'flags=bicubic' in cmd_str
        print("  CPU path OK")

def test_dub_to_vid():
    print("Testing core/_12_dub_to_vid.py...")
    with patch('subprocess.run') as mock_run, \
         patch('core._12_dub_to_vid.find_video_files', return_value='test.mp4'), \
         patch('core._12_dub_to_vid.load_key', side_effect=mock_load_key), \
         patch('core._12_dub_to_vid.normalize_audio_volume', MagicMock()):
        
        # CPU path
        _12_dub_to_vid.merge_video_audio()
        cmd = mock_run.call_args[0][0]
        cmd_str = ' '.join(str(arg) for arg in cmd)
        print(f"  CMD: {cmd_str}")
        assert '-crf 18' in cmd_str
        assert '-preset slow' in cmd_str
        assert 'flags=bicubic' in cmd_str
        assert '-b:a 192k' in cmd_str
        print("  CPU path OK")

if __name__ == "__main__":
    try:
        test_sub_into_vid()
        test_dub_to_vid()
        print("\nAll tests passed!")
    except AssertionError as e:
        print(f"\nTest failed!")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
