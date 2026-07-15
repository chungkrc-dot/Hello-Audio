import numpy as np
from tests.validate_pitch_synthetic import analyze, cents_error, create_wav_buffer

def apply_fade(y, sr, fade_ms=10):
    fade_len = int(sr * fade_ms / 1000.0)
    if fade_len > 0 and len(y) > 2 * fade_len:
        fade_in = np.linspace(0, 1, fade_len)
        fade_out = np.linspace(1, 0, fade_len)
        y[:fade_len] *= fade_in
        y[-fade_len:] *= fade_out
    return y

def generate_sine_var(freq, sr=44100, duration=3.0, phase_offset=0):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = np.sin(2 * np.pi * freq * t + phase_offset)
    return create_wav_buffer(apply_fade(y, sr), sr)

frequencies = [94.5, 113.1, 135.3, 277.5, 332.1]
phases = [0, np.pi/4, np.pi/2, np.pi]
durations = [2.5, 3.0, 3.5]

print("Freq | Phase | Dur | Result (Hz)")
for f in frequencies:
    for dur in durations:
        for phase in phases:
            buf = generate_sine_var(f, duration=dur, phase_offset=phase)
            meas = analyze(buf, "REAPER", f)
            err = cents_error(meas, f)
            pf = "PASS" if abs(err) <= 10 else "FAIL" if not np.isnan(err) else "NaN"
            print(f"{f:5.1f} | {phase:4.2f} | {dur:3.1f} | {meas:6.2f} ({pf})", flush=True)
