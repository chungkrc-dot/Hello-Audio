import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
import json

# Add root directory to sys path so we can import src modules
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_parser import parse_midi_with_timing
from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics, is_note_excluded

def analyze_track():
    dataset_dir = Path("dataset (Strings only)/44_K515_vn_vn_va_va_vc")
    
    targets = [
        ("1_vn", "Violin", 1, "AuSep_1_vn_44_K515.wav", "AuSep_1_vn_44_K515-Violin,_Violin_I.mid"),
        ("3_va", "Viola", 3, "AuSep_3_va_44_K515.wav", "AuSep_1_vn_44_K515-Violas,_Viola_I.mid"),
        ("4_va", "Viola", 4, "AuSep_4_va_44_K515.wav", "AuSep_1_vn_44_K515-Violas,_Viola_II.mid")
    ]
    
    results = []
    
    engines = {
        "REAPER": {"switch_prob": 0.05, "rms_threshold": 0.01, "min_frames": 5, "max_pitch_slope": 5.0},
        "pYIN": {"switch_prob": 0.05, "rms_threshold": 0.01, "min_frames": 5, "max_pitch_slope": 5.0}
    }
    
    toggles = {
        "freq_limits": True,
        "slope_filter": True,
        "duration_filter": True,
        "locked_target": True,
        "harmonic_folding": True,
        "force_global": True
    }
    
    for folder, inst, track_idx, wav_name, mid_name in targets:
        wav_path = dataset_dir / folder / wav_name
        mid_path = dataset_dir / folder / mid_name
        
        stem = Path(wav_name).stem
        print(f"\nProcessing {stem}...")
        
        with open(mid_path, 'rb') as f:
            # We already know the files have isolated tracks, so it's likely track 0 or 1.
            midi_notes = parse_midi_with_timing(f, target_track=1)
            if not midi_notes:
                f.seek(0)
                midi_notes = parse_midi_with_timing(f, target_track=0)
                
        if not midi_notes:
            print(f"  Failed to parse notes for {stem}")
            continue
            
        row_data = {
            "Filename": stem,
            "BPM": 100.0,
            "Instrument": inst,
            "Piece": "44_K515_vn_vn_va_va_vc"
        }
        
        for engine, params in engines.items():
            print(f"  -> Testing {engine}...")
            
            with open(wav_path, 'rb') as af:
                y, sr, f0, voiced_flag, rms = extract_pitch_and_rms(
                    af, instrument=inst, switch_prob=params['switch_prob'],
                    enable_freq_limits=toggles['freq_limits'], pitch_engine=engine
                )
                
            res = analyze_intonation(
                y, sr, f0, voiced_flag, rms, 
                rms_threshold=params['rms_threshold'], 
                min_frames=params['min_frames'], 
                max_pitch_slope=params['max_pitch_slope'], 
                toggles=toggles
            )
            final_mask = res['final_mask']
            
            time_array, expected, warped, expected_note_index, folded_f0_hz, folded_f0_midi, strict_mask, correction_array = process_dtw_alignment(
                midi_notes, f0, y, sr, final_mask, toggles, params['max_pitch_slope']
            )
            
            dtw_metrics = calculate_dtw_metrics(
                midi_notes, time_array, folded_f0_hz, rms, final_mask, warped, correction_array
            )
            
            if not dtw_metrics:
                row_data[f"Det_Yield_{engine}"] = 0.0
                row_data[f"Inc_Yield_{engine}"] = 0.0
                row_data[f"Dev_Hz_{engine}"] = 0.0
                continue
                
            total_notes = len(dtw_metrics)
            valid_detected_notes = [n for n in dtw_metrics if not np.isnan(n.get('Deviation_Cents', np.nan))]
            det_yield = len(valid_detected_notes) / total_notes if total_notes > 0 else 0
            
            included_notes = [n for n in valid_detected_notes if not is_note_excluded(n)]
            inc_yield = len(included_notes) / total_notes if total_notes > 0 else 0
            
            mean_dev_hz = np.mean([n['Deviation_Hz'] for n in included_notes]) if included_notes else 0
            
            row_data[f"Det_Yield_{engine}"] = round(det_yield * 100, 2)
            row_data[f"Inc_Yield_{engine}"] = round(inc_yield * 100, 2)
            row_data[f"Dev_Hz_{engine}"] = round(mean_dev_hz, 2)
            
        results.append(row_data)
        
    out_path = Path("tests/outputs/batch_results/missed_k515_results.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(out_path, index=False)
        
    print(f"\nDone! Results saved to {out_path}")

if __name__ == "__main__":
    analyze_track()
