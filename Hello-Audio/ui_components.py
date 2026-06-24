import streamlit as st
import numpy as np
import pandas as pd
from itertools import zip_longest

def render_sidebar_parameters():
    """
    Renders the sidebar UI elements and returns the selected parameters.
    """
    st.sidebar.header("Legacy Pitch Analyser Parameters")

    instrument = st.sidebar.selectbox(
        "Select Instrument",
        ["Violin", "Viola", "Cello"],
        help="Sets the appropriate frequency detection range for the instrument."
    )

    switch_prob = st.sidebar.number_input(
        "Switch Probability (pYIN)", 
        min_value=0.001, 
        max_value=0.050, 
        value=0.005, 
        step=0.001,
        format="%.3f",
        help="Penalizes rapid toggling between voiced/unvoiced states. Lower values favor longer sustained notes. You can manually enter the value if needed."
    )

    rms_threshold = st.sidebar.number_input(
        "RMS Amplitude Threshold", 
        min_value=0.0, 
        max_value=1.0, 
        value=0.01, 
        step=0.005,
        help="Minimum RMS energy required for a frame to be considered active. Filters out background noise and quiet transients."
    )

    min_frames = st.sidebar.number_input(
        "Minimum Sustain Duration (frames)", 
        min_value=1, 
        max_value=100, 
        value=10,
        help="Minimum continuous frames a note must sustain to be included in the analysis. Discards short blips."
    )

    max_pitch_slope = st.sidebar.slider(
        "Maximum Pitch Slope", 
        min_value=0.05, 
        max_value=0.50, 
        value=0.10, 
        step=0.01,
        help="Maximum allowed frame-to-frame pitch change (semitones) to strictly isolate horizontal steady-state notes. Discards glissandos and slides."
    )
    
    return instrument, switch_prob, rms_threshold, min_frames, max_pitch_slope

def get_val(res_dict, key):
    """Helper to safely extract a value from the results dictionary."""
    return res_dict[key] if res_dict and key in res_dict else np.nan

def render_results_table(res_unp, res_plg, unp_ok, plg_ok):
    """
    Renders the Legacy Island Intonation Results table.
    """
    st.subheader("Legacy Island Intonation Results")
    st.write("These metrics are generated using the legacy pitch analyser, which uses the slope filter to strictly isolate steady state notes and compares them against the nearest semitone target.")
    
    mean_dev_unp = get_val(res_unp, 'mean_dev')
    mean_dev_plg = get_val(res_plg, 'mean_dev')
    mean_dev_hz_unp = get_val(res_unp, 'mean_dev_hz')
    mean_dev_hz_plg = get_val(res_plg, 'mean_dev_hz')
    mean_dbfs_unp = get_val(res_unp, 'mean_dbfs')
    mean_dbfs_plg = get_val(res_plg, 'mean_dbfs')
    mean_dba_unp = get_val(res_unp, 'mean_dba')
    mean_dba_plg = get_val(res_plg, 'mean_dba')
    
    note_count_unp = get_val(res_unp, 'note_count')
    note_count_plg = get_val(res_plg, 'note_count')

    # Calculate Delta if both exist, otherwise NaN
    delta_cents = mean_dev_unp - mean_dev_plg if unp_ok and plg_ok else np.nan
    delta_hz = mean_dev_hz_unp - mean_dev_hz_plg if unp_ok and plg_ok else np.nan
    delta_dbfs = mean_dbfs_unp - mean_dbfs_plg if unp_ok and plg_ok else np.nan
    delta_dba = mean_dba_unp - mean_dba_plg if unp_ok and plg_ok else np.nan
    delta_note_count = note_count_unp - note_count_plg if unp_ok and plg_ok else np.nan
    
    data = {
        "Condition": ["Unplugged", "Plugged", "Delta (Unplugged - Plugged)"],
        "Mean Deviation (Hz)": [mean_dev_hz_unp, mean_dev_hz_plg, delta_hz],
        "Mean Deviation (cents)": [mean_dev_unp, mean_dev_plg, delta_cents],
        "Mean RMS (dBFS)": [mean_dbfs_unp, mean_dbfs_plg, delta_dbfs],
        "Mean RMS (dBA)": [mean_dba_unp, mean_dba_plg, delta_dba],
        "Detected Pitches (count)": [note_count_unp, note_count_plg, delta_note_count]
    }
    df = pd.DataFrame(data)
    df.set_index("Condition", inplace=True)
    
    st.dataframe(df.style.format("{:.2f}", na_rep=""), width="stretch")

    csv = df.to_csv().encode('utf-8')
    st.download_button(
        label="Download Legacy Data as CSV",
        data=csv,
        file_name='intonation_comparison_legacy.csv',
        mime='text/csv',
    )
    
    msg = "Successfully analyzed"
    if unp_ok:
        msg += f" {res_unp['frame_count']} frames (Unplugged)"
    if unp_ok and plg_ok:
        msg += " and"
    if plg_ok:
        msg += f" {res_plg['frame_count']} frames (Plugged)"
    st.success(msg + ".")

def render_sequence_comparison(midi_seq, unp_seq, plg_seq):
    """
    Renders the Note Sequence Comparison table.
    """
    st.subheader("Note Sequence Comparison")
    
    seq_data = {}
    if midi_seq:
        seq_data["MIDI Reference Sequence"] = midi_seq
    if unp_seq:
        seq_data["Detected Sequence (Unplugged)"] = unp_seq
    if plg_seq:
        seq_data["Detected Sequence (Plugged)"] = plg_seq
        
    if seq_data:
        padded_rows = list(zip_longest(*seq_data.values(), fillvalue=""))
        padded_columns = {col: [row[i] for row in padded_rows] for i, col in enumerate(seq_data.keys())}
        
        df_seq = pd.DataFrame(padded_columns)
        df_seq.index = df_seq.index + 1
        df_seq.index.name = "Note Index"
        
        st.dataframe(df_seq, width="stretch")
        
        csv_seq = df_seq.to_csv().encode('utf-8')
        st.download_button(
            label="Download Sequence Data as CSV",
            data=csv_seq,
            file_name='note_sequence_comparison.csv',
            mime='text/csv',
        )
    else:
        st.info("Upload an audio file or MIDI reference to see the sequence comparison.")
