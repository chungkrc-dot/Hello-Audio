import librosa
import numpy as np
import tempfile
import os
import soundfile as sf
import warnings
from src.pitch_engine import extract_pitch_and_rms

warnings.filterwarnings('ignore')

path = "dataset/44_K515_vn_vn_va_va_vc/1_vn/AuSep_1_vn_44_K515.wav"
instrument = "Violin"
cents = 30.0

print(f"Testing pYIN with {cents} cents shift...")

with tempfile.TemporaryDirectory() as tempdir:
    y, sr = librosa.load(path, sr=None)
    
    mod_path = os.path.join(tempdir, f"mod_{cents}.wav")
    rate_change = 2.0 ** (cents / 1200.0)
    y_mod = librosa.resample(y, orig_sr=sr * rate_change, target_sr=sr)
    sf.write(mod_path, y_mod, sr)
    
    with open(path, 'rb') as af:
        _, _, f0_base, v_base, _ = extract_pitch_and_rms(
            af, instrument=instrument, switch_prob=0.005, enable_freq_limits=True, pitch_engine="pYIN"
        )
        
    with open(mod_path, 'rb') as af:
        _, _, f0_mod, v_mod, _ = extract_pitch_and_rms(
            af, instrument=instrument, switch_prob=0.005, enable_freq_limits=True, pitch_engine="pYIN"
        )
        
    t_base = librosa.times_like(f0_base, sr=sr, hop_length=512)
    t_mod = librosa.times_like(f0_mod, sr=sr, hop_length=512)
    t_mod_mapped = t_mod * rate_change
    
    deltas = []
    for i, t in enumerate(t_base):
        if v_base[i]:
            idx = np.abs(t_mod_mapped - t).argmin()
            if abs(t_mod_mapped[idx] - t) < 0.05 and v_mod[idx]:
                midi_b = librosa.hz_to_midi(f0_base[i])
                midi_m = librosa.hz_to_midi(f0_mod[idx])
                deltas.append((midi_m - midi_b) * 100.0)
                
    if deltas:
        median_delta = np.median(deltas)
        error = abs(median_delta - cents)
        print(f"Shift: {cents} c, Measured: {median_delta:.2f} c, Error: {error:.2f} c")
