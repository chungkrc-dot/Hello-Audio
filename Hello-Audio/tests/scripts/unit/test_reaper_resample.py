import argparse
import librosa
import numpy as np
import warnings
import tempfile
import soundfile as sf
import os

from src.pitch_engine import extract_pitch_and_rms

def main():
    parser = argparse.ArgumentParser(description="REAPER pristine resampling proof")
    parser.add_argument("--cents", type=float, default=50.0, help="Modulation amount in cents")
    args = parser.parse_args()
    
    warnings.filterwarnings('ignore')
    
    base_audio = "dataset (Strings only)/02_Sonata_vn_vn/1_vn/AuSep_1_vn_02_Sonata.wav"
    instrument = "Violin"
    engine = "REAPER"
    
    print(f"Loading Base Audio: {base_audio}")
    y, sr = librosa.load(base_audio, sr=None)
    
    with tempfile.TemporaryDirectory() as tempdir:
        mod_path = os.path.join(tempdir, "modulated.wav")
        
        # Resample to pristine pitch shift
        print(f"Modulating Audio by {args.cents:+} cents (via Resampling)...")
        rate_change = 2.0 ** (args.cents / 1200.0)
        y_mod = librosa.resample(y, orig_sr=sr * rate_change, target_sr=sr)
        sf.write(mod_path, y_mod, sr)
        
        print(f"\n--- Testing Engine: {engine} ---")
        print(f"  Extracting Baseline...")
        with open(base_audio, 'rb') as af:
            _, _, f0_base, v_base, _ = extract_pitch_and_rms(
                af, instrument=instrument, switch_prob=0.005, enable_freq_limits=True, pitch_engine=engine
            )
            
        print(f"  Extracting Modulated...")
        with open(mod_path, 'rb') as af:
            _, _, f0_mod, v_mod, _ = extract_pitch_and_rms(
                af, instrument=instrument, switch_prob=0.005, enable_freq_limits=True, pitch_engine=engine
            )
            
        # Create time arrays
        t_base = librosa.times_like(f0_base, sr=sr, hop_length=512)
        t_mod = librosa.times_like(f0_mod, sr=sr, hop_length=512)
        
        # Map modulated time back to original timeline
        t_mod_mapped = t_mod * rate_change
        
        deltas = []
        for i, t in enumerate(t_base):
            if v_base[i]:
                # Find closest time in t_mod_mapped
                idx = np.abs(t_mod_mapped - t).argmin()
                # If they are very close in time and both are voiced
                if abs(t_mod_mapped[idx] - t) < 0.05 and v_mod[idx]:
                    # Calculate deviation in cents
                    midi_b = librosa.hz_to_midi(f0_base[i])
                    midi_m = librosa.hz_to_midi(f0_mod[idx])
                    deltas.append((midi_m - midi_b) * 100.0)
                    
        if not deltas:
            print("  [FAIL] No shared voiced frames found.")
            return
            
        # We use Median instead of Mean. 
        # Why? Because pitch trackers (especially REAPER) can occasionally suffer from "octave drops"
        # (tracking the 2nd subharmonic), which creates massive -1200 cent outliers.
        # The median robustly ignores these gross tracking artifacts and finds the true pitch center.
        median_delta = np.median(deltas)
        
        print("\nRESULTS:")
        print(f"  Measured Median Delta: {median_delta:+.2f} cents")
        print(f"  Expected Delta: {args.cents:+.2f} cents")
        
        error = abs(median_delta - args.cents)
        print(f"  Absolute Error: {error:.2f} cents")
        
        if error < 10.0:
            print(f"  [PASS] REAPER successfully extracted the pitch displacement using pristine resampling!")
        else:
            print(f"  [FAIL] REAPER error exceeded tolerance.")

if __name__ == "__main__":
    main()
