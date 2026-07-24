import sys
import os
import glob
import numpy as np
import librosa
import pretty_midi
import matplotlib.pyplot as plt

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
import pitch_engine
import midi_alignment
import midi_parser

DATA_DIR = "/Users/conradchung/Documents/PythonCode/Hello-Audio/dataset"
ARTIFACTS_DIR = "/Users/conradchung/.gemini/antigravity/brain/144bb055-59e2-4a86-9b79-cd054e17846b"

def plot_reaper_folding():
    target_folder = "44_K515_vn_vn_va_va_vc"
    folder_path = os.path.join(DATA_DIR, target_folder)
    
    # We will use the Cello file since it had a high octave fold rate (23%)
    audio_path = os.path.join(folder_path, "5_vc", "AuSep_5_vc_44_K515.wav")
    inst = "Cello"
    
    print(f"Processing {audio_path}...")
    
    # 1. Extract Pitch using REAPER
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
    
    # 2. Load MIDI
    midi_files = glob.glob(os.path.join(folder_path, "Sco_*.mid"))
    midi_path = midi_files[0]
    with open(midi_path, 'rb') as f:
        midi_notes = midi_parser.parse_midi_with_timing(f, target_track=5)
    
    # 3. Get expected pitch via DTW
    _, expected_pitch, _, expected_note_index = midi_alignment.get_alignment_mask(
        midi_notes, time_array, y, sr, hop_length=512, force_global=False
    )
    
    # 4. Find frames that triggered folding
    f0_midi = librosa.hz_to_midi(f0_hz)
    valid_mask = ~np.isnan(f0_midi) & ~np.isnan(expected_pitch)
    
    octave_offsets = np.zeros_like(f0_midi)
    octave_offsets[valid_mask] = np.round((f0_midi[valid_mask] - expected_pitch[valid_mask]) / 12.0)
    
    # Isolate time range specifically around 76.6 seconds
    start_time = 76.4
    end_time = 76.9
    
    start_frame = int(start_time * sr / 512)
    end_frame = int(end_time * sr / 512)
    
    t_plot = time_array[start_frame:end_frame]
    raw_pitch = f0_midi[start_frame:end_frame]
    exp_pitch = expected_pitch[start_frame:end_frame]
    
    # Calculate folded pitch
    f0_midi_oct = raw_pitch - (octave_offsets[start_frame:end_frame] * 12.0)
    
    # PLOT
    plt.figure(figsize=(10, 6))
    plt.plot(t_plot, raw_pitch, 'ro', label='Raw REAPER Pitch', markersize=6, alpha=0.6)
    plt.plot(t_plot, exp_pitch, 'k-', label='Expected Pitch (DTW Ground Truth)', linewidth=2)
    plt.plot(t_plot, f0_midi_oct, 'b.', label='Folded Pitch (Corrected)', markersize=6)
    
    plt.title("REAPER Octave Error and Harmonic Folding Correction (76.6s)")
    plt.xlabel("Time (seconds)")
    plt.ylabel("Pitch (MIDI Note)")
    plt.xlim(start_time, end_time)
    
    # Only show integer MIDI notes on y-axis for clarity
    min_pitch = np.nanmin(np.concatenate((raw_pitch, exp_pitch)))
    max_pitch = np.nanmax(np.concatenate((raw_pitch, exp_pitch)))
    plt.yticks(np.arange(np.floor(min_pitch)-1, np.ceil(max_pitch)+2, 1))
    
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    
    save_path = os.path.join(ARTIFACTS_DIR, "reaper_octave_folding_example.png")
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Saved plot to {save_path}")

if __name__ == '__main__':
    plot_reaper_folding()
