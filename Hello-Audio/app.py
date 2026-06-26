"""
app.py
------
Hello-Audio: A comparative intonation and amplitude analysis application.
This orchestrator module manages the Streamlit UI state, handles file uploads, 
and conditionally routes audio data to either the advanced DTW Alignment Engine 
(if a MIDI reference is provided) or the Legacy Pitch Analysis Engine.
"""
import streamlit as st
from pitch_engine import analyze_intonation
from amplitude_analysis import analyze_amplitude
from midi_parser import parse_midi, parse_midi_with_timing

# Import our new modular UI and visualization components
from ui_components import render_sidebar_parameters, render_results_table, render_sequence_comparison
from visualization import render_pitch_track_visualizations

def main():
    st.set_page_config(page_title="Hello-Audio", layout="wide")
    
    st.title("Hello-Audio")
    st.write("""
    This application comparatively analyzes the amplitude and intonation of uploaded audio recordings. 
    It uses the pYIN algorithm combined with strict Pitch Analyser Parameters (configured in the sidebar) to isolate clean, steady-state notes while aggressively filtering out transients, glissandos, and background noise.

    **Intonation Deviation Calculation:**
    - **With MIDI Upload:** Unlocks the advanced **DTW Alignment Engine**, which mathematically aligns your performance to the true note-by-note MIDI targets and scores the deviation of the steady-state median pitch against the exact target.
    - **Without MIDI Upload:** Falls back to the general **Legacy Analysis Engine**, which evaluates intonation deviation by comparing your performed pitch to the nearest absolute semitone on the 12-TET scale.
    """)
    
    # ==========================================
    # 1. Sidebar Parameters
    # ==========================================
    # Configures the strict filtering thresholds (Switch Probability, RMS, Sustain, Slope)
    # used by pYIN to isolate intentional, steady-state notes from noise.
    instrument, switch_prob, rms_threshold, min_frames, max_pitch_slope, toggles = render_sidebar_parameters()
    
    # ==========================================
    # 2. File Uploads & State Management
    # ==========================================
    # Manages the physical file inputs and resets the processing state 
    # whenever a new file is uploaded to prevent stale cache bugs.
    col_u1, col_u2, col_u3 = st.columns(3)
    with col_u1:
        file_unplugged = st.file_uploader("Upload 'Unplugged' Audio (without earplugs)", type=["wav", "mp3"])
    with col_u2:
        file_plugged = st.file_uploader("Upload 'Plugged' Audio (with earplugs)", type=["wav", "mp3"])
    with col_u3:
        file_midi = st.file_uploader("Upload MIDI Reference (Optional)", type=["mid", "midi"])
        
    # State Management
    if 'file_unplugged_name' not in st.session_state:
        st.session_state['file_unplugged_name'] = ""
    if 'file_plugged_name' not in st.session_state:
        st.session_state['file_plugged_name'] = ""
    if 'file_midi_name' not in st.session_state:
        st.session_state['file_midi_name'] = ""
    if 'analyze_clicked' not in st.session_state:
        st.session_state['analyze_clicked'] = False

    # Invalidate cache if files change
    if file_unplugged is not None and file_unplugged.name != st.session_state['file_unplugged_name']:
        st.session_state['analyze_clicked'] = False
        st.session_state['file_unplugged_name'] = file_unplugged.name
        if 'analysis_results_unplugged' in st.session_state:
            del st.session_state['analysis_results_unplugged']
        if 'extracted_unp' in st.session_state:
            del st.session_state['extracted_unp']

    if file_plugged is not None and file_plugged.name != st.session_state['file_plugged_name']:
        st.session_state['analyze_clicked'] = False
        st.session_state['file_plugged_name'] = file_plugged.name
        if 'analysis_results_plugged' in st.session_state:
            del st.session_state['analysis_results_plugged']
        if 'extracted_plg' in st.session_state:
            del st.session_state['extracted_plg']

    if file_midi is not None and file_midi.name != st.session_state['file_midi_name']:
        st.session_state['analyze_clicked'] = False
        st.session_state['file_midi_name'] = file_midi.name
        if 'analysis_results_midi' in st.session_state:
            del st.session_state['analysis_results_midi']

    # Detect Parameter Changes to Invalidate Cache
    current_params = {
        'instrument': instrument,
        'switch_prob': switch_prob,
        'rms_threshold': rms_threshold,
        'min_frames': min_frames,
        'max_pitch_slope': max_pitch_slope,
        'toggles': toggles
    }
    
    if 'last_params' not in st.session_state:
        st.session_state['last_params'] = {}
        
    if st.session_state['last_params'] != current_params:
        st.session_state['analyze_clicked'] = False
        st.session_state['last_params'] = current_params
        # Clear all cached extractions and results so the analysis reruns with new settings
        if 'analysis_results_unplugged' in st.session_state:
            del st.session_state['analysis_results_unplugged']
        if 'extracted_unp' in st.session_state:
            del st.session_state['extracted_unp']
        if 'analysis_results_plugged' in st.session_state:
            del st.session_state['analysis_results_plugged']
        if 'extracted_plg' in st.session_state:
            del st.session_state['extracted_plg']
        if 'analysis_results_midi' in st.session_state:
            del st.session_state['analysis_results_midi']
            
    # ==========================================
    # 3. Execution Engine
    # ==========================================
    # The core processing loop. It routes execution based on the presence of the MIDI file.
    # Pitch extraction (pYIN) and MIDI parsing are heavily cached to prevent 
    # redundant computation on UI refreshes.
    analyze_clicked = st.button("Run Analysis", type="primary")

    if analyze_clicked:
        if file_unplugged is None and file_plugged is None:
            st.error("Please upload at least one audio file to run the analysis.")
        else:
            # Smart Fallback Logic: Run DTW if MIDI is provided, otherwise fall back to Legacy
            st.session_state['active_view'] = 'dtw' if file_midi is not None else 'legacy'
            st.session_state['analyze_clicked'] = True
            
            status_container = st.empty()
            status_container.info("Processing... If this is the first run, pitch extraction may take a moment.")
            
            from pitch_engine import extract_pitch_and_rms
            
            # Extract and cache
            enable_freq_limits = toggles.get('freq_limits', True)
            if file_unplugged is not None and 'extracted_unp' not in st.session_state:
                with st.spinner("Extracting Pitch (Unplugged) using pYIN..."):
                    st.session_state['extracted_unp'] = extract_pitch_and_rms(file_unplugged, instrument, switch_prob, enable_freq_limits)
                    
            if file_plugged is not None and 'extracted_plg' not in st.session_state:
                with st.spinner("Extracting Pitch (Plugged) using pYIN..."):
                    st.session_state['extracted_plg'] = extract_pitch_and_rms(file_plugged, instrument, switch_prob, enable_freq_limits)

            if file_midi is not None and 'analysis_results_midi' not in st.session_state:
                with st.spinner("Parsing MIDI Reference Sequence..."):
                    st.session_state['analysis_results_midi'] = parse_midi(file_midi)
                    st.session_state['analysis_results_midi_timing'] = parse_midi_with_timing(file_midi)
            
            # Fast analysis logic
            if file_unplugged is not None:
                with st.spinner("Processing 'Unplugged' Intonation..."):
                    y, sr, f0, voiced_flag, rms = st.session_state['extracted_unp']
                    res_unp = analyze_intonation(y, sr, f0, voiced_flag, rms, rms_threshold, min_frames, max_pitch_slope, toggles)
                    res_unp.update(analyze_amplitude(y, sr))
                    st.session_state['analysis_results_unplugged'] = res_unp

            if file_plugged is not None:
                with st.spinner("Processing 'Plugged' Intonation..."):
                    y, sr, f0, voiced_flag, rms = st.session_state['extracted_plg']
                    res_plg = analyze_intonation(y, sr, f0, voiced_flag, rms, rms_threshold, min_frames, max_pitch_slope, toggles)
                    res_plg.update(analyze_amplitude(y, sr))
                    st.session_state['analysis_results_plugged'] = res_plg

            status_container.success("Processing complete!")

    # ==========================================
    # 4. Display Results & Rendering
    # ==========================================
    # Handles all visual output. Dynamically routes to either the DTW diagnostic view 
    # or the Legacy sequential view based on the active state.
    if st.session_state.get('analyze_clicked') and ('analysis_results_unplugged' in st.session_state or 'analysis_results_plugged' in st.session_state):
        res_unp = st.session_state.get('analysis_results_unplugged', None)
        res_plg = st.session_state.get('analysis_results_plugged', None)
        active_view = st.session_state.get('active_view', 'legacy')
        
        unp_ok = res_unp is not None and res_unp['success']
        plg_ok = res_plg is not None and res_plg['success']
        
        if (res_unp is not None and not unp_ok) or (res_plg is not None and not plg_ok):
            st.warning("No stable notes detected in one or more recordings. Try lowering the RMS threshold or minimum duration.")
            
        if unp_ok or plg_ok:
            if active_view == 'dtw':
                midi_timing = st.session_state.get('analysis_results_midi_timing', [])
                if midi_timing:
                    import librosa
                    from midi_alignment import get_alignment_mask, calculate_dtw_metrics, apply_octave_folding
                    from visualization import plot_alignment_diagnostics
                    from ui_components import render_dtw_results_table, render_dtw_summary_table
                    
                    dtw_metrics_unp = None
                    dtw_metrics_plg = None
                    
                    st.subheader("DTW Alignment Diagnostics")
                    
                    col_t1, col_t2, col_t3 = st.columns(3)
                    with col_t1:
                        show_target = st.checkbox("Show DTW Bridge Target", value=True)
                    with col_t2:
                        show_extraneous = st.checkbox("Show Extraneous F0", value=True)
                    with col_t3:
                        show_matched = st.checkbox("Show Matched F0", value=True)
                    
                    if unp_ok:
                        st.write("**Unplugged Alignment:**")
                        time_array_unp = librosa.times_like(res_unp['f0'], sr=res_unp['sr'], hop_length=512)
                        mask_unp, expected_unp, warped_unp, expected_note_index_unp = get_alignment_mask(midi_timing, time_array_unp, res_unp['y'], res_unp['sr'], hop_length=512)
                        
                        # Globally fold the extracted pitch to correct tracking harmonics BEFORE plotting if enabled
                        if toggles.get('octave_folding', True):
                            folded_f0_hz_unp, folded_f0_midi_unp = apply_octave_folding(res_unp['f0'], expected_unp)
                        else:
                            folded_f0_hz_unp = res_unp['f0']
                            folded_f0_midi_unp = librosa.hz_to_midi(folded_f0_hz_unp)
                        
                        # Re-calculate the slope filter on the mathematically folded pitch path to remove any artificial vertical cliffs
                        import numpy as np
                        folded_pitch_slope_unp = np.concatenate(([0], np.abs(np.diff(folded_f0_midi_unp))))
                        if toggles.get('slope_filter', True):
                            folded_slope_mask_unp = (folded_pitch_slope_unp <= max_pitch_slope) | np.isnan(folded_pitch_slope_unp)
                        else:
                            folded_slope_mask_unp = np.ones_like(folded_pitch_slope_unp, dtype=bool)
                        
                        strict_mask_unp = mask_unp & res_unp['final_mask'] & folded_slope_mask_unp
                        fig_unp_dtw = plot_alignment_diagnostics(
                            time_array_unp, folded_f0_midi_unp, expected_unp, strict_mask_unp, 
                            expected_note_index_unp, show_target, show_extraneous, show_matched
                        )
                        st.plotly_chart(fig_unp_dtw, use_container_width=True)
                        
                        dtw_metrics_unp = calculate_dtw_metrics(midi_timing, time_array_unp, folded_f0_hz_unp, res_unp['rms'], res_unp['final_mask'], warped_unp)
                    
                    if plg_ok:
                        st.write("**Plugged Alignment:**")
                        time_array_plg = librosa.times_like(res_plg['f0'], sr=res_plg['sr'], hop_length=512)
                        mask_plg, expected_plg, warped_plg, expected_note_index_plg = get_alignment_mask(midi_timing, time_array_plg, res_plg['y'], res_plg['sr'], hop_length=512)
                        
                        # Globally fold the extracted pitch to correct tracking harmonics BEFORE plotting if enabled
                        if toggles.get('octave_folding', True):
                            folded_f0_hz_plg, folded_f0_midi_plg = apply_octave_folding(res_plg['f0'], expected_plg)
                        else:
                            folded_f0_hz_plg = res_plg['f0']
                            folded_f0_midi_plg = librosa.hz_to_midi(folded_f0_hz_plg)
                        
                        # Re-calculate the slope filter on the mathematically folded pitch path to remove any artificial vertical cliffs
                        import numpy as np
                        folded_pitch_slope_plg = np.concatenate(([0], np.abs(np.diff(folded_f0_midi_plg))))
                        if toggles.get('slope_filter', True):
                            folded_slope_mask_plg = (folded_pitch_slope_plg <= max_pitch_slope) | np.isnan(folded_pitch_slope_plg)
                        else:
                            folded_slope_mask_plg = np.ones_like(folded_pitch_slope_plg, dtype=bool)
                        
                        strict_mask_plg = mask_plg & res_plg['final_mask'] & folded_slope_mask_plg
                        fig_plg_dtw = plot_alignment_diagnostics(
                            time_array_plg, folded_f0_midi_plg, expected_plg, strict_mask_plg, 
                            expected_note_index_plg, show_target, show_extraneous, show_matched
                        )
                        st.plotly_chart(fig_plg_dtw, use_container_width=True)
                        
                        dtw_metrics_plg = calculate_dtw_metrics(midi_timing, time_array_plg, folded_f0_hz_plg, res_plg['rms'], res_plg['final_mask'], warped_plg)
                        
                    excluded_indices = render_dtw_results_table(dtw_metrics_unp, dtw_metrics_plg)
                    render_dtw_summary_table(dtw_metrics_unp, dtw_metrics_plg, excluded_indices)
                else:
                    st.info("Upload a MIDI reference to view DTW Alignment Diagnostics.")

            elif active_view == 'legacy':
                # Sequence Comparison
                midi_seq = st.session_state.get('analysis_results_midi', [])
                unp_seq = res_unp['detected_notes_sequence'] if unp_ok else []
                plg_seq = res_plg['detected_notes_sequence'] if plg_ok else []
                render_sequence_comparison(midi_seq, unp_seq, plg_seq)
                
                # Legacy Tables
                render_results_table(res_unp, res_plg, unp_ok, plg_ok)
                
                # Pitch Tracks
                render_pitch_track_visualizations(unp_ok, plg_ok, res_unp, res_plg)

if __name__ == "__main__":
    main()
