import os
import sys
import numpy as np
import librosa
import pandas as pd
import glob

sys.path.append('/Users/conradchung/Documents/PythonCode/Hello-Audio')
from src.midi_parser import parse_midi_with_timing
from src.pitch_engine import extract_pitch_and_rms, apply_duration_filter
from src.midi_alignment import get_alignment_mask, calculate_dtw_metrics

DATA_DIR = "/Users/conradchung/Documents/PythonCode/Hello-Audio/dataset"
ARTIFACTS_DIR = "/Users/conradchung/.gemini/antigravity/brain/144bb055-59e2-4a86-9b79-cd054e17846b"

def process_instrument(audio_path, midi_path, target_track, inst):
    print(f"Processing {audio_path}...")
    
    with open(audio_path, 'rb') as f:
        # Use pYIN this time
        y, sr, f0_hz, voiced_flag, rms = extract_pitch_and_rms(
            f, inst, 0.005, enable_freq_limits=True, pitch_engine='pYIN'
        )
    
    time_array = librosa.times_like(f0_hz, sr=sr, hop_length=512)
    
    with open(midi_path, 'rb') as f:
        midi_notes = parse_midi_with_timing(f, target_track=target_track)
        
    _, expected_pitch, warped_timeline, _ = get_alignment_mask(
        midi_notes, time_array, y, sr, hop_length=512, force_global=False
    )
    
    final_mask = apply_duration_filter(voiced_flag, min_frames=2)
    
    metrics = calculate_dtw_metrics(midi_notes, time_array, f0_hz, rms, final_mask, warped_timeline)
    
    total_expected = len(metrics)
    detected_count = sum(1 for m in metrics if not np.isnan(m['Deviation_Cents']))
    yield_pct = (detected_count / total_expected) * 100 if total_expected > 0 else 0
    mean_dev_hz = np.nanmean([m['Deviation_Hz'] for m in metrics if not np.isnan(m['Deviation_Hz'])])
    
    return {
        'total_expected': total_expected,
        'detected_count': detected_count,
        'yield_pct': yield_pct,
        'mean_dev_hz': mean_dev_hz
    }

def main():
    results = []
    
    folders = sorted([f for f in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, f))])
    
    for target_folder in folders:
        folder_path = os.path.join(DATA_DIR, target_folder)
        midi_files = glob.glob(os.path.join(folder_path, "Sco_*.mid"))
        if not midi_files:
            continue
        midi_path = midi_files[0]
        
        audio_files = glob.glob(os.path.join(folder_path, "**", "AuSep_*.wav"), recursive=True)
        audio_files.sort()
        
        for audio_path in audio_files:
            basename = os.path.basename(audio_path)
            
            # Extract instrument type
            if "vn" in basename.lower():
                inst = "Violin"
            elif "va" in basename.lower():
                inst = "Viola"
            elif "vc" in basename.lower():
                inst = "Cello"
            elif "db" in basename.lower():
                inst = "Double Bass"
            else:
                continue
                
            track_num = int(basename.split('_')[1])
            
            try:
                res = process_instrument(audio_path, midi_path, track_num, inst)
                res['Dataset'] = target_folder
                res['Track'] = f"{track_num}_{inst.lower()[:2]}"
                res['Instrument'] = inst
                results.append(res)
            except Exception as e:
                print(f"Error processing {audio_path}: {e}")
                
            # Write partial results so we can see progress
            df = pd.DataFrame(results)
            df.to_csv(os.path.join(ARTIFACTS_DIR, "all_strings_pyin_batch_results.csv"), index=False)
            
    print("FINISHED ALL TRACKS!")

if __name__ == '__main__':
    main()
