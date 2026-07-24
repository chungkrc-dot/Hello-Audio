import os
import sys
import glob
import librosa
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Add root directory to sys path so we can import src modules
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_parser import parse_midi, parse_midi_with_timing, get_midi_tempo
from src.midi_alignment import get_alignment_mask, calculate_dtw_metrics, apply_octave_folding, get_midi_chroma, get_audio_chroma


def plot_dtw_cost(midi_chroma, audio_chroma, output_path):
    """Recomputes DTW and saves a plot of the Cost Matrix and Alignment Path."""
    import librosa.display
    D, wp = librosa.sequence.dtw(X=midi_chroma, Y=audio_chroma, metric='cosine', subseq=True)
    
    plt.figure(figsize=(10, 8))
    librosa.display.specshow(D, x_axis='frames', y_axis='frames', cmap='gray_r')
    plt.title('DTW Cost Matrix & Alignment Path')
    plt.plot(wp[:, 1], wp[:, 0], label='Optimal Path', color='r', linewidth=2)
    plt.xlabel('Audio Frames')
    plt.ylabel('MIDI Frames (Synthesized)')
    plt.colorbar(label='Cosine Distance')
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

def main():
    print("Starting Hello-Audio Batch Tester (Preset Sweep)...")
    dataset_dir = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '../dataset')))
    
    if not dataset_dir.exists():
        print(f"Error: Dataset directory not found at {dataset_dir}")
        sys.exit(1)
        
    tests_dir = Path(os.path.abspath(os.path.dirname(__file__)))
    output_dir = tests_dir / "batch_results"
    output_dir.mkdir(exist_ok=True)
    plots_dir = output_dir / "test_plots"
    plots_dir.mkdir(exist_ok=True)
    
    # Recursively find all audio files in the dataset
    audio_files = list(dataset_dir.rglob("*.wav"))
    
    presets = {
        "Rapid":  {"min_frames": 1, "rms": 0.01, "slope": 0.20},
        "Medium": {"min_frames": 3, "rms": 0.01, "slope": 0.20},
        "Legato": {"min_frames": 5, "rms": 0.01, "slope": 0.20}
    }
    
    out_csv = output_dir / "test_results.csv"
    # Create empty CSV with headers
    pd.DataFrame(columns=["Filename", "BPM", "Instrument", "Piece", "Yield_Rapid", "Dev_Rapid", "Yield_Medium", "Dev_Medium", "Yield_Legato", "Dev_Legato"]).to_csv(out_csv, index=False)
    
    for audio_path_obj in audio_files:
        audio_path = str(audio_path_obj)
        stem = audio_path_obj.stem
        
        # Skip polyphonic mix files (we only want single isolated instrument tracks)
        if stem.startswith('AuMix'):
            print(f"Skipping {stem}: Polyphonic mix files are out of scope.")
            continue
        
        # Look for a .mid file in the same directory
        parent_dir = audio_path_obj.parent
        midi_files = list(parent_dir.glob("*.mid"))
        if not midi_files:
            print(f"Skipping {stem}: No matching .mid file found.")
            continue
            
        midi_path = str(midi_files[0])
        
        # Extract track index and instrument from filename
        parts = stem.split('_')
        try:
            target_track = int(parts[1])
            inst_code = parts[2]
        except (IndexError, ValueError):
            target_track = None
            inst_code = "vn"
            
        inst_map = {
            "vn": "Violin", "va": "Viola", "vc": "Cello", "db": "Contrabass",
            "fl": "Flute", "ob": "Oboe", "cl": "Clarinet", "bn": "Bassoon",
            "sax": "Saxophone", "tpt": "Trumpet", "hn": "Horn", "tbn": "Trombone", "tba": "Tuba"
        }
        instrument_name = inst_map.get(inst_code, "Violin")
        
        # Exclude non-string instruments
        if instrument_name not in ["Violin", "Viola", "Cello"]:
            print(f"Skipping {stem}: Instrument '{instrument_name}' is not Violin, Viola, or Cello.")
            continue
            
        print(f"\nProcessing: {stem} (Target Track: {target_track}, Instrument: {instrument_name})")
        
        MAX_DURATION = 90.0 # Cap analysis at 1.5 minutes to prevent OOM
        
        # 1. Parse MIDI and truncate to MAX_DURATION
        with open(midi_path, 'rb') as f:
            raw_midi_notes = parse_midi_with_timing(f, target_track=target_track)
            
        if not raw_midi_notes:
            print(f"  [!] No valid notes found in Track {target_track}")
            continue
            
        # Filter MIDI notes that start within the first 90 seconds
        midi_notes = []
        for note in raw_midi_notes:
            start = note['Start_Time'] if isinstance(note, dict) else getattr(note, 'Start_Time', 0)
            if start <= MAX_DURATION:
                midi_notes.append(note)
        
        if not midi_notes:
            print(f"  [!] No valid notes found in the first {MAX_DURATION} seconds.")
            continue
            
        bpm = get_midi_tempo(midi_path)
        
        # 2. Extract raw pitch once per audio file
        with open(audio_path, 'rb') as af:
            y, sr, f0, voiced_flag, rms, _ = extract_pitch_and_rms(
                af, 
                instrument=instrument_name,
                switch_prob=0.005,
                enable_freq_limits=True,
                duration=MAX_DURATION
            )
        
        # Prepare row for CSV
        row_data = {
            "Filename": stem,
            "BPM": round(bpm, 1),
            "Instrument": instrument_name,
            "Piece": parent_dir.name
        }
        
        # Save a plot for DTW
        time_array = librosa.times_like(f0, sr=sr, hop_length=512)
        mask, expected, warped, _ = get_alignment_mask(midi_notes, time_array, y, sr, hop_length=512)
        
        # Memory-saver: Do NOT plot the 7750x7750 DTW Cost Matrix heatmap!
        # Matplotlib uses >20GB of RAM to render it.
        # try:
        #     m_chroma = get_midi_chroma(midi_notes, sr, 512)
        #     a_chroma = get_audio_chroma(y, sr, 512)
        #     plot_path = os.path.join(plots_dir, f"{stem}_dtw.png")
        #     plot_dtw_cost(m_chroma, a_chroma, plot_path)
        # except Exception as e:
        #     print(f"  [!] Failed to generate DTW plot: {e}")
        
        # 3. Iterate through all 3 presets
        for preset_name, params in presets.items():
            print(f"  -> Testing {preset_name} preset...")
            
            # Apply the filter cascade
            pitch_track = analyze_intonation(
                y, sr, f0, voiced_flag, rms,
                rms_threshold=params["rms"],
                min_frames=params["min_frames"],
                max_pitch_slope=params["slope"],
                toggles={'enable_pitch_slope_filter': True, 'enable_minimum_frames': True}
            )
            
            final_f0 = pitch_track['f0']
            final_mask = ~np.isnan(final_f0)
            
            folded_f0_hz, folded_f0_midi = apply_octave_folding(final_f0, expected)
            
            folded_pitch_slope = np.concatenate(([0], np.abs(np.diff(folded_f0_midi))))
            folded_slope_mask = (folded_pitch_slope <= params["slope"]) | np.isnan(folded_pitch_slope)
            
            strict_mask = mask & final_mask & folded_slope_mask
            # Calculate metrics
            metrics_list = calculate_dtw_metrics(midi_notes, time_array, folded_f0_hz, rms, strict_mask, warped)
            
            valid_notes = [n for n in metrics_list if not np.isnan(n['Deviation_Cents'])]
            yield_pct = len(valid_notes) / len(metrics_list) if metrics_list else 0
            mean_dev = np.mean([abs(n['Deviation_Cents']) for n in valid_notes]) if valid_notes else 0
            
            row_data[f"Yield_{preset_name}"] = round(yield_pct * 100, 2)
            row_data[f"Dev_{preset_name}"] = round(mean_dev, 2)
            
            # Delete inner loop vars immediately
            del pitch_track, final_f0, final_mask, folded_f0_hz, folded_f0_midi, folded_pitch_slope, folded_slope_mask, strict_mask, metrics_list, valid_notes
            
        # Append row immediately to CSV so it's safely written before the next file
        pd.DataFrame([row_data]).to_csv(out_csv, mode='a', header=False, index=False)
        print(f"  [+] Data saved for {stem}")
        
        # Aggressive memory management to prevent macOS out-of-memory warnings
        import gc
        del y, sr, f0, voiced_flag, rms, time_array, mask, expected, warped, midi_notes, raw_midi_notes, row_data
        plt.close('all') # Force close all matplotlib backends
        gc.collect() # Force Python to dump the massive arrays from RAM immediately
        
    print(f"\nMicro-Batch testing complete! Results saved to {out_csv}")

if __name__ == "__main__":
    main()
