import librosa
import numpy as np
import tempfile
import os
import soundfile as sf
import warnings
from src.pitch_engine import extract_pitch_and_rms

def test_condition(base_audio, instrument, engine, cents, tempdir):
    y, sr = librosa.load(base_audio, sr=None)
    
    mod_path = os.path.join(tempdir, f"mod_{instrument}_{engine}_{cents}.wav")
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
    error_dir = median_delta - cents
    return median_delta, error_dir

def main():
    warnings.filterwarnings('ignore')
    
    datasets = {
        "Violin 1": "dataset/44_K515_vn_vn_va_va_vc/1_vn/AuSep_1_vn_44_K515.wav",
        "Violin 2": "dataset/44_K515_vn_vn_va_va_vc/2_vn/AuSep_2_vn_44_K515.wav",
        "Viola 1": "dataset/44_K515_vn_vn_va_va_vc/3_va/AuSep_3_va_44_K515.wav",
        "Viola 2": "dataset/44_K515_vn_vn_va_va_vc/4_va/AuSep_4_va_44_K515.wav",
        "Cello": "dataset/44_K515_vn_vn_va_va_vc/5_vc/AuSep_5_vc_44_K515.wav"
    }
    
    engine_inst_map = {
        "Violin 1": "Violin", "Violin 2": "Violin",
        "Viola 1": "Viola", "Viola 2": "Viola", "Cello": "Cello"
    }
    
    conditions = [25.0, -25.0, 50.0, -50.0]
    
    print("Fetching REAPER data (Fast C++ backend)...")
    with tempfile.TemporaryDirectory() as tempdir:
        for inst_name, path in datasets.items():
            for cents in conditions:
                meas, err = test_condition(path, engine_inst_map[inst_name], "REAPER", cents, tempdir)
                print(f"{inst_name} | REAPER | {cents:+.0f}c | Meas: {meas:+.2f}c | Err: {err:+.2f}c")

if __name__ == "__main__":
    main()
