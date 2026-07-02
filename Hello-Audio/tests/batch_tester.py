import os
import sys
import glob
import librosa
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Add root directory to sys path so we can import src modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import Hello-Audio modules
from src.pitch_engine import extract_pitch_data
from src.midi_parser import parse_midi
from src.midi_alignment import get_alignment_mask, calculate_dtw_metrics, apply_octave_folding, get_midi_chroma, get_audio_chroma
from src.amplitude_analysis import calculate_dBA

def plot_dtw_cost(midi_chroma, audio_chroma, output_path):
    """Recomputes DTW and saves a plot of the Cost Matrix and Alignment Path."""
    import librosa.display
    D, wp = librosa.sequence.dtw(X=midi_chroma, Y=audio_chroma, metric='cosine', subseq=True)
    
    plt.figure(figsize=(10, 8))
    librosa.display.specshow(D, x_axis='frames', y_axis='frames', cmap='gray_r')
    plt.title('DTW Cost Matrix & Alignment Path')
    plt.plot(wp[:, 1], wp[:, 0], label='Optimal Path', color='r', linewidth=2)
    plt.xlabel('Audio Frames')
    plt.ylabel('MIDI Frames')
    plt.legend()
    plt.colorbar(label='Cosine Distance')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()

def main():
    dataset_dir = "dataset"
    plots_dir = "test_plots"
    
    os.makedirs(plots_dir, exist_ok=True)
    
    # We look for all .wav files in the dataset directory recursively
    audio_files = glob.glob(os.path.join(dataset_dir, "**", "*.wav"), recursive=True)
    if not audio_files:
        print(f"No .wav files found in {dataset_dir}/. Please add your files.")
        return

    results = []
    
    print(f"Starting batch testing on {len(audio_files)} files...")
    
    for audio_path in audio_files:
        stem = Path(audio_path).stem
        # Assume MIDI file has same stem: e.g. track1.wav -> track1.mid
        midi_path = os.path.join(dataset_dir, f"{stem}.mid")
        
        if not os.path.exists(midi_path):
            print(f"Skipping {audio_path}: No matching .mid file found.")
            continue
            
        print(f"Processing: {stem}")
        
        # 1. Parse MIDI
        midi_notes, _, _ = parse_midi(midi_path)
        
        # 2. Process Audio (using default parameters as in UI)
        y, sr = librosa.load(audio_path, sr=44100)
        res = extract_pitch_data(
            audio_path, 
            instrument="Violin", 
            analysis_profile="Rapid", 
            rms_threshold=0.01,
            switch_prob=0.005,
            sustain_duration=10,
            max_pitch_slope=0.1
        )
        
        if not res['success']:
            print(f"  [!] Pitch extraction failed for {stem}")
            continue
            
        # 3. DTW Alignment
        time_array = librosa.times_like(res['f0'], sr=res['sr'], hop_length=512)
        mask, expected, warped, _ = get_alignment_mask(midi_notes, time_array, res['y'], res['sr'], hop_length=512)
        
        # Apply octave folding (assuming True for dataset)
        folded_f0_hz, folded_f0_midi = apply_octave_folding(res['f0'], expected)
        
        # Re-apply slope filter on folded pitch
        folded_pitch_slope = np.concatenate(([0], np.abs(np.diff(folded_f0_midi))))
        folded_slope_mask = (folded_pitch_slope <= 0.1) | np.isnan(folded_pitch_slope)
        
        strict_mask = mask & res['final_mask'] & folded_slope_mask
        
        # Calculate DTW Metrics
        metrics = calculate_dtw_metrics(midi_notes, time_array, folded_f0_hz, res['rms'], res['final_mask'], warped)
        
        # 4. Generate Plot
        try:
            m_chroma = get_midi_chroma(midi_notes, res['sr'], 512)
            a_chroma = get_audio_chroma(res['y'], res['sr'], 512)
            plot_path = os.path.join(plots_dir, f"{stem}_dtw.png")
            plot_dtw_cost(m_chroma, a_chroma, plot_path)
            print(f"  Saved DTW plot to {plot_path}")
        except Exception as e:
            print(f"  [!] Failed to generate DTW plot: {e}")
        
        # 5. Evaluate Criteria
        mean_dev_cents = metrics.get('Mean Deviation (Cents)', 9999)
        detection_yield = float(metrics.get('Tracking Yield (%)', '0').strip('%')) if isinstance(metrics.get('Tracking Yield (%)'), str) else 0.0
        inclusion_yield = float(metrics.get('Valid Notes for Calculation (%)', '0').strip('%')) if isinstance(metrics.get('Valid Notes for Calculation (%)'), str) else 0.0
        
        pass_yield = detection_yield >= 90.0
        pass_valid = inclusion_yield >= 90.0
        pass_dev = abs(mean_dev_cents) < 35.0
        
        overall_pass = pass_yield and pass_valid and pass_dev
        
        results.append({
            'Filename': stem,
            'Detection Yield (%)': detection_yield,
            'Valid Included (%)': inclusion_yield,
            'Mean Deviation (Cents)': mean_dev_cents,
            'Dev Std Dev (Cents)': metrics.get('Standard Deviation (Cents)', 0),
            'Yield PASS': pass_yield,
            'Valid PASS': pass_valid,
            'Dev PASS': pass_dev,
            'OVERALL PASS': overall_pass
        })

    # Output report
    if results:
        df = pd.DataFrame(results)
        df.to_csv('test_results.csv', index=False)
        print(f"\nCompleted! Report saved to test_results.csv with {len(results)} entries.")
    else:
        print("\nNo valid tests completed.")

if __name__ == "__main__":
    main()
