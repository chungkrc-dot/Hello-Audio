import streamlit as st
import librosa
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import tempfile
import os

st.set_page_config(layout="wide")
st.title("Acoustic Analysis: Comparative Data Table")

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
st.header("Upload Audio Files")
st.markdown("Upload any combination of files. Missing conditions will be left blank in the data table.")

col1, col2, col3 = st.columns(3)
with col1:
    unplugged_file = st.file_uploader("Unplugged Recording", type=['wav', 'mp3', 'm4a'])
with col2:
    plugged_file = st.file_uploader("Plugged Recording", type=['wav', 'mp3', 'm4a'])
with col3:
    midi_file = st.file_uploader("MIDI Baseline Audio", type=['wav', 'mp3', 'm4a'])

# --- 3. Processing Logic (cached to avoid re-processing on re-runs) ---
@st.cache_data
def extract_metrics(file_bytes, fmin, fmax):
    """Processes audio bytes and returns metrics and pitch track data.
    
    Args:
        file_bytes: Raw bytes of the uploaded audio file.
        fmin: Minimum frequency for pYIN pitch tracking.
        fmax: Maximum frequency for pYIN pitch tracking.
    
    Returns:
        Dict with 'metrics' ([db_fs, db_a, cents_dev, hz_dev]) and
        'pitch_track' ({times, f0, semitone_hz}) or None if input is None.
    """
    if file_bytes is None:
        return {"metrics": [None, None, None, None], "pitch_track": None}
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as ta:
        ta.write(file_bytes)
        a_path = ta.name
        
    try:
        y, sr = librosa.load(a_path, sr=22050)
        hop_length = 512
        
        # A. Amplitude Metrics — dB Full Scale (linear RMS)
        rms_raw = np.sqrt(np.mean(y**2))
        db_fs = 20 * np.log10(rms_raw + 1e-9)
        
        # B. Amplitude Metrics — dB(A) weighted
        #    A-weighting is applied per-frequency-bin before averaging over time.
        #    Note: This is a relative value, not calibrated SPL.
        S = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sr)
        a_weights_db = librosa.A_weighting(freqs)
        a_weights_linear = librosa.db_to_power(a_weights_db)
        
        # Apply A-weighting per frequency bin, then compute mean across all bins and time frames
        weighted_S2 = (S**2) * a_weights_linear[:, np.newaxis]
        db_a = 10 * np.log10(np.mean(weighted_S2) + 1e-9)
        
        # C. pYIN Pitch Tracking 
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=fmin, fmax=fmax, sr=sr,
            hop_length=hop_length,
            no_trough_prob=0.01, switch_prob=0.001
        )
        
        # Build pitch track arrays for visualisation
        times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop_length)
        
        # Nearest semitone in Hz for every frame (NaN where unvoiced)
        f0_display = f0.copy()
        semitone_hz = np.full_like(f0, np.nan)
        valid_mask = voiced_flag & (f0 > 0)
        f0_valid = f0[valid_mask]
        
        if len(f0_valid) == 0:
            # Failsafe: audio is entirely silent or unvoiced
            return {
                "metrics": [db_fs, db_a, np.nan, np.nan],
                "pitch_track": {"times": times, "f0": f0_display, "semitone_hz": semitone_hz}
            }
        
        # Compute nearest semitone for voiced frames
        midi_fractional = librosa.hz_to_midi(f0_valid)
        midi_target = np.round(midi_fractional)
        semitone_hz[valid_mask] = librosa.midi_to_hz(midi_target)
        
        # Set unvoiced frames to NaN for clean visualisation
        f0_display[~valid_mask] = np.nan
            
        # D. Deviations
        cents_dev = np.mean(np.abs((midi_fractional - midi_target) * 100))
        hz_target = librosa.midi_to_hz(midi_target)
        hz_dev = np.mean(np.abs(f0_valid - hz_target))
        
        return {
            "metrics": [db_fs, db_a, cents_dev, hz_dev],
            "pitch_track": {"times": times, "f0": f0_display, "semitone_hz": semitone_hz}
        }
    
    except Exception as e:
        st.error(f"⚠️ Failed to process audio file: {e}")
        return {"metrics": [None, None, None, None], "pitch_track": None}
        
    finally:
        if os.path.exists(a_path):
            os.remove(a_path)

# --- 4. Math Helper ---
def safe_subtract(a, b):
    """Returns a - b, or NaN if either value is missing."""
    if a is None or pd.isna(a) or b is None or pd.isna(b):
        return np.nan
    return a - b

# --- 5. Main Execution ---
if st.button("Generate Comparative Analysis", type="primary"):
    progress = st.progress(0, text="Starting analysis...")
    
    fmin = instrument_config[inst_type]["fmin"]
    fmax = instrument_config[inst_type]["fmax"]
    
    # Read file bytes upfront (with seek to handle Streamlit re-runs),
    # then pass bytes to the cached function
    def get_bytes(uploaded_file):
        if uploaded_file is None:
            return None
        uploaded_file.seek(0)
        return uploaded_file.getvalue()
    
    unplug_bytes = get_bytes(unplugged_file)
    plug_bytes = get_bytes(plugged_file)
    midi_bytes = get_bytes(midi_file)
    
    # Extract metrics with progress updates
    progress.progress(10, text="Analysing Unplugged recording...")
    unplug_result = extract_metrics(unplug_bytes, fmin, fmax)
    unplug_db_fs, unplug_db_a, unplug_cents, unplug_hz = unplug_result["metrics"]
    
    progress.progress(40, text="Analysing Plugged recording...")
    plug_result = extract_metrics(plug_bytes, fmin, fmax)
    plug_db_fs, plug_db_a, plug_cents, plug_hz = plug_result["metrics"]
    
    progress.progress(70, text="Analysing MIDI Baseline...")
    midi_result = extract_metrics(midi_bytes, fmin, fmax)
    midi_db_fs, midi_db_a, midi_cents, midi_hz = midi_result["metrics"]
    
    progress.progress(90, text="Building comparison table...")

    # --- 6. Constructing the Data Table ---
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
        "Absolute Mean Dev (Cents)": [
            unplug_cents, 
            plug_cents, 
            safe_subtract(plug_cents, unplug_cents)
        ],
        "Absolute Mean Dev (Hz)": [
            unplug_hz, 
            plug_hz, 
            safe_subtract(plug_hz, unplug_hz)
        ],
        "Relative Mean Dev (Cents)": [
            safe_subtract(unplug_cents, midi_cents), 
            safe_subtract(plug_cents, midi_cents), 
            safe_subtract(
                safe_subtract(plug_cents, midi_cents), 
                safe_subtract(unplug_cents, midi_cents)
            )
        ],
        "Relative Mean Dev (Hz)": [
            safe_subtract(unplug_hz, midi_hz), 
            safe_subtract(plug_hz, midi_hz), 
            safe_subtract(
                safe_subtract(plug_hz, midi_hz), 
                safe_subtract(unplug_hz, midi_hz)
            )
        ]
    }
    
    df = pd.DataFrame(data, index=["Unplugged Condition", "Plugged Condition", "Delta (Plugged - Unplugged)"])
    
    # Colour-code the delta row: green for negative (improvement), red for positive (degradation)
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
    
    # --- 7. Display Results ---
    st.subheader("Analysis Results")
    st.dataframe(styled_df, use_container_width=True)
    
    # --- 8. CSV Export ---
    csv = df.to_csv(index=True)
    st.download_button(
        "📥 Download CSV", 
        csv, 
        file_name=f"{participant_id}_comparative_analysis.csv",
        mime="text/csv"
    )
    
    # --- 9. Pitch Track Visualisations ---
    st.subheader("Pitch Track Visualisations")
    
    tracks = [
        ("Unplugged", unplug_result),
        ("Plugged", plug_result),
        ("MIDI Baseline", midi_result)
    ]
    
    for label, result in tracks:
        pt = result["pitch_track"]
        if pt is None:
            continue
        
        fig = go.Figure()
        
        # Nearest semitone (step-like reference)
        fig.add_trace(go.Scatter(
            x=pt["times"], y=pt["semitone_hz"],
            name="Nearest Semitone",
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
            title=f"{label} — Pitch Track vs Nearest Semitone",
            xaxis_title="Time (s)",
            yaxis_title="Frequency (Hz)",
            legend_title="Legend",
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)
