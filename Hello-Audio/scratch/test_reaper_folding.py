import sys
import os
import glob
import numpy as np
import librosa
import pretty_midi

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
import pitch_engine
import midi_alignment

DATA_DIR = "/Users/conradchung/Documents/PythonCode/Hello-Audio/dataset"

def test_reaper_folding():
    target_folder = "44_K515_vn_vn_va_va_vc"
    folder_path = os.path.join(DATA_DIR, target_folder)
    
    audio_files = glob.glob(os.path.join(folder_path, "**", "AuSep_*.wav"), recursive=True)
    audio_files.sort()
    
    total_valid_frames = 0
    total_octave_folds = 0
    total_fifth_folds = 0
    total_third_folds = 0
    
    print("Testing REAPER octave folding on K515...")
    for audio_path in audio_files:
        basename = os.path.basename(audio_path)
        print(f"Processing {basename}...")
        
        # 1. Load Audio
        y, sr = librosa.load(audio_path, sr=None)
        
        # 2. Extract Pitch using REAPER
        if "vn" in basename.lower():
            inst = "Violin"
        elif "va" in basename.lower():
            inst = "Viola"
        elif "vc" in basename.lower():
            inst = "Cello"
        else:
            continue
            
        with open(audio_path, 'rb') as f:
            y, sr, f0_hz, voiced_flag, rms, _ = pitch_engine.extract_pitch_and_rms(
                f,
                inst,
                0.005,
                enable_freq_limits=True,
                duration=None,
                pitch_engine='REAPER'
            )
            time_array = librosa.times_like(f0_hz, sr=sr, hop_length=512)
        
        # 3. Load MIDI
        track_num = basename.split('_')[1]
        import midi_parser
        midi_files = glob.glob(os.path.join(folder_path, "Sco_*.mid"))
        if not midi_files:
            continue
        midi_path = midi_files[0]
        with open(midi_path, 'rb') as f:
            midi_notes = midi_parser.parse_midi_with_timing(f, target_track=int(track_num))
        
        # 4. Get expected pitch via DTW
        _, expected_pitch, _, _ = midi_alignment.get_alignment_mask(
            midi_notes, time_array, y, sr, hop_length=512, force_global=False
        )
        
        # 5. Check how many frames would trigger folding
        f0_midi = librosa.hz_to_midi(f0_hz)
        valid_mask = ~np.isnan(f0_midi) & ~np.isnan(expected_pitch)
        
        # Octave
        octave_offsets = np.zeros_like(f0_midi)
        octave_offsets[valid_mask] = np.round((f0_midi[valid_mask] - expected_pitch[valid_mask]) / 12.0)
        
        # Harmonic
        f0_midi_oct = f0_midi - (octave_offsets * 12.0)
        dev = np.zeros_like(f0_midi)
        dev[valid_mask] = f0_midi_oct[valid_mask] - expected_pitch[valid_mask]
        
        is_fifth = valid_mask & (dev >= -5.5) & (dev <= -4.5)
        is_third = valid_mask & (dev >= 3.5) & (dev <= 4.5)
        
        num_valid = np.sum(valid_mask)
        num_oct = np.sum(octave_offsets != 0)
        num_5th = np.sum(is_fifth)
        num_3rd = np.sum(is_third)
        
        total_valid_frames += num_valid
        total_octave_folds += num_oct
        total_fifth_folds += num_5th
        total_third_folds += num_3rd
        
        print(f"  Valid frames: {num_valid}")
        print(f"  Octave folds: {num_oct} ({num_oct/num_valid*100:.2f}%)")
        print(f"  5th folds:    {num_5th} ({num_5th/num_valid*100:.2f}%)")
        print(f"  3rd folds:    {num_3rd} ({num_3rd/num_valid*100:.2f}%)")
        
    print("\n--- SUMMARY ---")
    print(f"Total Valid Frames: {total_valid_frames}")
    if total_valid_frames > 0:
        print(f"Total Octave Folds: {total_octave_folds} ({total_octave_folds/total_valid_frames*100:.2f}%)")
        print(f"Total 5th Folds:    {total_fifth_folds} ({total_fifth_folds/total_valid_frames*100:.2f}%)")
        print(f"Total 3rd Folds:    {total_third_folds} ({total_third_folds/total_valid_frames*100:.2f}%)")

if __name__ == '__main__':
    test_reaper_folding()
