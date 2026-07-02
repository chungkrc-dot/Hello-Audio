"""
ui_components.py
----------------
Modular definitions for the Streamlit user interface.
This module extracts the complex UI rendering logic from the main application loop.
It handles sidebar parameter configurations (with scientific presets) and renders the 
interactive DataFrames for both DTW and Legacy metrics.
"""
import streamlit as st
import numpy as np
import pandas as pd
from itertools import zip_longest

def render_sidebar_parameters():
    """
    Renders the sidebar UI elements and returns the selected parameters.
    """
    st.sidebar.header("Pitch Analyser Parameters")
    
    preset = st.sidebar.selectbox(
        "Analysis Profile",
        ["Custom (Manual Tuning)", "Rapid / Virtuosic", "Slow / Legato"],
        help="Select a standardized preset to lock parameters across participants, ensuring experimental consistency."
    )
    
    if preset == "Rapid / Virtuosic":
        def_switch, def_rms, def_frames, def_slope = 0.005, 0.01, 1, 0.20
        disabled = True
    elif preset == "Slow / Legato":
        def_switch, def_rms, def_frames, def_slope = 0.005, 0.02, 10, 0.10
        disabled = True
    else:
        def_switch, def_rms, def_frames, def_slope = 0.005, 0.01, 10, 0.10
        disabled = False

    instrument = st.sidebar.selectbox(
        "Select Instrument",
        ["Violin", "Viola", "Cello"],
        help="Sets the appropriate frequency detection range for the instrument."
    )

    switch_prob = st.sidebar.number_input(
        "Switch Probability (pYIN)", 
        min_value=0.001, 
        max_value=0.050, 
        value=def_switch, 
        step=0.001,
        format="%.3f",
        disabled=disabled,
        help="Penalizes rapid toggling between voiced/unvoiced states. Lower values favor longer sustained notes. You can manually enter the value if needed."
    )

    rms_threshold = st.sidebar.number_input(
        "RMS Amplitude Threshold", 
        min_value=0.0, 
        max_value=1.0, 
        value=def_rms, 
        step=0.005,
        disabled=disabled,
        help="Minimum RMS energy required for a frame to be considered active. Filters out background noise and quiet transients."
    )

    min_frames = st.sidebar.number_input(
        "Minimum Sustain Duration (frames)", 
        min_value=1, 
        max_value=100, 
        value=def_frames,
        disabled=disabled,
        help="Minimum continuous frames a note must sustain to be included in the analysis. Discards short blips."
    )

    max_pitch_slope = st.sidebar.number_input(
        "Maximum Pitch Slope (semitones)", 
        min_value=0.01, 
        max_value=1.00, 
        value=def_slope, 
        step=0.01,
        disabled=disabled,
        help="Discards frames where the frame-to-frame pitch jump exceeds this limit. Filters out transients and glissandi."
    )

    # ==========================================
    # Logic Component Toggles (Demonstration Mode)
    # ==========================================
    st.sidebar.markdown("---")
    st.sidebar.subheader("Logic Component Toggles")
    st.sidebar.caption("Disable components to demonstrate failure modes for the technical manual.")
    
    enable_freq_limits = st.sidebar.checkbox("Enable Instrument Freq Limits", value=True, help="Limit pitch detection to range of instrument.")
    enable_slope_filter = st.sidebar.checkbox("Enable Pitch Slope Filter", value=True, help="Discard frames where pitch changes too rapidly.")
    enable_duration_filter = st.sidebar.checkbox("Enable Sustain Duration Filter", value=True, help="Discard pitch islands that are too short.")
    enable_locked_target = st.sidebar.checkbox("Enable Locked Target Rule", value=True, help="Lock legacy notes to their median semitone.")
    enable_octave_folding = st.sidebar.checkbox("Enable Octave Folding", value=True, help="Fold tracking errors to target octave in DTW.")
    
    toggles = {
        "freq_limits": enable_freq_limits,
        "slope_filter": enable_slope_filter,
        "duration_filter": enable_duration_filter,
        "locked_target": enable_locked_target,
        "octave_folding": enable_octave_folding
    }
    
    return instrument, switch_prob, rms_threshold, min_frames, max_pitch_slope, toggles

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

def render_dtw_results_table(dtw_metrics_unp, dtw_metrics_plg):
    """
    Renders the DTW Metric Table which explicitly maps detected audio notes to the MIDI score.
    """
    st.subheader("DTW Note-by-Note Intonation Metrics")
    st.caption("Use the checkboxes in the **Include** column to manually exclude corrupt notes (e.g. double-stops or tracking errors) from the Overall Summary calculation below. Unchecking a row will dynamically update the means.")
    st.write("This table extracts the exact median frequency and deviation from the DTW-warped timeline, strictly bound to the MIDI note expectations.")
    
    auto_exclude = st.checkbox(
        "Auto-exclude gross tracking errors (>1 semitone deviation)",
        value=True,
        help="Unchecks notes where deviation exceeds 100 cents. These are typically algorithmic tracking errors (e.g., tracking a sympathetic string resonance) rather than human intonation errors."
    )
    
    if not dtw_metrics_unp and not dtw_metrics_plg:
        st.info("No DTW metrics available to display.")
        return
        
    df_list = []
    include_list = []
    
    # Use the available array to dictate the structure since both depend entirely on the MIDI
    reference_metrics = dtw_metrics_unp if dtw_metrics_unp else dtw_metrics_plg
    
    for i, ref_note in enumerate(reference_metrics):
        row = {
            "Note Index": ref_note["Note_Index"],
            "Expected Note": ref_note["Expected_Note"],
            "Target Freq (Hz)": ref_note["Expected_Target_Pitch_Hz"],
        }
        
        dev_hz_unp = np.nan
        dev_hz_plg = np.nan
        include_val = True
        
        if dtw_metrics_unp and i < len(dtw_metrics_unp):
            unp_note = dtw_metrics_unp[i]
            row["Unplugged Dev (Hz)"] = unp_note["Deviation_Hz"]
            row["Unplugged RMS (dBFS)"] = unp_note["Median_RMS_dBFS"]
            dev_hz_unp = unp_note["Deviation_Hz"]
            
            if auto_exclude and abs(unp_note["Deviation_Cents"]) > 100:
                include_val = False
            
        if dtw_metrics_plg and i < len(dtw_metrics_plg):
            plg_note = dtw_metrics_plg[i]
            row["Plugged Dev (Hz)"] = plg_note["Deviation_Hz"]
            row["Plugged RMS (dBFS)"] = plg_note["Median_RMS_dBFS"]
            dev_hz_plg = plg_note["Deviation_Hz"]
            
            if auto_exclude and abs(plg_note["Deviation_Cents"]) > 100:
                include_val = False
            
        if dtw_metrics_unp and dtw_metrics_plg:
            row["Delta Dev (Unplugged - Plugged)"] = dev_hz_unp - dev_hz_plg
            
        df_list.append(row)
        include_list.append(include_val)
        
    df = pd.DataFrame(df_list)
    df.set_index("Note Index", inplace=True)
    
    df.insert(0, "Include", include_list)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    disabled_cols = df.columns.drop("Include").tolist()
    
    styled_df = df.style.format("{:.2f}", subset=numeric_cols, na_rep="Missed")\
                        .highlight_null(color='rgba(255, 75, 75, 0.3)')
    
    edited_df = st.data_editor(
        styled_df,
        column_config={
            "Include": st.column_config.CheckboxColumn(
                "Include",
                help="Select which notes to include in the overall summary means",
                default=True,
            )
        },
        disabled=disabled_cols,
        width="stretch",
        use_container_width=True
    )
    
    excluded_indices = edited_df[~edited_df["Include"]].index.tolist()
    
    csv = edited_df.drop(columns=["Include"]).to_csv().encode('utf-8')
    st.download_button(
        label="Download DTW Metrics as CSV",
        data=csv,
        file_name='dtw_metrics_comparison.csv',
        mime='text/csv',
    )
    
    return excluded_indices

def render_dtw_summary_table(dtw_metrics_unp, dtw_metrics_plg, excluded_indices=None):
    """
    Renders an overall performance summary table aggregating the note-by-note DTW metrics.
    Includes Delta calculation between Unplugged and Plugged conditions.
    """
    if not dtw_metrics_unp and not dtw_metrics_plg:
        return
        
    if excluded_indices is None:
        excluded_indices = []
        
    st.write("**Overall DTW Performance Summary**")
    
    summary_data = []
    
    def calculate_means(metrics):
        if not metrics:
            return {
                "Notes Detected (%)": np.nan,
                "Notes Included (%)": np.nan,
                "mean RMS amplitude (dB FS)": np.nan, 
                "mean RMS amplitude (dB A)": np.nan, 
                "mean intonation deviation (Hz)": np.nan, 
                "mean intonation deviation (cents)": np.nan
            }
            
        total_expected = len(metrics)
        detected_count = sum(1 for m in metrics if not pd.isna(m["Deviation_Cents"]))
        
        filtered_metrics = [m for m in metrics if m["Note_Index"] not in excluded_indices]
        
        included_count = sum(1 for m in filtered_metrics if not pd.isna(m["Deviation_Cents"]))
        
        pct_detected = (detected_count / total_expected * 100) if total_expected > 0 else np.nan
        pct_included = (included_count / detected_count * 100) if detected_count > 0 else np.nan
        
        if not filtered_metrics:
            return {
                "Notes Detected (%)": pct_detected,
                "Notes Included (%)": pct_included,
                "mean RMS amplitude (dB FS)": np.nan, 
                "mean RMS amplitude (dB A)": np.nan, 
                "mean intonation deviation (Hz)": np.nan, 
                "mean intonation deviation (cents)": np.nan
            }
            
        df = pd.DataFrame(filtered_metrics)
        return {
            "Notes Detected (%)": pct_detected,
            "Notes Included (%)": pct_included,
            "mean RMS amplitude (dB FS)": df["Median_RMS_dBFS"].mean(),
            "mean RMS amplitude (dB A)": df["Median_RMS_dBA"].mean(),
            "mean intonation deviation (Hz)": df["Deviation_Hz"].mean(),
            "mean intonation deviation (cents)": df["Deviation_Cents"].mean(),
        }
        
    unp_means = calculate_means(dtw_metrics_unp)
    plg_means = calculate_means(dtw_metrics_plg)
    
    unp_means["Condition"] = "Unplugged"
    plg_means["Condition"] = "Plugged"
    
    summary_data.append(unp_means)
    summary_data.append(plg_means)
    
    delta = {
        "Condition": "Delta (Unplugged - Plugged)",
        "Notes Detected (%)": unp_means["Notes Detected (%)"] - plg_means["Notes Detected (%)"],
        "Notes Included (%)": unp_means["Notes Included (%)"] - plg_means["Notes Included (%)"],
        "mean RMS amplitude (dB FS)": unp_means["mean RMS amplitude (dB FS)"] - plg_means["mean RMS amplitude (dB FS)"],
        "mean RMS amplitude (dB A)": unp_means["mean RMS amplitude (dB A)"] - plg_means["mean RMS amplitude (dB A)"],
        "mean intonation deviation (Hz)": unp_means["mean intonation deviation (Hz)"] - plg_means["mean intonation deviation (Hz)"],
        "mean intonation deviation (cents)": unp_means["mean intonation deviation (cents)"] - plg_means["mean intonation deviation (cents)"]
    }
    summary_data.append(delta)
    
    df_summary = pd.DataFrame(summary_data)
    df_summary.set_index("Condition", inplace=True)
    
    numeric_cols = df_summary.select_dtypes(include=[np.number]).columns
    st.dataframe(df_summary.style.format("{:.2f}", subset=numeric_cols, na_rep="N/A"), width="stretch")
    
    csv = df_summary.to_csv().encode('utf-8')
    st.download_button(
        label="Download DTW Summary as CSV",
        data=csv,
        file_name='dtw_summary.csv',
        mime='text/csv',
    )
    
    st.caption("**Notes Detected (%)**: The percentage of expected MIDI notes that were successfully extracted by the pitch tracking algorithm.\n\n"
               "**Notes Included (%)**: The percentage of *detected notes* that successfully passed all algorithmic tracking filters (and manual exclusions) to contribute to the mean deviation calculations above.")


