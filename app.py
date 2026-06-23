# --- Imports ---
import streamlit as st
import librosa
import numpy as np
import plotly.graph_objects as go
from pitch_engine import analyze_intonation
from amplitude_analysis import analyze_amplitude

# Configure the Streamlit page layout to be wide for better graph visibility
st.set_page_config(page_title="Intonation Tracker", layout="wide")

# --- App Header ---
st.title("Pitch & Intonation Tracker")
st.write("""
This app analyzes musician intonation deviation by isolating steady-state notes. 
It uses pYIN for pitch extraction, applies RMS amplitude thresholding, and filters out short transients and glissandos to focus strictly on sustained, stable notes.
""")

# --- Sidebar UI Parameters ---
st.sidebar.header("Parameters")

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

# --- File Upload & State Management ---
from midi_parser import parse_midi, parse_midi_with_timing

col_u1, col_u2, col_u3 = st.columns(3)
with col_u1:
    file_unplugged = st.file_uploader("Upload 'Unplugged' Audio (without earplugs)", type=["wav", "mp3"])
with col_u2:
    file_plugged = st.file_uploader("Upload 'Plugged' Audio (with earplugs)", type=["wav", "mp3"])
with col_u3:
    file_midi = st.file_uploader("Upload MIDI Reference (Optional)", type=["mid", "midi"])

if 'file_unplugged_name' not in st.session_state:
    st.session_state['file_unplugged_name'] = ""
if 'file_plugged_name' not in st.session_state:
    st.session_state['file_plugged_name'] = ""
if 'file_midi_name' not in st.session_state:
    st.session_state['file_midi_name'] = ""
if 'analyze_clicked' not in st.session_state:
    st.session_state['analyze_clicked'] = False

# Reset state if either file changes
if file_unplugged is not None and file_unplugged.name != st.session_state['file_unplugged_name']:
    st.session_state['analyze_clicked'] = False
    st.session_state['file_unplugged_name'] = file_unplugged.name
    if 'analysis_results_unplugged' in st.session_state:
        del st.session_state['analysis_results_unplugged']

if file_plugged is not None and file_plugged.name != st.session_state['file_plugged_name']:
    st.session_state['analyze_clicked'] = False
    st.session_state['file_plugged_name'] = file_plugged.name
    if 'analysis_results_plugged' in st.session_state:
        del st.session_state['analysis_results_plugged']

if file_midi is not None and file_midi.name != st.session_state['file_midi_name']:
    st.session_state['analyze_clicked'] = False
    st.session_state['file_midi_name'] = file_midi.name
    if 'analysis_results_midi' in st.session_state:
        del st.session_state['analysis_results_midi']

# --- Step 1: Audio Processing Execution ---
if st.button("Start Analysis", type="primary"):
    if file_unplugged is None and file_plugged is None:
        st.error("Please upload at least one audio file to run the analysis.")
    else:
        st.session_state['analyze_clicked'] = True
        
        st.info("Loading and processing audio... This might take a moment depending on the file lengths.")
        
        # --- Pre-compute MIDI Reference ---
        midi_notes_timing = None
        if file_midi is not None:
            with st.spinner("Parsing MIDI Reference Sequence..."):
                midi_sequence = parse_midi(file_midi)
                st.session_state['analysis_results_midi'] = midi_sequence
                midi_notes_timing = parse_midi_with_timing(file_midi)
                st.session_state['analysis_results_midi_timing'] = midi_notes_timing
        
        if file_unplugged is not None:
            with st.spinner("Analyzing 'Unplugged' Intonation & Amplitude..."):
                res_unplugged = analyze_intonation(
                    audio_file=file_unplugged,
                    instrument=instrument,
                    switch_prob=switch_prob,
                    rms_threshold=rms_threshold,
                    min_frames=min_frames,
                    max_pitch_slope=max_pitch_slope
                )
                amp_unplugged = analyze_amplitude(file_unplugged)
                res_unplugged.update(amp_unplugged)
                st.session_state['analysis_results_unplugged'] = res_unplugged

        if file_plugged is not None:
            with st.spinner("Analyzing 'Plugged' Intonation & Amplitude..."):
                res_plugged = analyze_intonation(
                    audio_file=file_plugged,
                    instrument=instrument,
                    switch_prob=switch_prob,
                    rms_threshold=rms_threshold,
                    min_frames=min_frames,
                    max_pitch_slope=max_pitch_slope
                )
                amp_plugged = analyze_amplitude(file_plugged)
                res_plugged.update(amp_plugged)
                st.session_state['analysis_results_plugged'] = res_plugged
            
# --- Step 2: Global Aggregation & UI Display ---
if st.session_state['analyze_clicked'] and ('analysis_results_unplugged' in st.session_state or 'analysis_results_plugged' in st.session_state):
    res_unp = st.session_state.get('analysis_results_unplugged', None)
    res_plg = st.session_state.get('analysis_results_plugged', None)
    
    unp_ok = res_unp is not None and res_unp['success']
    plg_ok = res_plg is not None and res_plg['success']
    
    if (res_unp is not None and not unp_ok) or (res_plg is not None and not plg_ok):
        st.warning("No stable notes detected in one or more recordings. Try lowering the RMS threshold or minimum duration.")
        
    if unp_ok or plg_ok:
        def get_val(res_dict, key):
            return res_dict[key] if res_dict and key in res_dict else np.nan
            
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
        
        # --- Diagnostic Plotting ---
        from midi_alignment import get_alignment_mask, plot_alignment_diagnostics
        
        midi_timing = st.session_state.get('analysis_results_midi_timing', [])
        if midi_timing:
            st.subheader("DTW Alignment Diagnostics")
            
            # Unplugged Diagnostic
            if unp_ok:
                st.write("**Unplugged Alignment:**")
                time_array_unp = librosa.times_like(res_unp['f0'], sr=res_unp['sr'], hop_length=512)
                f0_midi_unp = librosa.hz_to_midi(res_unp['f0'])
                mask_unp, expected_unp = get_alignment_mask(midi_timing, time_array_unp, res_unp['y'], res_unp['sr'], hop_length=512)
                fig_unp_dtw = plot_alignment_diagnostics(
                    time_array_unp, 
                    f0_midi_unp, 
                    expected_unp, 
                    mask_unp
                )
                st.pyplot(fig_unp_dtw)
            
            # Plugged Diagnostic
            if plg_ok:
                st.write("**Plugged Alignment:**")
                time_array_plg = librosa.times_like(res_plg['f0'], sr=res_plg['sr'], hop_length=512)
                f0_midi_plg = librosa.hz_to_midi(res_plg['f0'])
                mask_plg, expected_plg = get_alignment_mask(midi_timing, time_array_plg, res_plg['y'], res_plg['sr'], hop_length=512)
                fig_plg_dtw = plot_alignment_diagnostics(
                    time_array_plg, 
                    f0_midi_plg, 
                    expected_plg, 
                    mask_plg
                )
                st.pyplot(fig_plg_dtw)
        
        st.subheader("Legacy Island Intonation Results")
        
        import pandas as pd
        
        # Create a DataFrame for the legacy table
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
        
        # Format the DataFrame for display to render NaNs as blank cells
        st.dataframe(df.style.format("{:.2f}", na_rep=""), use_container_width=True)
        

        # Create download button
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
        
        # --- Step 3: Note Sequence Comparison ---
        st.subheader("Note Sequence Comparison")
        
        midi_seq = st.session_state.get('analysis_results_midi', [])
        unp_seq = res_unp['detected_notes_sequence'] if unp_ok else []
        plg_seq = res_plg['detected_notes_sequence'] if plg_ok else []
        
        # We want to display them side-by-side. We use zip_longest to pad unequal lengths cleanly.
        from itertools import zip_longest
        
        seq_data = {}
        if midi_seq:
            seq_data["MIDI Reference Sequence"] = midi_seq
        if unp_ok:
            seq_data["Detected Sequence (Unplugged)"] = unp_seq
        if plg_ok:
            seq_data["Detected Sequence (Plugged)"] = plg_seq
            
        if seq_data:
            # zip_longest transposes the padded arrays so we can feed them to DataFrame
            padded_rows = list(zip_longest(*seq_data.values(), fillvalue=""))
            
            # Reconstruct the columns
            padded_columns = {col: [row[i] for row in padded_rows] for i, col in enumerate(seq_data.keys())}
            
            df_seq = pd.DataFrame(padded_columns)
            # Make the index 1-based for readability (Note 1, Note 2, etc.)
            df_seq.index = df_seq.index + 1
            df_seq.index.name = "Note Index"
            
            st.dataframe(df_seq, use_container_width=True)
            
            csv_seq = df_seq.to_csv().encode('utf-8')
            st.download_button(
                label="Download Sequence Data as CSV",
                data=csv_seq,
                file_name='note_sequence_comparison.csv',
                mime='text/csv',
            )
        else:
            st.info("Upload an audio file or MIDI reference to see the sequence comparison.")
        # --- Step 4: Plotly Graphing ---
        st.subheader("Pitch Track Visualizations")
        
        # Interactive checkboxes cleanly separated right above the graph
        col_t1, col_t2, col_t3 = st.columns(3)
        show_raw = col_t1.checkbox("Show Raw pYIN f0 (voiced)", value=True)
        show_steady = col_t2.checkbox("Show Isolated Steady Notes", value=True)
        show_target = col_t3.checkbox("Show Target Pitch", value=True)
        
        # Helper function to avoid repeating the huge Plotly code block twice
        def render_plotly_fig(res_dict, title_suffix):
            f0 = res_dict['f0']
            final_mask = res_dict['final_mask']
            f0_target = res_dict['f0_target']
            full_deviation = res_dict['full_deviation']
            sr = res_dict['sr']
            
            times = librosa.times_like(f0, sr=sr, hop_length=512)
            f0_steady = np.full_like(f0, np.nan)
            f0_steady[final_mask] = f0[final_mask]
            
            hover_text = []
            for d_pitch, t_pitch, dev in zip(f0_steady, f0_target, full_deviation):
                if not np.isnan(d_pitch):
                    hover_text.append(f"Detected: {d_pitch:.1f} Hz<br>Target: {t_pitch:.1f} Hz<br>Dev: {dev:.1f} ¢")
                else:
                    hover_text.append("")
                    
            fig = go.Figure()
            
            if show_raw:
                fig.add_trace(go.Scatter(
                    x=times, y=f0, mode='lines', name='Raw pYIN f0 (voiced)',
                    line=dict(color='rgba(128, 128, 128, 0.3)', width=1), hoverinfo='skip'
                ))
            
            if show_steady:
                fig.add_trace(go.Scatter(
                    x=times, y=f0_steady, mode='lines', name='Isolated Steady Notes',
                    line=dict(color='blue', width=2), text=hover_text, hovertemplate="%{text}<extra></extra>"
                ))
            
            if show_target:
                fig.add_trace(go.Scatter(
                    x=times, y=f0_target, mode='lines', name='Target Pitch (Nearest Semitone)',
                    line=dict(color='red', width=2, dash='dash'), hovertemplate="Target: %{y:.1f} Hz<extra></extra>"
                ))
            
            max_y = np.nanmax(f0) if not np.all(np.isnan(f0)) else 2000
            tick_vals = np.arange(0, max_y + 500, 500)
            tick_text = [f"{v/1000:g}kHz" for v in tick_vals]
            
            fig.update_layout(
                title=f"Pitch Track vs Isolated Steady-State Notes ({title_suffix})",
                xaxis_title="Time (seconds)",
                yaxis_title="Frequency",
                yaxis=dict(tickmode='array', tickvals=tick_vals, ticktext=tick_text, range=[0, max_y + 200]),
                hovermode="x unified",
                margin=dict(l=20, r=20, t=40, b=20)
            )
            return fig

        # Use Streamlit Tabs to keep the UI clean if both are present
        if unp_ok and plg_ok:
            tab1, tab2 = st.tabs(["Unplugged Recording", "Plugged Recording"])
            with tab1:
                fig_unp = render_plotly_fig(res_unp, "Unplugged")
                st.plotly_chart(fig_unp, use_container_width=True)
            with tab2:
                fig_plg = render_plotly_fig(res_plg, "Plugged")
                st.plotly_chart(fig_plg, use_container_width=True)
        elif unp_ok:
            fig_unp = render_plotly_fig(res_unp, "Unplugged")
            st.plotly_chart(fig_unp, use_container_width=True)
        elif plg_ok:
            fig_plg = render_plotly_fig(res_plg, "Plugged")
            st.plotly_chart(fig_plg, use_container_width=True)
