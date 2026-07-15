import numpy as np
import librosa
import pyreaper
import sys

def apply_fade(y, sr, fade_ms=10):
    fade_len = int(sr * fade_ms / 1000.0)
    if fade_len > 0 and len(y) > 2 * fade_len:
        fade_in = np.linspace(0, 1, fade_len)
        fade_out = np.linspace(1, 0, fade_len)
        y[:fade_len] *= fade_in
        y[-fade_len:] *= fade_out
    return y

def test_reaper_raw(freq, dur=3.0, sr=16000, fade=10):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    y = np.sin(2 * np.pi * freq * t)
    y = apply_fade(y, sr, fade_ms=fade)
    y_int16 = (y * 32767 * 0.9).astype(np.int16)
    
    # REAPER parameters from extract_pitch_and_rms
    frame_period = 512.0 / 44100.0
    
    # Bounds logic
    fmin_hz = 40.0
    fmax_hz = 2000.0
    
    pm_times, pm, f0_times, f0, corr = pyreaper.reaper(
        y_int16, sr, minf0=fmin_hz, maxf0=fmax_hz, frame_period=frame_period
    )
    
    print(f"\n--- Raw REAPER for {freq} Hz ---")
    
    valid_f0 = f0[f0 != -1.0]
    print(f"Total frames: {len(f0)}")
    print(f"Valid frames (!=-1): {len(valid_f0)}")
    if len(valid_f0) > 0:
        print(f"Median F0: {np.median(valid_f0)}")
        print(f"Unique valid F0 values: {np.unique(valid_f0)}")
        
    print(f"Sample values of f0 (first 20 valid): {valid_f0[:20] if len(valid_f0) > 0 else 'None'}")
    
    # Let's test with harmonic content just to compare
    y_saw = librosa.tone(freq, sr=sr, length=int(sr*dur)) # tone generates a sine, not saw, but wait...
    # Just manual saw:
    y_saw = 2.0 * (t * freq - np.floor(t * freq + 0.5))
    y_saw = apply_fade(y_saw, sr, fade_ms=fade)
    y_saw_int16 = (y_saw * 32767 * 0.9).astype(np.int16)
    _, _, _, f0_saw, _ = pyreaper.reaper(y_saw_int16, sr, minf0=fmin_hz, maxf0=fmax_hz, frame_period=frame_period)
    valid_f0_saw = f0_saw[f0_saw != -1.0]
    print(f"\n--- Raw REAPER for {freq} Hz SAWTOOTH ---")
    if len(valid_f0_saw) > 0:
        print(f"Median F0: {np.median(valid_f0_saw)}")
    else:
        print("No valid F0 found.")

test_reaper_raw(66.0)
test_reaper_raw(77.8)
test_reaper_raw(160.1)
test_reaper_raw(440.0)
test_reaper_raw(880.0)
