"""Conservative per-file hardware decode selection for device-verified profiles."""
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname


def hardware_allowed(arguments, policy, probe='/usr/bin/ffprobe'):
    if policy == 'all':
        return True
    if policy != 'h264-baseline':
        return False
    files = []
    for value in arguments:
        if value.startswith('-'):
            continue
        if value.startswith('file:'):
            uri = urlsplit(value)
            if uri.netloc not in ('', 'localhost'):
                return False
            path = Path(url2pathname(uri.path))
        elif '://' in value:
            # Do not prefetch streams or credentials just to select a decoder.
            return False
        else:
            path = Path(value)
        try:
            if path.is_file():
                files.append(path.resolve())
        except OSError:
            return False
    if not files:
        return False
    for path in files:
        try:
            result = subprocess.run(
                [probe, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                 'stream=codec_name,profile,has_b_frames,width,height,pix_fmt,avg_frame_rate',
                 '-of', 'json', '-i', str(path)],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5, check=True)
            data = json.loads(result.stdout)
            streams = data.get('streams', []) if isinstance(data, dict) else []
            if not isinstance(streams, list) or len(streams) != 1:
                return False
            stream = streams[0]
            if not (isinstance(stream, dict) and stream.get('codec_name') == 'h264'
                    and stream.get('profile') in ('Baseline', 'Constrained Baseline')
                    and stream.get('has_b_frames') == 0
                    and stream.get('pix_fmt') == 'yuv420p'
                    and 0 < stream.get('width', 0) <= 1920
                    and 0 < stream.get('height', 0) <= 1080
                    and 0 < Fraction(stream.get('avg_frame_rate', '0')) <= 30):
                return False
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, ZeroDivisionError):
            return False
    return True
