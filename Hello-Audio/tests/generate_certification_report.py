import os
import sys
import warnings
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
import librosa
import matplotlib.pyplot as plt

# Add root directory to sys path so we can import src modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.amplitude_analysis import analyze_amplitude
from src.midi_alignment import apply_octave_folding, calculate_dtw_metrics

# Create output directory
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "certification_reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_amplitude_proof():
    print("Running Amplitude & Psychoacoustics Proof...")
    sr = 44100
    duration = 5.0 # Longer duration for smoother noise averaging
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    
    # Generate broadband white noise
    np.random.seed(42) # For perfect mathematical reproducibility
    y_noise = np.random.normal(0, 0.5, len(t))
    
    res_noise = analyze_amplitude(y_noise, sr)
    
    df = pd.DataFrame([
        {"Signal": "Broadband White Noise", "dBFS": res_noise["mean_dbfs"], "dBA": res_noise["mean_dba"]}
    ])
    df.to_csv(f"{OUTPUT_DIR}/01_amplitude_proof.csv", index=False)
    
    # Visual Proof: Frequency-Amplitude Spectrum
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    a_weights = librosa.A_weighting(freqs)
    a_weights_amp = 10 ** (a_weights / 20)
    
    # Calculate magnitude spectrum (mean across time)
    S_noise = np.abs(librosa.stft(y_noise, n_fft=2048, hop_length=512)).mean(axis=1)
    
    # Smooth the noise spectrum for visual clarity using a moving average
    window_size = 50
    S_smoothed = np.convolve(S_noise, np.ones(window_size)/window_size, mode='same')
    
    # Apply A-weighting to spectrum
    S_noise_A = S_smoothed * a_weights_amp
    
    # Convert to dB for plotting (referenced to max for clean visualization)
    S_noise_dB = librosa.amplitude_to_db(S_smoothed, ref=np.max)
    S_noise_A_dB = librosa.amplitude_to_db(S_noise_A, ref=np.max)
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    # Plot Unweighted (Before)
    axes[0].plot(freqs, S_noise_dB, label="White Noise Spectrum", color='blue', linewidth=2)
    axes[0].set_xscale('log')
    axes[0].set_xlim([100, 20000])
    axes[0].set_ylim([-60, 5])
    axes[0].set_title("Raw Digital Spectrum (dBFS) - Before Filter")
    axes[0].set_xlabel("Frequency (Hz) [Log Scale]")
    axes[0].set_ylabel("Relative Magnitude (dB)")
    axes[0].legend()
    axes[0].grid(True, which="both", ls="--", alpha=0.5)
    
    # Plot A-Weighted (After)
    axes[1].plot(freqs, S_noise_A_dB, label="Filtered White Noise (dBA)", color='blue', linewidth=2)
    axes[1].plot(freqs, a_weights, label="A-Weighting Transfer Function", color='purple', linestyle='--')
    axes[1].set_xscale('log')
    axes[1].set_xlim([100, 20000])
    axes[1].set_ylim([-60, 5])
    axes[1].set_title("Psychoacoustic Spectrum (dBA) - After Filter")
    axes[1].set_xlabel("Frequency (Hz) [Log Scale]")
    axes[1].legend()
    axes[1].grid(True, which="both", ls="--", alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/01_amplitude_proof_graph.png")
    plt.close()

def run_octave_folding_proof():
    print("Running Octave Folding Proof...")
    
    # Expected MIDI sequence: C4 (60), D4 (62), E4 (64)
    expected_pitch = np.concatenate([
        np.full(33, 60.0), # C4
        np.full(33, 62.0), # D4
        np.full(34, 64.0)  # E4
    ])
    
    expected_hz = librosa.midi_to_hz(expected_pitch)
    
    # Detected Pitch with algorithmic octave errors.
    # pYIN correctly tracks C4 and E4, but makes an octave harmonic error tracking D4 at D5 (MIDI 74)
    # We add a tiny bit of random noise to simulate a real acoustic trace/vibrato
    np.random.seed(42)
    f0_hz = expected_hz.copy() + np.random.normal(0, 1.5, 100)
    
    # Inject the octave error for the middle note
    f0_hz[33:66] = librosa.midi_to_hz(74.0) + np.random.normal(0, 3, 33) 
    
    folded_f0_hz, folded_f0_midi = apply_octave_folding(f0_hz, expected_pitch)
    
    df = pd.DataFrame({
        "Frame": np.arange(100),
        "Expected MIDI": expected_pitch,
        "Expected Hz": expected_hz,
        "Raw Detected (Hz)": f0_hz,
        "Folded Output (Hz)": folded_f0_hz,
        "Folded Output (MIDI)": folded_f0_midi
    })
    df.to_csv(f"{OUTPUT_DIR}/02_octave_folding_proof.csv", index=False)
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    # Graph 1: Unfolded (Raw pYIN)
    axes[0].plot(df["Frame"], df["Expected Hz"], label="Expected Target Path", color='green', linestyle='--', linewidth=2)
    axes[0].plot(df["Frame"], df["Raw Detected (Hz)"], label="Raw pYIN Output (Harmonic Error)", color='red', alpha=0.8, linewidth=2)
    axes[0].set_title("Before: Raw pYIN Tracking")
    axes[0].set_xlabel("Time (Frames)")
    axes[0].set_ylabel("Frequency (Hz)")
    axes[0].legend()
    axes[0].grid(True, which="both", ls="--", alpha=0.5)
    
    # Graph 2: Folded (Corrected)
    axes[1].plot(df["Frame"], df["Expected Hz"], label="Expected Target Path", color='green', linestyle='--', linewidth=2)
    axes[1].plot(df["Frame"], df["Folded Output (Hz)"], label="Folded Corrected Output", color='blue', alpha=0.8, linewidth=3)
    axes[1].set_title("After: Algorithmically Folded Pitch Path")
    axes[1].set_xlabel("Time (Frames)")
    axes[1].legend()
    axes[1].grid(True, which="both", ls="--", alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/02_octave_folding_proof_graph.png")
    plt.close()

def run_dtw_masking_proof():
    print("Running DTW Masking & Intonation Proof...")
    
    # Simulate a DTW warped timeline matching a MIDI note
    time_array = np.linspace(0, 1.0, 100)
    warped_midi = np.linspace(0.5, 1.5, 100) # The matched note runs from 0.5s to 1.5s in MIDI time
    
    # Note dictionary
    midi_notes = [{"Start_Time": 0.5, "End_Time": 1.5, "Pitch": 69, "Pitch_Hz": 440.0, "Expected_Target_Pitch_Hz": 440.0}]
    
    # Detected pitch: perfect 440 Hz, but with NaN holes and a giant slope spike at frame 50
    f0_hz = np.full(100, 440.0)
    f0_hz[20:30] = np.nan # Garbage tracking hole
    f0_hz[50:55] = 460.0 # Sudden glitch spike
    
    # Masks
    rms = np.full(100, 0.1)
    final_mask = ~np.isnan(f0_hz)
    
    # We apply a strict pitch slope mask manually for the test
    f0_midi = librosa.hz_to_midi(np.nan_to_num(f0_hz, nan=0))
    slope = np.concatenate(([0], np.abs(np.diff(f0_midi))))
    slope_mask = (slope <= 0.5)
    strict_mask = final_mask & slope_mask
    
    metrics = calculate_dtw_metrics(midi_notes, time_array, f0_hz, rms, strict_mask, warped_midi)
    
    df = pd.DataFrame(metrics)
    df.to_csv(f"{OUTPUT_DIR}/03_dtw_masking_proof.csv", index=False)
    
    plt.figure(figsize=(10, 5))
    plt.plot(time_array, f0_hz, label="Raw Pitch (With Glitches/Holes)", color='red', alpha=0.5)
    
    clean_f0 = f0_hz.copy()
    clean_f0[~strict_mask] = np.nan
    plt.plot(time_array, clean_f0, label="Masked Pitch (Strict Plateau)", color='blue', linewidth=3)
    
    plt.axhline(y=metrics[0]["Median_Detected_Pitch_Hz"], color='green', linestyle='--', label=f"Extracted Median ({metrics[0]['Median_Detected_Pitch_Hz']} Hz)")
    plt.title("DTW Masking & Robust Median Extraction Proof")
    plt.xlabel("Time (s)")
    plt.ylabel("Frequency (Hz)")
    plt.legend()
    plt.grid(True)
    plt.savefig(f"{OUTPUT_DIR}/03_dtw_masking_proof_graph.png")
    plt.close()

def run_chroma_cqt_proof():
    print("Running Chroma CQT Octave-Agnostic Proof...")
    sr = 22050
    hop_length = 512
    
    # Synthesize C3 (130 Hz), C4 (261 Hz), G3 (196 Hz)
    t_05 = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    y_chroma_test = np.concatenate([
        np.sin(2 * np.pi * librosa.midi_to_hz(48) * t_05), # C3
        np.sin(2 * np.pi * librosa.midi_to_hz(60) * t_05), # C4
        np.sin(2 * np.pi * librosa.midi_to_hz(55) * t_05)  # G3
    ])
    
    # Before: Standard STFT Spectrogram (Linear Frequency)
    S = np.abs(librosa.stft(y_chroma_test, n_fft=2048, hop_length=hop_length))
    S_dB = librosa.amplitude_to_db(S, ref=np.max)
    
    # After: Chroma CQT (12 Pitch Classes)
    chroma_matrix = librosa.feature.chroma_cqt(y=y_chroma_test, sr=sr, hop_length=hop_length)
    
    # Export the Chroma Table
    pitch_classes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    df_chroma = pd.DataFrame(chroma_matrix.T, columns=pitch_classes)
    df_chroma.insert(0, "Time_Frame", np.arange(len(df_chroma)))
    labels = ["C3 (Octave 3)"] * (len(df_chroma) // 3) + ["C4 (Octave 4)"] * (len(df_chroma) // 3) + ["G3 (Octave 3)"] * (len(df_chroma) - 2 * (len(df_chroma) // 3))
    df_chroma.insert(1, "Input_Signal", labels)
    df_chroma.to_csv(f"{OUTPUT_DIR}/04_chroma_cqt_proof.csv", index=False)
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    # Graph 1: Standard Linear Spectrogram (Before)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    img1 = axes[0].imshow(S_dB, aspect='auto', origin='lower', cmap='magma', extent=[0, 1.5, freqs[0], freqs[-1]])
    axes[0].set_ylim(0, 400) # Zoom in to the low frequencies where our notes are
    axes[0].set_title("Before: Raw Digital Spectrogram (Hz)")
    axes[0].set_xlabel("Time (s) [C3 -> C4 -> G3]")
    axes[0].set_ylabel("Absolute Frequency (Hz)")
    axes[0].text(0.25, librosa.midi_to_hz(48)+20, "C3 (130 Hz)", color="white", ha="center")
    axes[0].text(0.75, librosa.midi_to_hz(60)+20, "C4 (261 Hz)", color="white", ha="center")
    axes[0].text(1.25, librosa.midi_to_hz(55)+20, "G3 (196 Hz)", color="white", ha="center")
    
    # Graph 2: Chroma CQT (After)
    img2 = axes[1].imshow(chroma_matrix, aspect='auto', origin='lower', cmap='viridis', extent=[0, 1.5, 0, 12])
    axes[1].set_title("After: Chroma CQT Filter")
    axes[1].set_xlabel("Time (s) [C3 -> C4 -> G3]")
    axes[1].set_ylabel("Pitch Class (12 Bins)")
    axes[1].set_yticks(np.arange(12) + 0.5)
    axes[1].set_yticklabels(pitch_classes)
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/04_chroma_cqt_proof_graph.png")
    plt.close()

def run_chroma_dtw_advantage_proof():
    print("Running Chroma vs STFT DTW Advantage Proof...")
    sr = 22050
    hop_length = 512
    
    # 1. Synthesize MIDI Target: C4 (1s) -> D4 (1s)
    t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False)
    y_midi = np.concatenate([
        np.sin(2 * np.pi * librosa.midi_to_hz(60) * t[:len(t)//2]),
        np.sin(2 * np.pi * librosa.midi_to_hz(62) * t[len(t)//2:])
    ])
    
    # 2. Synthesize Human Audio: Played an octave HIGHER! C5 (1s) -> D5 (1s)
    y_human = np.concatenate([
        np.sin(2 * np.pi * librosa.midi_to_hz(72) * t[:len(t)//2]),
        np.sin(2 * np.pi * librosa.midi_to_hz(74) * t[len(t)//2:])
    ])
    
    # --- Absolute Frequency DTW (STFT) ---
    stft_midi = np.abs(librosa.stft(y_midi, n_fft=2048, hop_length=hop_length))
    stft_human = np.abs(librosa.stft(y_human, n_fft=2048, hop_length=hop_length))
    
    from scipy.spatial.distance import cdist
    # Compute instantaneous cross-similarity matrix (Cost Matrix)
    # We clip the STFT to the bottom 100 bins (up to ~1000Hz) to clearly focus on our notes
    cost_stft = cdist(stft_human[:100, :].T, stft_midi[:100, :].T, metric='cosine')
    
    # --- 12-Bin Chroma CQT DTW ---
    chroma_midi = librosa.feature.chroma_cqt(y=y_midi, sr=sr, hop_length=hop_length)
    chroma_human = librosa.feature.chroma_cqt(y=y_human, sr=sr, hop_length=hop_length)
    
    cost_chroma = cdist(chroma_human.T, chroma_midi.T, metric='cosine')
    
    # Visual Proof
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    # Graph 1: STFT Cost Matrix
    im1 = axes[0].imshow(cost_stft, aspect='auto', origin='lower', cmap='magma')
    axes[0].set_title("Before: Absolute Frequency Alignment Cost Matrix\nTarget = C4/D4 | Human = C5/D5")
    axes[0].set_xlabel("Target MIDI Frames")
    axes[0].set_ylabel("Human Audio Frames")
    fig.colorbar(im1, ax=axes[0], label="Mismatch Error Cost (Bright = Total Failure)")
    
    # Graph 2: Chroma CQT Cost Matrix
    im2 = axes[1].imshow(cost_chroma, aspect='auto', origin='lower', cmap='magma')
    axes[1].set_title("After: 12-Bin Chroma CQT Alignment Cost Matrix\n(Octave Errors Mathematically Erased)")
    axes[1].set_xlabel("Target MIDI Frames")
    axes[1].set_ylabel("Human Audio Frames")
    fig.colorbar(im2, ax=axes[1], label="Mismatch Error Cost (Dark = Perfect Alignment)")
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/06_chroma_dtw_advantage_proof_graph.png")
    plt.close()

def run_dtw_alignment_proof():
    print("Running DTW Temporal Alignment Proof...")
    sr = 22050
    hop_length = 512
    
    # 1. Synthesize "Perfect" MIDI Audio: C4 (1s), D4 (1s), E4 (1s)
    t_1 = np.linspace(0, 1.0, int(sr * 1.0), endpoint=False)
    y_midi = np.concatenate([
        np.sin(2 * np.pi * librosa.midi_to_hz(60) * t_1),
        np.sin(2 * np.pi * librosa.midi_to_hz(62) * t_1),
        np.sin(2 * np.pi * librosa.midi_to_hz(64) * t_1)
    ])
    
    # 2. Synthesize "Human" Audio: Skewed timing -> C4 (1.5s), D4 (0.5s), E4 (1.0s)
    t_1_5 = np.linspace(0, 1.5, int(sr * 1.5), endpoint=False)
    t_0_5 = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    y_human = np.concatenate([
        np.sin(2 * np.pi * librosa.midi_to_hz(60) * t_1_5),
        np.sin(2 * np.pi * librosa.midi_to_hz(62) * t_0_5),
        np.sin(2 * np.pi * librosa.midi_to_hz(64) * t_1)
    ])
    
    # 3. Create a synthetic "pYIN" trace based on the Human Audio (Frequency in Hz)
    np.random.seed(42)
    pyin_human = np.concatenate([
        np.full(int(sr * 1.5) // hop_length, librosa.midi_to_hz(60)) + np.random.normal(0, 1.5, int(sr * 1.5) // hop_length),
        np.full(int(sr * 0.5) // hop_length, librosa.midi_to_hz(62)) + np.random.normal(0, 1.5, int(sr * 0.5) // hop_length),
        np.full(int(sr * 1.0) // hop_length, librosa.midi_to_hz(64)) + np.random.normal(0, 1.5, int(sr * 1.0) // hop_length)
    ])
    
    chroma_midi = librosa.feature.chroma_cqt(y=y_midi, sr=sr, hop_length=hop_length)
    chroma_human = librosa.feature.chroma_cqt(y=y_human, sr=sr, hop_length=hop_length)
    
    # Ensure pyin array size perfectly matches chroma frame size
    min_len_human = min(len(pyin_human), chroma_human.shape[1])
    pyin_human = pyin_human[:min_len_human]
    chroma_human = chroma_human[:, :min_len_human]
    
    # 4. Perform DTW entirely on the Chroma CQT Matrices
    D, wp = librosa.sequence.dtw(X=chroma_human, Y=chroma_midi, metric='cosine')
    
    # Map the expected MIDI targets (Frequency in Hz)
    midi_targets_hz = np.concatenate([
        np.full(int(sr * 1.0) // hop_length, librosa.midi_to_hz(60)),
        np.full(int(sr * 1.0) // hop_length, librosa.midi_to_hz(62)),
        np.full(int(sr * 1.0) // hop_length, librosa.midi_to_hz(64))
    ])
    min_len_midi = min(len(midi_targets_hz), chroma_midi.shape[1])
    midi_targets_hz = midi_targets_hz[:min_len_midi]
    chroma_midi = chroma_midi[:, :min_len_midi]
    
    # 5. Apply the Chroma DTW Warping Path to the pYIN trace timeline
    warped_pyin = np.zeros_like(midi_targets_hz)
    for midi_idx in range(len(midi_targets_hz)):
        matches = wp[wp[:, 1] == midi_idx]
        if len(matches) > 0:
            human_idx = matches[0, 0]
            if human_idx < len(pyin_human):
                warped_pyin[midi_idx] = pyin_human[human_idx]
            else:
                warped_pyin[midi_idx] = pyin_human[-1]
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    time_midi = np.linspace(0, 3.0, len(midi_targets_hz))
    time_human = np.linspace(0, 3.0, len(pyin_human))
    
    # Graph 1: Before DTW
    axes[0].plot(time_midi, midi_targets_hz, label="Target MIDI Grid (1.0s each)", color='green', linestyle='--', linewidth=3)
    axes[0].plot(time_human, pyin_human, label="Raw pYIN Output (Skewed Timing)", color='red', alpha=0.8, linewidth=2)
    axes[0].set_title("Before: pYIN Trace vs MIDI Target (Temporal Mismatch)")
    axes[0].set_xlabel("Time (s)")
    axes[0].set_ylabel("Frequency (Hz)")
    axes[0].legend(loc="lower right")
    axes[0].grid(True, ls="--", alpha=0.5)
    
    # Graph 2: After DTW
    axes[1].plot(time_midi, midi_targets_hz, label="Target MIDI Grid (1.0s each)", color='green', linestyle='--', linewidth=3)
    axes[1].plot(time_midi, warped_pyin, label="DTW-Warped pYIN Trace", color='blue', alpha=0.8, linewidth=3)
    axes[1].set_title("After: DTW Chroma Warping applied to pYIN Trace")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Frequency (Hz)")
    axes[1].legend(loc="lower right")
    axes[1].grid(True, ls="--", alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/05_dtw_alignment_proof_graph.png")
    plt.close()

if __name__ == "__main__":
    print("Initiating Hello-Audio Mathematical Certification Suite...")
    run_amplitude_proof()
    run_octave_folding_proof()
    run_dtw_masking_proof()
    run_chroma_cqt_proof()
    run_chroma_dtw_advantage_proof()
    run_dtw_alignment_proof()
    print(f"Certification complete. All proofs saved to: {OUTPUT_DIR}/")
