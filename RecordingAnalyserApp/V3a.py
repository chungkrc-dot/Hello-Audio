import streamlit as st
import librosa
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pretty_midi
import tempfile
import os

st.set_page_config(layout="wide")
st.title("Acoustic Analysis: Segment-to-Sequence Mapping")

# --- 1. Instrument Configuration ---
instrument_config = {
    "Violin": {"fmin": 190, "fmax": 3500},
    "Viola": {"fmin": 130, "fmax": 2500},
    "Cello": {"fmin": 60, "fmax": 1500}
}

st.sidebar.header("Settings")
inst_type = st.sidebar.selectbox("Select Instrument", list(instrument_config.keys()))
participant_id = st.sidebar.text_input("Participant ID", "P01")

# --- 2. File Uploaders ---
st.header("Upload Files")
st.markdown(
    "Upload audio recordings for A-B comparison and a **MIDI file** (.mid) "
    "to establish the target pitch sequence for segment-to-sequence mapping."
)

col1, col2, col3 = st.columns(3)
with col1:
    unplugged_file = st.file_uploader("Unplugged Recording", type=['wav', 'mp3', 'm4a'])
with col2:
    plugged_file = st.file_uploader("Plugged Recording", type=['wav', 'mp3', 'm4a'])
with col3:
    midi_file = st.file_uploader("MIDI Reference File", type=['mid'])

# --- 3. MIDI Sequence Extraction ---
@st.cache_data
def extract_midi_sequence(midi_bytes):
    """Extracts an ordered list of MIDI note pitches from a .mid file.
    
    Args:
        midi_bytes: Raw bytes of the uploaded MIDI file.
    
    Returns:
        List of MIDI note numbers (integers) in temporal order,
        or None if input is None.
    """
    if midi_bytes is None:
        return None
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mid') as tm:
        tm.write(midi_bytes)
        m_path = tm.name
    
    try:
        midi = pretty_midi.PrettyMIDI(m_path)
        # Collect all non-drum notes across instruments, sorted by onset time
        all_notes = []
        for instrument in midi.instruments:
            if not instrument.is_drum:
                for note in instrument.notes:
                    all_notes.append((note.start, note.pitch))
        
        # Sort by onset time and return the ordered pitch sequence
        all_notes.sort(key=lambda x: x[0])
        return [pitch for _, pitch in all_notes]
    
    except Exception as e:
        st.error(f"⚠️ Failed to parse MIDI file: {e}")
        return None
    
    finally:
        if os.path.exists(m_path):
            os.remove(m_path)

# --- 4. Audio Processing with Segment-to-Sequence Mapping ---
@st.cache_data
def extract_metrics(file_bytes, fmin, fmax, midi_sequence=None):
    """Processes audio and performs segment-to-sequence mapping against MIDI targets.
    
    If a midi_sequence is provided, onset detection segments the audio into notes,
    and each segment's median pitch is compared to the corresponding MIDI target.
    Otherwise, falls back to nearest-semitone deviation analysis.
    
    Args:
        file_bytes: Raw bytes of the uploaded audio file.
        fmin: Minimum frequency for pYIN pitch tracking.
        fmax: Maximum frequency for pYIN pitch tracking.
        midi_sequence: Optional list of MIDI note numbers for segment mapping.
    
    Returns:
        Dict with:
          'metrics': [db_fs, db_a, cents_dev, hz_dev]
          'pitch_track': {times, f0, target_hz} for visualisation
          'segment_table': DataFrame of per-segment deviations (or None)
          'warnings': list of warning strings
    """
    empty_result = {
        "metrics": [None, None, None, None],
        "pitch_track": None,
        "segment_table": None,
        "warnings": []
    }
    
    if file_bytes is None:
        return empty_result
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as ta:
        ta.write(file_bytes)
        a_path = ta.name
        
    try:
        y, sr = librosa.load(a_path, sr=22050)
        hop_length = 512
        warnings = []
        
        # A. Amplitude Metrics — dB Full Scale (linear RMS)
        rms_raw = np.sqrt(np.mean(y**2))
        db_fs = 20 * np.log10(rms_raw + 1e-9)
        
        # B. Amplitude Metrics — dB(A) weighted
        S = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sr)
        a_weights_db = librosa.A_weighting(freqs)
        a_weights_linear = librosa.db_to_power(a_weights_db)
        weighted_S2 = (S**2) * a_weights_linear[:, np.newaxis]
        db_a = 10 * np.log10(np.mean(weighted_S2) + 1e-9)
        
        # C. pYIN Pitch Tracking (full track for visualisation)
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=fmin, fmax=fmax, sr=sr,
            hop_length=hop_length,
            no_trough_prob=0.01, switch_prob=0.001
        )
        times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop_length)
        
        # Prepare display arrays
        f0_display = f0.copy()
        valid_mask = voiced_flag & (f0 > 0)
        f0_display[~valid_mask] = np.nan
        
        # D. Segment-to-Sequence Mapping (if MIDI provided)
        if midi_sequence is not None and len(midi_sequence) > 0:
            # Detect note onsets in the audio
            onset_frames = librosa.onset.onset_detect(
                y=y, sr=sr, hop_length=hop_length,
                backtrack=True
            )
            onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop_length)
            
            # Build segment boundaries: [onset_0, onset_1, ..., onset_n, end_of_audio]
            total_duration = len(y) / sr
            boundaries = np.append(onset_times, total_duration)
            num_segments = len(onset_frames)
            num_midi_notes = len(midi_sequence)
            
            if num_segments != num_midi_notes:
                warnings.append(
                    f"⚠️ Segment count mismatch: detected **{num_segments}** audio segments "
                    f"but MIDI contains **{num_midi_notes}** notes. "
                    f"Mapping will use the first {min(num_segments, num_midi_notes)} pairs."
                )
            
            num_pairs = min(num_segments, num_midi_notes)
            
            # Per-segment analysis
            seg_data = []
            all_cents_devs = []
            all_hz_devs = []
            
            # Build target Hz array for visualisation (same length as f0)
            target_hz_track = np.full_like(f0, np.nan, dtype=float)
            
            for i in range(num_pairs):
                seg_start = boundaries[i]
                seg_end = boundaries[i + 1]
                midi_note = midi_sequence[i]
                target_hz = librosa.midi_to_hz(midi_note)
                
                # Find f0 frames within this segment
                seg_mask = (times >= seg_start) & (times < seg_end) & valid_mask
                f0_in_seg = f0[seg_mask]
                
                # Fill the target Hz track for this segment's time range
                time_mask = (times >= seg_start) & (times < seg_end)
                target_hz_track[time_mask] = target_hz
                
                if len(f0_in_seg) == 0:
                    seg_data.append({
                        "Segment": i + 1,
                        "Time Start (s)": round(seg_start, 3),
                        "Time End (s)": round(seg_end, 3),
                        "MIDI Note": midi_note,
                        "Target (Hz)": round(target_hz, 2),
                        "Median Performed (Hz)": np.nan,
                        "Deviation (Cents)": np.nan,
                        "Deviation (Hz)": np.nan
                    })
                    continue
                
                median_f0 = np.median(f0_in_seg)
                
                # Cents deviation: 1200 * log2(performed / target)
                cents_dev = 1200 * np.log2(median_f0 / target_hz)
                hz_dev = median_f0 - target_hz
                
                all_cents_devs.append(abs(cents_dev))
                all_hz_devs.append(abs(hz_dev))
                
                seg_data.append({
                    "Segment": i + 1,
                    "Time Start (s)": round(seg_start, 3),
                    "Time End (s)": round(seg_end, 3),
                    "MIDI Note": midi_note,
                    "Target (Hz)": round(target_hz, 2),
                    "Median Performed (Hz)": round(median_f0, 2),
                    "Deviation (Cents)": round(cents_dev, 2),
                    "Deviation (Hz)": round(hz_dev, 2)
                })
            
            segment_df = pd.DataFrame(seg_data)
            
            # Mean absolute deviations across all valid segments
            mean_cents = np.mean(all_cents_devs) if all_cents_devs else np.nan
            mean_hz = np.mean(all_hz_devs) if all_hz_devs else np.nan
            
            return {
                "metrics": [db_fs, db_a, mean_cents, mean_hz],
                "pitch_track": {"times": times, "f0": f0_display, "target_hz": target_hz_track},
                "segment_table": segment_df,
                "warnings": warnings
            }
        
        else:
            # E. Fallback: nearest-semitone deviation (no MIDI provided)
            f0_valid = f0[valid_mask]
            semitone_hz = np.full_like(f0, np.nan)
            
            if len(f0_valid) == 0:
                return {
                    "metrics": [db_fs, db_a, np.nan, np.nan],
                    "pitch_track": {"times": times, "f0": f0_display, "target_hz": semitone_hz},
                    "segment_table": None,
                    "warnings": []
                }
            
            midi_fractional = librosa.hz_to_midi(f0_valid)
            midi_target = np.round(midi_fractional)
            semitone_hz[valid_mask] = librosa.midi_to_hz(midi_target)
            
            cents_dev = np.mean(np.abs((midi_fractional - midi_target) * 100))
            hz_target = librosa.midi_to_hz(midi_target)
            hz_dev = np.mean(np.abs(f0_valid - hz_target))
            
            return {
                "metrics": [db_fs, db_a, cents_dev, hz_dev],
                "pitch_track": {"times": times, "f0": f0_display, "target_hz": semitone_hz},
                "segment_table": None,
                "warnings": []
            }
    
    except Exception as e:
        st.error(f"⚠️ Failed to process audio file: {e}")
        return empty_result
        
    finally:
        if os.path.exists(a_path):
            os.remove(a_path)

# --- 5. Math Helper ---
def safe_subtract(a, b):
    """Returns a - b, or NaN if either value is missing."""
    if a is None or pd.isna(a) or b is None or pd.isna(b):
        return np.nan
    return a - b

# --- 6. Main Execution ---
if st.button("Generate Comparative Analysis", type="primary"):
    progress = st.progress(0, text="Starting analysis...")
    
    fmin = instrument_config[inst_type]["fmin"]
    fmax = instrument_config[inst_type]["fmax"]
    
    # Read file bytes upfront (with seek to handle Streamlit re-runs)
    def get_bytes(uploaded_file):
        if uploaded_file is None:
            return None
        uploaded_file.seek(0)
        return uploaded_file.getvalue()
    
    unplug_bytes = get_bytes(unplugged_file)
    plug_bytes = get_bytes(plugged_file)
    midi_bytes = get_bytes(midi_file)
    
    # Extract the MIDI target sequence
    progress.progress(5, text="Parsing MIDI reference...")
    midi_sequence = extract_midi_sequence(midi_bytes)
    
    if midi_sequence is not None:
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**MIDI Notes Detected:** {len(midi_sequence)}")
        st.sidebar.markdown(f"**Sequence:** {midi_sequence}")
    
    # Extract metrics with segment-to-sequence mapping
    progress.progress(10, text="Analysing Unplugged recording...")
    unplug_result = extract_metrics(unplug_bytes, fmin, fmax, midi_sequence)
    unplug_db_fs, unplug_db_a, unplug_cents, unplug_hz = unplug_result["metrics"]
    
    progress.progress(40, text="Analysing Plugged recording...")
    plug_result = extract_metrics(plug_bytes, fmin, fmax, midi_sequence)
    plug_db_fs, plug_db_a, plug_cents, plug_hz = plug_result["metrics"]
    
    progress.progress(70, text="Analysing MIDI Baseline audio...")
    # MIDI baseline uses nearest-semitone fallback (no segment mapping against itself)
    midi_audio_result = extract_metrics(None, fmin, fmax, None)
    midi_db_fs, midi_db_a, midi_cents, midi_hz = midi_audio_result["metrics"]
    
    progress.progress(90, text="Building comparison table...")
    
    # --- 7. Display Warnings ---
    all_warnings = []
    for label, result in [("Unplugged", unplug_result), ("Plugged", plug_result)]:
        for w in result["warnings"]:
            all_warnings.append(f"**{label}:** {w}")
    
    if all_warnings:
        st.divider()
        for w in all_warnings:
            st.warning(w)

    # --- 8. Constructing the Data Table ---
    data = {
        "Mean RMS Amplitude (dB FS)": [
            unplug_db_fs, 
            plug_db_fs, 
            safe_subtract(plug_db_fs, unplug_db_fs)
        ],
        "Mean RMS Amplitude (dB A)": [
            unplug_db_a, 
            plug_db_a, 
            safe_subtract(plug_db_a, unplug_db_a)
        ],
        "Mean Abs Dev (Cents)": [
            unplug_cents, 
            plug_cents, 
            safe_subtract(plug_cents, unplug_cents)
        ],
        "Mean Abs Dev (Hz)": [
            unplug_hz, 
            plug_hz, 
            safe_subtract(plug_hz, unplug_hz)
        ],
    }
    
    row_labels = ["Unplugged Condition", "Plugged Condition", "Delta (Plugged - Unplugged)"]
    df = pd.DataFrame(data, index=row_labels)
    
    # Colour-code the delta row
    def highlight_delta(row):
        if row.name == "Delta (Plugged - Unplugged)":
            return [
                'color: green' if pd.notna(v) and v < 0 
                else 'color: red' if pd.notna(v) and v > 0 
                else '' 
                for v in row
            ]
        return ['' for _ in row]
    
    styled_df = df.style.apply(highlight_delta, axis=1).format(
        lambda x: f"{x:.2f}" if pd.notna(x) else ""
    )
    
    progress.progress(100, text="Analysis complete!")
    
    # --- 9. Display Results ---
    deviation_method = "Segment-to-Sequence (MIDI)" if midi_sequence else "Nearest Semitone (no MIDI)"
    st.subheader(f"Analysis Results — {deviation_method}")
    st.dataframe(styled_df, use_container_width=True)
    
    # --- 10. CSV Export ---
    csv = df.to_csv(index=True)
    st.download_button(
        "📥 Download Summary CSV", 
        csv, 
        file_name=f"{participant_id}_comparative_analysis.csv",
        mime="text/csv"
    )
    
    # --- 11. Per-Segment Detail Tables ---
    segment_results = [
        ("Unplugged", unplug_result),
        ("Plugged", plug_result)
    ]
    
    has_segment_tables = any(r["segment_table"] is not None for _, r in segment_results)
    
    if has_segment_tables:
        st.subheader("Per-Segment Deviation Details")
        
        tabs = st.tabs([label for label, r in segment_results if r["segment_table"] is not None])
        tab_idx = 0
        for label, result in segment_results:
            if result["segment_table"] is not None:
                with tabs[tab_idx]:
                    st.dataframe(result["segment_table"], use_container_width=True, hide_index=True)
                    
                    seg_csv = result["segment_table"].to_csv(index=False)
                    st.download_button(
                        f"📥 Download {label} Segments CSV",
                        seg_csv,
                        file_name=f"{participant_id}_{label.lower()}_segments.csv",
                        mime="text/csv",
                        key=f"dl_{label.lower()}_seg"
                    )
                tab_idx += 1
    
    # --- 12. Pitch Track Visualisations ---
    st.subheader("Pitch Track Visualisations")
    
    tracks = [
        ("Unplugged", unplug_result),
        ("Plugged", plug_result),
    ]
    
    for label, result in tracks:
        pt = result["pitch_track"]
        if pt is None:
            continue
        
        fig = go.Figure()
        
        # Target reference (MIDI target or nearest semitone, step-like)
        target_label = "MIDI Target" if midi_sequence else "Nearest Semitone"
        fig.add_trace(go.Scatter(
            x=pt["times"], y=pt["target_hz"],
            name=target_label,
            mode="lines",
            line=dict(color="rgba(255, 165, 0, 0.6)", width=3, shape="hv"),
        ))
        
        # Detected pitch (continuous line)
        fig.add_trace(go.Scatter(
            x=pt["times"], y=pt["f0"],
            name="Detected Pitch (pYIN)",
            mode="lines",
            line=dict(color="rgba(65, 105, 225, 0.9)", width=1.5),
        ))
        
        fig.update_layout(
            title=f"{label} — Pitch Track vs {target_label}",
            xaxis_title="Time (s)",
            yaxis_title="Frequency (Hz)",
            legend_title="Legend",
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)
