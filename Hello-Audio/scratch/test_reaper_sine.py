import sys
import os
import io
import numpy as np
import scipy.io.wavfile
import librosa
import pyreaper

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.pitch_engine import extract_pitch_and_rms

def create_wav_buffer(y, sr=44100):
    buf = io.BytesIO()
    y_int16 = np.int16(y / np.max(np.abs(y)) * 32767 * 0.9)
    scipy.io.wavfile.write(buf, sr, y_int16)
    buf.seek(0)
    return buf

for f in [275.1, 329.5, 394.6, 440.0, 1394.4]:
    t = np.linspace(0, 3.0, int(44100 * 3.0), endpoint=False)
    y = np.sin(2 * np.pi * f * t)
    buf = create_wav_buffer(y, sr=44100)
    
    # Try PyREAPER natively directly
    buf.seek(0)
    y_read, sr_read = librosa.load(buf, sr=16000, duration=3.0)
    y_int16 = (y_read * 32767).astype(np.int16)
    
    # Direct
    pm_times, pm, f0_times, f0, corr = pyreaper.reaper(y_int16, sr_read, minf0=40.0, maxf0=2000.0, frame_period=0.0116)
    f0_valid = f0[f0 > 0]
    if len(f0_valid) > 0:
        med = np.median(f0_valid)
    else:
        med = np.nan
        
    print(f"Freq: {f} Hz -> REAPER direct: {med:.2f} Hz")
