import streamlit as st
import librosa
import numpy as np
import pandas as pd
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

# --- 3. Processing Logic ---
def extract_metrics(uploaded_file, fmin, fmax):
    """Processes audio and returns [db_fs, db_a, cents_dev, hz_dev]. Returns Nones if empty."""
    if uploaded_file is None:
        return [None, None, None, None]
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as ta:
        ta.write(uploaded_file.read())
        a_path = ta.name
        
    try:
        y, sr = librosa.load(a_path, sr=22050)
        
        # A. Amplitude Metrics
        rms_raw = np.sqrt(np.mean(y**2))
        db_fs = 20 * np.log10(rms_raw + 1e-9)
        
        S = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sr)
        a_weights = librosa.A_weighting(freqs)
        weighted_power = np.mean(S**2, axis=1) * librosa.db_to_power(a_weights)
        db_a = 10 * np.log10(np.sum(weighted_power) + 1e-9)
        
        # B. pYIN Pitch Tracking 
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=fmin, fmax=fmax, sr=sr,
            no_trough_prob=0.01, switch_prob=0.001
        )
        
        valid_mask = voiced_flag & (f0 > 0)
        f0_valid = f0[valid_mask]
        
        if len(f0_valid) == 0: # Failsafe if audio is silent
            return [db_fs, db_a, np.nan, np.nan]
            
        # C. Absolute Pitch Quantization
        midi_fractional = librosa.hz_to_midi(f0_valid)
        midi_target = np.round(midi_fractional)
        
        # D. Deviations
        cents_dev = np.mean(np.abs((midi_fractional - midi_target) * 100))
        hz_target = librosa.midi_to_hz(midi_target)
        hz_dev = np.mean(np.abs(f0_valid - hz_target))
        
        return [db_fs, db_a, cents_dev, hz_dev]
        
    finally:
        os.remove(a_path)

# --- 4. Main Execution ---
if st.button("Generate Comparative Analysis", type="primary"):
    with st.spinner("Analyzing and aligning available datasets..."):
        fmin = instrument_config[inst_type]["fmin"]
        fmax = instrument_config[inst_type]["fmax"]
        
        # Extract base metrics (Unpacks the lists into 4 scalar variables each)
        unplug_db_fs, unplug_db_a, unplug_cents, unplug_hz = extract_metrics(unplugged_file, fmin, fmax)
        plug_db_fs, plug_db_a, plug_cents, plug_hz = extract_metrics(plugged_file, fmin, fmax)
        midi_db_fs, midi_db_a, midi_cents, midi_hz = extract_metrics(midi_file, fmin, fmax)
        
        # Math Helpers for dealing with missing variables
        def get_rel(val, baseline):
            if val is None or pd.isna(val) or baseline is None or pd.isna(baseline): 
                return np.nan
            return val - baseline
            
        def get_delta(val_plug, val_unplug):
            if val_plug is None or pd.isna(val_plug) or val_unplug is None or pd.isna(val_unplug):
                return np.nan
            return val_plug - val_unplug

        # --- 5. Constructing the Data Table ---
        # Data is organized by column using the unpacked scalar variables
        data = {
            "Mean RMS Amplitude (dB FS)": [
                unplug_db_fs, 
                plug_db_fs, 
                get_delta(plug_db_fs, unplug_db_fs)
            ],
            "Mean RMS Amplitude (dB A)": [
                unplug_db_a, 
                plug_db_a, 
                get_delta(plug_db_a, unplug_db_a)
            ],
            "Absolute Mean Dev (Cents)": [
                unplug_cents, 
                plug_cents, 
                get_delta(plug_cents, unplug_cents)
            ],
            "Absolute Mean Dev (Hz)": [
                unplug_hz, 
                plug_hz, 
                get_delta(plug_hz, unplug_hz)
            ],
            "Relative Mean Dev (Cents)": [
                get_rel(unplug_cents, midi_cents), 
                get_rel(plug_cents, midi_cents), 
                get_delta(get_rel(plug_cents, midi_cents), get_rel(unplug_cents, midi_cents))
            ],
            "Relative Mean Dev (Hz)": [
                get_rel(unplug_hz, midi_hz), 
                get_rel(plug_hz, midi_hz), 
                get_delta(get_rel(plug_hz, midi_hz), get_rel(unplug_hz, midi_hz))
            ]
        }
        
        df = pd.DataFrame(data, index=["Unplugged Condition", "Plugged Condition", "Delta (Plugged - Unplugged)"])
        
        # Style the DataFrame to format NaNs as empty strings and round valid numbers to 2 decimal places
        styled_df = df.style.format(lambda x: f"{x:.2f}" if pd.notna(x) else "")
        
        st.subheader("Analysis Results")
        st.dataframe(styled_df, use_container_width=True)