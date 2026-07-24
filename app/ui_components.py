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
from src.midi_alignment import (
    is_note_excluded, summarize_dtw_metrics, low_detection_yield_warning,
    paired_delta_summary, paired_coverage_advisory,
)
from src.stats_summary import PYIN_RESOLUTION_CENTS, TRIM_PROPORTION

# Rows of the distributional summary tables, in reporting order.
# (stat key, display label, format string)
DEVIATION_STAT_ROWS = [
    ("n",        "Sample size (n)",             "{:.0f}"),
    ("mean",     "Mean",                        "{:.2f}"),
    ("std",      "Standard deviation",          "{:.2f}"),
    ("sem",      "Standard error of the mean",  "{:.2f}"),
    ("median",   "Median",                      "{:.2f}"),
    ("q1",       "1st quartile (Q1)",           "{:.2f}"),
    ("q3",       "3rd quartile (Q3)",           "{:.2f}"),
    ("iqr",      "Interquartile range (IQR)",   "{:.2f}"),
    ("mad",      "Median absolute deviation",   "{:.2f}"),
    ("trimmed_mean", f"{TRIM_PROPORTION:.0%}-trimmed mean", "{:.2f}"),
    ("skewness", "Skewness (G1)",               "{:.3f}"),
    ("kurtosis", "Excess kurtosis (G2)",        "{:.3f}"),
    ("min",      "Minimum",                     "{:.2f}"),
    ("max",      "Maximum",                     "{:.2f}"),
]

DISTRIBUTION_CAPTION = (
    "**Skewness (G1)** is 0 for a symmetric distribution; positive values mean the sharp "
    "(above-target) tail is the longer one. **Excess kurtosis (G2)** is 0 for a Gaussian; "
    "positive values mean heavier tails than normal, so the mean and standard deviation "
    "understate how often large errors occur and the median/IQR pair is the more honest "
    "summary. Both are bias-corrected sample estimators."
)


def render_deviation_statistics_table(stats_by_condition, unit_label, caption_key,
                                      note_resolution=False):
    """
    Renders a statistic-per-row table comparing the full deviation distribution
    across conditions. `stats_by_condition` maps a condition name to a dict of
    the un-prefixed statistic keys produced by src.stats_summary.descriptive_stats.
    """
    if not stats_by_condition:
        return

    table = {}
    for condition, stats in stats_by_condition.items():
        column = []
        for key, _label, fmt in DEVIATION_STAT_ROWS:
            value = stats.get(key, np.nan)
            column.append("N/A" if value is None or pd.isna(value) else fmt.format(value))
        table[condition] = column

    df = pd.DataFrame(table, index=[label for _k, label, _f in DEVIATION_STAT_ROWS])
    df.index.name = f"Statistic ({unit_label})"

    st.dataframe(df, width="stretch")

    csv = df.to_csv().encode('utf-8')
    st.download_button(
        label=f"Download Distribution Statistics ({unit_label}) as CSV",
        data=csv,
        file_name=f'deviation_distribution_stats_{caption_key}.csv',
        mime='text/csv',
        key=f'dl_dist_{caption_key}'
    )

    if note_resolution:
        st.caption(
            f"**Resolution floor:** pYIN decodes pitch on a fixed grid of "
            f"{PYIN_RESOLUTION_CENTS:.0f} cents, so frame deviations are exact multiples of "
            f"{PYIN_RESOLUTION_CENTS:.0f} cents and per-note medians land on a 5-cent lattice. "
            "The median, quartiles and IQR are order statistics: they can only ever return a "
            "lattice value, and on large note populations they stop moving altogether. Treat "
            "them as naming a grid cell, not as measurements to two decimal places. The mean "
            f"and the {TRIM_PROPORTION:.0%}-trimmed mean are averages of many lattice values, "
            "so they dither off the grid and keep full resolution — the trimmed mean is the "
            "one to quote when the distribution is heavy-tailed. REAPER returns continuous f0 "
            "and has no such floor."
        )

def render_sidebar_parameters(is_midi_uploaded=False):
    """
    Renders the sidebar UI elements and returns the selected parameters.
    """
    st.sidebar.header("Pitch Analyser Parameters")
    
    # Engine selection. pYIN is the validated default for all standard analysis;
    # REAPER is a specialised secondary engine kept only for its one measured
    # advantage — continuous (non-quantised) pitch for sub-10-cent microtonal work
    # (Appendix B). It is placed behind an "Advanced" reveal so the common case
    # needs no decision, rather than presented as an equal coin-flip.
    st.sidebar.markdown("**Pitch Tracker Engine:** pYIN _(recommended)_")
    st.sidebar.caption(
        "pYIN (probabilistic YIN) is the validated default and leads note-detection "
        "yield across violin, viola and cello. Use it for all standard intonation analysis."
    )

    with st.sidebar.expander("Advanced: alternative engine"):
        use_reaper = st.checkbox(
            "Use REAPER instead of pYIN",
            value=False,
            help="REAPER (Robust Epoch And Pitch EstimatoR) tracks pitch in the continuous "
                 "time domain, so it resolves intonation finer than pYIN's 10-cent output grid."
        )
        st.caption(
            "Switch to REAPER **only** when you need sub-10-cent microtonal precision on "
            "deliberately detuned material — it is the more accurate engine for off-grid "
            "shifts (Appendix B). For normal performance analysis pYIN is preferred: it "
            "detects more notes and is far less prone to octave-tracking errors."
        )

    pitch_engine = "REAPER" if use_reaper else "pYIN"

    if pitch_engine == "REAPER":
        st.sidebar.info("⚙️ REAPER engine active — microtonal precision mode. "
                        "Switch-probability and voicing-confidence controls are inactive.")

    preset = st.sidebar.selectbox(
        "Analysis Profile (Legacy Mode)",
        ["Engine Optimal Default", "Rapid / Virtuosic", "Medium / Andante", "Slow / Legato"],
        help="Select a standardized preset. Note: These presets primarily govern the Legacy Island Intonation logic. The DTW engine is robust enough to ignore tempo.",
        disabled=is_midi_uploaded
    )
    
    if preset == "Rapid / Virtuosic":
        def_switch, def_rms, def_frames, def_slope = 0.005, 0.01, 1, 0.20
        disabled = True
    elif preset == "Medium / Andante":
        def_switch, def_rms, def_frames, def_slope = 0.005, 0.01, 3, 0.20
        disabled = True
    elif preset == "Slow / Legato":
        def_switch, def_rms, def_frames, def_slope = 0.005, 0.01, 5, 0.20
        disabled = True
    else:
        if pitch_engine == "REAPER":
            def_switch, def_rms, def_frames, def_slope = 0.005, 0.005, 4, 0.50
        else:
            def_switch, def_rms, def_frames, def_slope = 0.005, 0.005, 2, 0.50
        disabled = False

    disabled = False

    instrument = st.sidebar.selectbox(
        "Select Instrument",
        ["Violin", "Viola", "Cello"],
        key="selected_instrument",
        help="Sets the appropriate frequency detection range for the instrument."
    )

    reference_pitch_hz = st.sidebar.number_input(
        "Reference Pitch (Hz)",
        min_value=430.0,
        max_value=450.0,
        value=440.0,
        step=0.5,
        format="%.1f",
        help="Concert A reference frequency. Standard orchestral tuning is A=440 Hz. Many European ensembles tune to A=441–443 Hz."
    )

    switch_prob = st.sidebar.number_input(
        "Switch Probability (pYIN)", 
        min_value=0.001, 
        max_value=0.050, 
        value=def_switch, 
        step=0.001,
        format="%.3f",
        disabled=disabled or (pitch_engine == "REAPER"),
        help="Penalizes rapid toggling between voiced/unvoiced states. Lower values favor longer sustained notes. (Disabled when using REAPER)"
    )

    rms_threshold = st.sidebar.number_input(
        "RMS Amplitude Threshold", 
        min_value=0.0, 
        max_value=1.0, 
        value=def_rms, 
        step=0.001,
        format="%.3f",
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

    confidence_threshold = st.sidebar.number_input(
        "Voicing Confidence Threshold",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.05,
        format="%.2f",
        disabled=(pitch_engine == "REAPER"),
        help="Minimum pYIN voicing probability for a frame to be included. 0.0 preserves default behavior (no filtering). "
             "Higher values discard uncertain frames. Has no effect with REAPER (binary voicing only)."
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
    enable_harmonic_folding = st.sidebar.checkbox("Enable Harmonic Folding", value=True, help="Fold harmonic (e.g., octaves, perfect 5ths) tracking errors to target note in DTW.")
    enable_force_global = st.sidebar.checkbox("Force Global DTW Alignment", value=True, help="Forces a strict 1:1 global DTW alignment, preventing path degeneracy on fast repetitive full performances.")
    enable_adaptive_rms = st.sidebar.checkbox("Enable Adaptive RMS Threshold", value=True, help="Dynamically adjust the RMS threshold based on the recording's 10th percentile noise floor.")
    
    toggles = {
        "freq_limits": enable_freq_limits,
        "slope_filter": enable_slope_filter,
        "duration_filter": enable_duration_filter,
        "locked_target": enable_locked_target,
        "harmonic_folding": enable_harmonic_folding,
        "force_global": enable_force_global,
        "adaptive_rms": enable_adaptive_rms
    }
    
    return pitch_engine, instrument, reference_pitch_hz, switch_prob, rms_threshold, min_frames, max_pitch_slope, confidence_threshold, toggles

def get_val(res_dict, key):
    """Helper to safely extract a value from the results dictionary."""
    return res_dict[key] if res_dict and key in res_dict else np.nan

def _unprefix(res_dict, prefix):
    """
    Recovers a plain statistics dict from the flattened, prefixed keys stored in a
    results dict (e.g. 'dev_cents_median' -> 'median').
    """
    if not res_dict:
        return {}
    head = f"{prefix}_"
    return {k[len(head):]: v for k, v in res_dict.items() if k.startswith(head)}

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

    # --- Distributional summary ---
    # The table above reports means only. Frame-level cent deviations are strongly
    # non-normal (vibrato produces broad shoulders, residual tracking errors produce
    # heavy tails), so the robust and shape statistics are reported separately.
    st.write("**Deviation Distribution Statistics (Legacy)**")

    cents_stats = {}
    hz_stats = {}
    if unp_ok:
        cents_stats["Unplugged"] = _unprefix(res_unp, 'dev_cents')
        hz_stats["Unplugged"] = _unprefix(res_unp, 'dev_hz')
    if plg_ok:
        cents_stats["Plugged"] = _unprefix(res_plg, 'dev_cents')
        hz_stats["Plugged"] = _unprefix(res_plg, 'dev_hz')

    tab_cents, tab_hz = st.tabs(["Cents", "Hertz"])
    with tab_cents:
        render_deviation_statistics_table(cents_stats, "cents", "legacy_cents",
                                          note_resolution=True)
    with tab_hz:
        render_deviation_statistics_table(hz_stats, "Hz", "legacy_hz")

    st.caption(DISTRIBUTION_CAPTION)

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
    st.write(
        "This table extracts the exact median frequency and deviation from the DTW-warped timeline, "
        "strictly bound to the MIDI note expectations. Each row is one MIDI note; the **Detected (Hz)**, "
        "**Dev (Hz)**, and **RMS (dBFS)** columns report the tracked pitch, its signed deviation from the "
        "expected target, and the note's loudness for each condition."
    )
    st.write(
        "The **Harmonic Fold** column reports any harmonic correction the pitch tracker applied "
        "before scoring the note — an *Octave* (±12 semitones), *Perfect 5th* (3rd/6th-harmonic "
        "confusion), or *Major 3rd* (5th-harmonic confusion) fold made when detection locked onto a "
        "harmonic instead of the fundamental. **A blank cell is the normal case:** it means the "
        "fundamental was tracked cleanly and no fold was needed."
    )
    
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
        
        # Determine if we should auto-exclude based on deviation
        dev_cents_unp = dtw_metrics_unp[i]["Deviation_Cents"] if dtw_metrics_unp and i < len(dtw_metrics_unp) else np.nan
        dev_cents_plg = dtw_metrics_plg[i]["Deviation_Cents"] if dtw_metrics_plg and i < len(dtw_metrics_plg) else np.nan
        
        # Determine if correction was applied
        corr_unp = dtw_metrics_unp[i].get("Correction_Applied", False) if dtw_metrics_unp and i < len(dtw_metrics_unp) else False
        corr_plg = dtw_metrics_plg[i].get("Correction_Applied", False) if dtw_metrics_plg and i < len(dtw_metrics_plg) else False
        
        corr_type_unp = dtw_metrics_unp[i].get("Correction_Type", "None") if dtw_metrics_unp and i < len(dtw_metrics_unp) else "None"
        corr_type_plg = dtw_metrics_plg[i].get("Correction_Type", "None") if dtw_metrics_plg and i < len(dtw_metrics_plg) else "None"
        
        if auto_exclude:
            unp_excl = is_note_excluded(dtw_metrics_unp[i]) if dtw_metrics_unp and i < len(dtw_metrics_unp) else False
            plg_excl = is_note_excluded(dtw_metrics_plg[i]) if dtw_metrics_plg and i < len(dtw_metrics_plg) else False
            if unp_excl or plg_excl:
                include_val = False
        
        if dtw_metrics_unp and i < len(dtw_metrics_unp):
            unp_note = dtw_metrics_unp[i]
            row["Unplugged Detected (Hz)"] = unp_note["Median_Detected_Pitch_Hz"]
            row["Unplugged Dev (Hz)"] = unp_note["Deviation_Hz"]
            row["Unplugged RMS (dBFS)"] = unp_note["Median_RMS_dBFS"]
            row["Unplugged Harmonic Fold"] = corr_type_unp if corr_unp else ""
            dev_hz_unp = unp_note["Deviation_Hz"]
            
        if dtw_metrics_plg and i < len(dtw_metrics_plg):
            plg_note = dtw_metrics_plg[i]
            row["Plugged Detected (Hz)"] = plg_note["Median_Detected_Pitch_Hz"]
            row["Plugged Dev (Hz)"] = plg_note["Deviation_Hz"]
            row["Plugged RMS (dBFS)"] = plg_note["Median_RMS_dBFS"]
            row["Plugged Harmonic Fold"] = corr_type_plg if corr_plg else ""
            dev_hz_plg = plg_note["Deviation_Hz"]
            
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
            ),
            "Unplugged Harmonic Fold": st.column_config.TextColumn(
                "Unplugged Harmonic Fold",
                help="Harmonic correction applied before scoring (Octave / Perfect 5th / Major 3rd). "
                     "Blank = fundamental tracked cleanly, no fold needed.",
            ),
            "Plugged Harmonic Fold": st.column_config.TextColumn(
                "Plugged Harmonic Fold",
                help="Harmonic correction applied before scoring (Octave / Perfect 5th / Major 3rd). "
                     "Blank = fundamental tracked cleanly, no fold needed.",
            ),
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

def render_dtw_summary_table(dtw_metrics_unp, dtw_metrics_plg, excluded_indices=None,
                             pitch_engine=None):
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

    # Aggregation lives in src/midi_alignment.summarize_dtw_metrics() so the UI,
    # the headless CLI and the validation scripts all report the same numbers.
    unp_summary = summarize_dtw_metrics(dtw_metrics_unp, excluded_indices)
    plg_summary = summarize_dtw_metrics(dtw_metrics_plg, excluded_indices)

    def as_row(summary):
        return {
            "Notes Detected (%)": summary["pct_detected"],
            "Notes Included (%)": summary["pct_included"],
            "mean RMS amplitude (dB FS)": summary["mean_rms_dbfs"],
            "mean RMS amplitude (dB A)": summary["mean_rms_dba"],
            "mean intonation deviation (Hz)": summary["dev_hz_mean"],
            "mean intonation deviation (cents)": summary["dev_cents_mean"],
            "median intonation deviation (cents)": summary["dev_cents_median"],
            "IQR of deviation (cents)": summary["dev_cents_iqr"],
        }

    unp_means = as_row(unp_summary)
    plg_means = as_row(plg_summary)

    unp_means["Condition"] = "Unplugged"
    plg_means["Condition"] = "Plugged"

    summary_data.append(unp_means)
    summary_data.append(plg_means)

    # Two deltas, and the order is deliberate. The PAIRED delta compares the two
    # conditions note-for-note over the notes both detected, so the difference is
    # the condition effect rather than a byproduct of which notes each side caught
    # — it is the figure to report. The INDEPENDENT-MEANS delta subtracts each
    # condition's own mean over its own note set; it is kept for transparency and
    # to expose drift (the two agree only when the takes detect the same notes).
    have_both = bool(dtw_metrics_unp) and bool(dtw_metrics_plg)
    pd_summary = paired_delta_summary(dtw_metrics_unp, dtw_metrics_plg, excluded_indices) if have_both else None

    if have_both:
        paired_row = {"Condition": "Delta (paired, drift-free)"}
        for key in unp_means:
            if key == "Condition":
                continue
            paired_row[key] = pd_summary["deltas"].get(key, np.nan)  # N/A for non-mean columns
        summary_data.append(paired_row)

    delta = {"Condition": "Delta (independent means)"}
    for key in unp_means:
        if key == "Condition":
            continue
        delta[key] = unp_means[key] - plg_means[key]
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
               "**Notes Included (%)**: The percentage of *detected notes* that successfully passed all algorithmic tracking filters (and manual exclusions) to contribute to the mean deviation calculations above.\n\n"
               "**Delta (paired, drift-free)**: the condition effect measured note-for-note over the notes *both* takes detected — the figure to report. **Delta (independent means)**: each condition's own mean subtracted; shown for transparency, it matches the paired figure only when the two takes detect the same notes.")

    # Pairing-coverage line: how much of the score the paired Delta rests on.
    if pd_summary is not None:
        st.caption(
            f"Paired Delta computed over **{pd_summary['n_paired']} notes** both takes "
            f"detected (Unplugged detected {unp_summary['pct_detected']:.0f}%, "
            f"Plugged {plg_summary['pct_detected']:.0f}%)."
        )

    # Advisory: a very low detection yield is the only signal that catches a
    # same-instrument part swap, which the tessitura check cannot see.
    for label, summary in (("Unplugged", unp_summary), ("Plugged", plg_summary)):
        msg = low_detection_yield_warning(summary["pct_detected"], pitch_engine)
        if msg:
            st.warning(f"**{label}:** {msg}")

    # Advisory: when the two takes' yields diverge, the independent-means delta
    # drifts and the paired delta should be trusted instead.
    if pd_summary is not None:
        adv = paired_coverage_advisory(
            unp_summary["pct_detected"], plg_summary["pct_detected"],
            pd_summary["n_paired"], pd_summary["n_detected_a"], pd_summary["n_detected_b"],
        )
        if adv:
            st.warning(adv)

    # --- Distributional summary ---
    st.write("**Deviation Distribution Statistics (DTW)**")

    cents_stats = {}
    hz_stats = {}
    if dtw_metrics_unp:
        cents_stats["Unplugged"] = _unprefix(unp_summary, 'dev_cents')
        hz_stats["Unplugged"] = _unprefix(unp_summary, 'dev_hz')
    if dtw_metrics_plg:
        cents_stats["Plugged"] = _unprefix(plg_summary, 'dev_cents')
        hz_stats["Plugged"] = _unprefix(plg_summary, 'dev_hz')

    tab_cents, tab_hz = st.tabs(["Cents", "Hertz"])
    with tab_cents:
        render_deviation_statistics_table(cents_stats, "cents", "dtw_cents",
                                          note_resolution=True)
    with tab_hz:
        render_deviation_statistics_table(hz_stats, "Hz", "dtw_hz")

    st.caption(DISTRIBUTION_CAPTION)

    return unp_summary, plg_summary


