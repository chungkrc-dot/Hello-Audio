import argparse
import librosa
import numpy as np
import warnings
import tempfile
import soundfile as sf
import os

from src.pitch_engine import extract_pitch_and_rms

def test_condition(base_audio, instrument, engine, cents, tempdir):
    y, sr = librosa.load(base_audio, sr=None)
    
    mod_path = os.path.join(tempdir, f"modulated_{engine}_{cents}.wav")
    rate_change = 2.0 ** (cents / 1200.0)
    y_mod = librosa.resample(y, orig_sr=sr * rate_change, target_sr=sr)
    sf.write(mod_path, y_mod, sr)
    
    with open(base_audio, 'rb') as af:
        _, _, f0_base, v_base, _ = extract_pitch_and_rms(
            af, instrument=instrument, switch_prob=0.005, enable_freq_limits=True, pitch_engine=engine
        )
        
    with open(mod_path, 'rb') as af:
        _, _, f0_mod, v_mod, _ = extract_pitch_and_rms(
            af, instrument=instrument, switch_prob=0.005, enable_freq_limits=True, pitch_engine=engine
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
                
    if not deltas:
        return np.nan, np.nan
        
    median_delta = np.median(deltas)
    error = abs(median_delta - cents)
    return median_delta, error

def main():
    warnings.filterwarnings('ignore')
    base_audio = "dataset/02_Sonata_vn_vn/1_vn/AuSep_1_vn_02_Sonata.wav"
    instrument = "Violin"
    
    conditions = [25.0, 50.0, -25.0, -50.0]
    engines = ["pYIN", "REAPER"]
    
    print("Starting Batch Resample Modulation Test...")
    print(f"{'Engine':<10} | {'Condition':<12} | {'Measured':<10} | {'Error':<10}")
    print("-" * 50)
    
    with tempfile.TemporaryDirectory() as tempdir:
        for engine in engines:
            for cents in conditions:
                median_delta, error = test_condition(base_audio, instrument, engine, cents, tempdir)
                cond_str = f"{cents:+.0f} cents"
                print(f"{engine:<10} | {cond_str:<12} | {median_delta:>+7.2f} c | {error:>6.2f} c")

if __name__ == "__main__":
    main()
