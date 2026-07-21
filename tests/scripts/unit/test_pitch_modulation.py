import os
import argparse
import librosa
import numpy as np
import warnings
import tempfile
import soundfile as sf

from src.pitch_engine import extract_pitch_and_rms

def main():
    parser = argparse.ArgumentParser(description="Pitch Modulation Accuracy Proof")
    parser.add_argument("--cents", type=float, required=True, help="Modulation amount in cents")
    parser.add_argument("--engine", choices=["pYIN", "REAPER", "BOTH"], default="BOTH", help="Engine to test")
    args = parser.parse_args()
    
    warnings.filterwarnings('ignore')
    
    # Use a naturally short track (46 seconds) to keep it fast
    base_audio = "dataset (Strings only)/02_Sonata_vn_vn/1_vn/AuSep_1_vn_02_Sonata.wav"
    instrument = "Violin"
    
    print(f"Loading Base Audio: {base_audio}")
    y, sr = librosa.load(base_audio, sr=None)
    
    with tempfile.TemporaryDirectory() as tempdir:
        mod_path = os.path.join(tempdir, "modulated.wav")
        
        print(f"Modulating Audio by {args.cents:+} cents...")
        y_mod = librosa.effects.pitch_shift(y, sr=sr, n_steps=args.cents / 100.0)
        
        # Ensure exact same length to prevent broadcasting errors
        if len(y_mod) > len(y): y_mod = y_mod[:len(y)]
        elif len(y_mod) < len(y): y_mod = np.pad(y_mod, (0, len(y) - len(y_mod)), mode='constant')
        
        sf.write(mod_path, y_mod, sr)
        
        engines_to_test = ["pYIN", "REAPER"] if args.engine == "BOTH" else [args.engine]
        
        for eng in engines_to_test:
            print(f"\n--- Testing Engine: {eng} ---")
            print(f"  Extracting Baseline ({eng})...")
            with open(base_audio, 'rb') as af:
                _, _, f0_base, v_base, _, _ = extract_pitch_and_rms(
                    af, instrument=instrument, switch_prob=0.005, enable_freq_limits=True, pitch_engine=eng
                )
                
            print(f"  Extracting Modulated ({eng})...")
            with open(mod_path, 'rb') as af:
                _, _, f0_mod, v_mod, _, _ = extract_pitch_and_rms(
                    af, instrument=instrument, switch_prob=0.005, enable_freq_limits=True, pitch_engine=eng
                )
            
            # We want to measure the exact cent deviation between the two f0 arrays.
            # We must only compare frames where BOTH extraction runs successfully voiced a pitch.
            shared_voice_mask = v_base & v_mod
            
            if not np.any(shared_voice_mask):
                print("  [FAIL] No shared voiced frames found to compare.")
                continue
                
            f0_base_voiced = f0_base[shared_voice_mask]
            f0_mod_voiced = f0_mod[shared_voice_mask]
            
            # Convert Hz to MIDI (semitones) and then to cents
            midi_base = librosa.hz_to_midi(f0_base_voiced)
            midi_mod = librosa.hz_to_midi(f0_mod_voiced)
            
            # Calculate frame-by-frame delta in cents
            deltas_cents = (midi_mod - midi_base) * 100.0
            
            mean_delta = np.mean(deltas_cents)
            
            print("\nRESULTS:")
            print(f"  Measured Mean Delta: {mean_delta:+.2f} cents")
            print(f"  Expected Delta: {args.cents:+.2f} cents")
            
            error = abs(mean_delta - args.cents)
            print(f"  Absolute Error: {error:.2f} cents")
            
            # We set a somewhat generous threshold (e.g. 10 cents) because phase vocoder pitch shifting
            # natively introduces spectral artifacts that degrade the underlying pitch integrity slightly.
            if error < 10.0:
                print(f"  [PASS] The {eng} frequency detection logic accurately captures the displacement!")
            else:
                print(f"  [FAIL] The {eng} engine deviation exceeded the error tolerance.")

if __name__ == "__main__":
    main()
