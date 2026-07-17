import argparse
import librosa
import numpy as np
import warnings
import tempfile
import soundfile as sf
import os

from src.pitch_engine import extract_pitch_and_rms

def get_base_extraction(base_audio, instrument, engine):
    with open(base_audio, 'rb') as af:
        _, _, f0_base, v_base, _ = extract_pitch_and_rms(
            af, instrument=instrument, switch_prob=0.005, enable_freq_limits=True, pitch_engine=engine
        )
    return f0_base, v_base

def test_condition(base_audio, instrument, engine, cents, tempdir, f0_base, v_base, sr):
    y, _ = librosa.load(base_audio, sr=sr)
    
    mod_path = os.path.join(tempdir, f"modulated_{instrument}_{engine}_{cents}.wav")
    rate_change = 2.0 ** (cents / 1200.0)
    y_mod = librosa.resample(y, orig_sr=sr * rate_change, target_sr=sr)
    sf.write(mod_path, y_mod, sr)
    
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
        return np.nan
        
    median_delta = np.median(deltas)
    error = abs(median_delta - cents)
    return error

def main():
    warnings.filterwarnings('ignore')
    
    datasets = {
        "Violin 1": "dataset (Strings only)/44_K515_vn_vn_va_va_vc/1_vn/AuSep_1_vn_44_K515.wav",
        "Violin 2": "dataset (Strings only)/44_K515_vn_vn_va_va_vc/2_vn/AuSep_2_vn_44_K515.wav",
        "Viola 1": "dataset (Strings only)/44_K515_vn_vn_va_va_vc/3_va/AuSep_3_va_44_K515.wav",
        "Viola 2": "dataset (Strings only)/44_K515_vn_vn_va_va_vc/4_va/AuSep_4_va_44_K515.wav",
        "Cello": "dataset (Strings only)/44_K515_vn_vn_va_va_vc/5_vc/AuSep_5_vc_44_K515.wav"
    }
    
    conditions = [25.0, -25.0, 50.0, -50.0]
    engines = ["pYIN", "REAPER"]
    
    print("Starting Expanded Hybrid Proof Resample Modulation Test...")
    print(f"{'Instrument':<12} | {'Engine':<10} | {'Condition':<12} | {'Absolute Error':<15}")
    print("-" * 55)
    
    with tempfile.TemporaryDirectory() as tempdir:
        for inst_name, path in datasets.items():
            engine_inst_map = {
                "Violin 1": "Violin",
                "Violin 2": "Violin",
                "Viola 1": "Viola",
                "Viola 2": "Viola",
                "Cello": "Cello"
            }
            engine_inst = engine_inst_map[inst_name]
            
            # Load sample rate once for this file
            _, sr = librosa.load(path, sr=None)
            
            for engine in engines:
                # Optimize: Compute baseline extraction only once per engine per instrument
                f0_base, v_base = get_base_extraction(path, engine_inst, engine)
                
                for cents in conditions:
                    error = test_condition(path, engine_inst, engine, cents, tempdir, f0_base, v_base, sr)
                    cond_str = f"{cents:+.0f} c"
                    print(f"{inst_name:<12} | {engine:<10} | {cond_str:<12} | {error:>10.2f} c")

if __name__ == "__main__":
    main()
