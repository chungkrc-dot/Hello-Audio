"""
app.py
# Trigger Streamlit rerun 2
------
Hello-Audio: A comparative intonation and amplitude analysis application.
This orchestrator module manages the Streamlit UI state, handles file uploads, 
and conditionally routes audio data to either the advanced DTW Alignment Engine 
(if a MIDI reference is provided) or the Legacy Pitch Analysis Engine.
"""
import streamlit as st
import sys
import os

# Ensure the root directory is on the path so we can import from src/ and app/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.pitch_engine import analyze_intonation
from src.amplitude_analysis import analyze_amplitude
from src.midi_parser import parse_midi, parse_midi_with_timing
from ui_components import render_sidebar_parameters, render_results_table, render_sequence_comparison, render_dtw_results_table, render_dtw_summary_table
from src.visualization import render_pitch_track_visualizations

def _check_and_invalidate_cache(uploaded_file, name_key, keys_to_delete):
    if uploaded_file is not None and uploaded_file.name != st.session_state.get(name_key, ""):
        st.session_state['analyze_clicked'] = False
        st.session_state[name_key] = uploaded_file.name
        for key in keys_to_delete:
            if key in st.session_state:
                del st.session_state[key]

def _check_and_invalidate_engine_cache(pitch_engine, instrument, switch_prob, freq_limits):
    if ('pitch_engine' not in st.session_state or
        'engine_instrument' not in st.session_state or 
        'engine_switch_prob' not in st.session_state or
        'engine_freq_limits' not in st.session_state or
        st.session_state['pitch_engine'] != pitch_engine or
        st.session_state['engine_instrument'] != instrument or
        st.session_state['engine_switch_prob'] != switch_prob or
        st.session_state['engine_freq_limits'] != freq_limits):
        
        st.session_state['pitch_engine'] = pitch_engine
        st.session_state['engine_instrument'] = instrument
        st.session_state['engine_switch_prob'] = switch_prob
        st.session_state['engine_freq_limits'] = freq_limits
        return True
    return False


def main():
    st.set_page_config(page_title="Hello-Audio", layout="wide")
    
    st.title("Hello-Audio")
    st.warning("**Dataset & Instrument Caveat:** Hello-Audio is primarily designed, parameterized, and tested using the relevant instrument samples from the URMP dataset. As such, the application in its current state is strictly validated for **Violin, Viola, and Cello**. It should not be used to analyze other instruments without further calibration.")
    st.info(
        "**Purpose & measurement scope:** Hello-Audio was designed for one comparison — the "
        "difference in **amplitude** and **intonation** when a performer plays **without earplugs "
        "('Unplugged')** versus **with earplugs ('Plugged')**. Because those two quantities are the "
        "effect under study, expressive variation that also moves loudness or pitch — dynamic "
        "shading, tempo fluctuation, ornaments and vibrato — should be **minimised in the recorded "
        "performances**, as it otherwise confounds the measurement. The engine still runs when such "
        "expression is present, but the comparison is only clean when it is suppressed. See the "
        "recording guidelines below."
    )
    st.write("""
    This application comparatively analyzes the amplitude and intonation of uploaded audio recordings. 
    It uses the pYIN algorithm combined with strict Pitch Analyser Parameters (configured in the sidebar) to isolate clean, steady-state notes while aggressively filtering out transients, glissandos, and background noise.

    **Intonation Deviation Calculation:**
    - **With MIDI Upload:** Unlocks the advanced **DTW Alignment Engine**, which mathematically aligns your performance to the true note-by-note MIDI targets and scores the deviation of the steady-state median pitch against the exact target.
    - **Without MIDI Upload:** Falls back to the general **Legacy Analysis Engine**, which evaluates intonation deviation by comparing your performed pitch to the nearest absolute semitone on the 12-TET scale.
    """)

    with st.expander("📋 Recording & Preparation Guidelines (read before collecting data)"):
        st.markdown(
            """
Follow these guidelines so a single, fixed analysis configuration is valid for every take and the
plugged-vs-unplugged comparison is not confounded by performance expression.

**Performance**
- **Fixed repertoire** per instrument — every participant plays the same score, so the comparison is within-material.
- **Minimal expression:** steady dynamics (no crescendo/diminuendo), steady tempo (no *accelerando* / *ritardando*), **no ornaments**, and **no vibrato**. These modulate the very loudness and pitch the study measures.
- **No click track needed.** Performers may play at their own steady tempo, near the score's written tempo.

**Recording**
- **Controlled acoustics:** a quiet, low-reverberation room. Keep microphone type, position and gain **identical** across the Plugged and Unplugged takes of the same performer and piece, and record both conditions in **one session**.
- **Short excerpts:** keep each take short (**≤ ~2 minutes**). This is for data hygiene and easy re-runs, not alignment stability (the current pipeline aligns full-length takes fine).
- **Clean attack:** start on an unambiguous first note; a short count-in helps alignment latch on.

**Preparation for analysis**
- **Trim** leading and trailing silence so the file begins at the first note and ends at the last. Room tone may be captured separately to document signal-to-noise ratio, but keep it **out of** the analysed region.

**Recommended analysis settings for this protocol** (these deviate from the shipped defaults — see Technical Manual §1, §4A, §6):
- **DTW:** *uncheck* **"Force Global DTW Alignment"** → use **Subsequence** DTW (absorbs participant tempo variation; short excerpts stay clear of the long-recording drift regime).
- **Adaptive RMS:** *uncheck* **"Enable Adaptive RMS Threshold"** → use the static gate (controlled studio + near-continuous solo playing makes the adaptive floor over-gate real notes).
            """
        )

    # ==========================================
    # 1. File Uploads & State Management
    # ==========================================
    # Manages the physical file inputs and resets the processing state 
    # whenever a new file is uploaded to prevent stale cache bugs.
    col_u1, col_u2, col_u3 = st.columns(3)
    with col_u1:
        file_unplugged = st.file_uploader("Upload 'Unplugged' Audio (without earplugs)", type=["wav", "mp3"])
    with col_u2:
        file_plugged = st.file_uploader("Upload 'Plugged' Audio (with earplugs)", type=["wav", "mp3"])
    target_track = None
    with col_u3:
        file_midi = st.file_uploader("Upload MIDI Reference (Optional)", type=["mid", "midi"])
        if file_midi is not None:
            from src.midi_parser import (
                describe_midi_tracks, format_track_label,
                fits_instrument, best_fitting_instrument,
            )
            # The instrument selector lives in the sidebar, which is rendered
            # after this block; read the committed value so track labels can be
            # annotated against it on every rerun after the first.
            sel_instrument = st.session_state.get("selected_instrument")
            tracks = describe_midi_tracks(file_midi)

            if not tracks:
                st.error("This MIDI file contains no note events.")
            elif len(tracks) == 1:
                # A single-part MIDI is assumed to be the correct part — the
                # assumption the application is built on. No prompt is shown.
                target_track = next(iter(tracks))
            else:
                track_options = list(tracks.keys())
                track_labels = [format_track_label(t, tracks[t], sel_instrument)
                                for t in track_options]
                selected_label = st.selectbox(
                    "Select Track to Analyze", track_labels,
                    help="This MIDI holds several parts (a condensed score). Pick the "
                         "one matching the uploaded audio — the pitch range and duration "
                         "shown are the best guide."
                )
                target_track = track_options[track_labels.index(selected_label)]

            # Advisory only: transposing parts and scordatura are legitimate, so
            # never block the run on a range mismatch.
            if target_track is not None and sel_instrument:
                entry = tracks[target_track]
                if not fits_instrument(entry['lo'], entry['hi'], sel_instrument):
                    alt = best_fitting_instrument(entry['lo'], entry['hi'])
                    st.warning(
                        f"Track {target_track} spans {entry['lo_note']}–{entry['hi_note']}, "
                        f"outside the expected range for {sel_instrument}"
                        + (f" (it fits {alt.capitalize()})." if alt else ".")
                        + " Check that this is the right part before analysing."
                    )

    # ==========================================
    # 2. Sidebar Parameters
    # ==========================================
    # 1. SIDEBAR PARAMETERS
    pitch_engine, instrument, reference_pitch_hz, switch_prob, rms_threshold, min_frames, max_pitch_slope, confidence_threshold, toggles = render_sidebar_parameters(is_midi_uploaded=(file_midi is not None))
    
    # Check if core parameters changed
    enable_freq_limits = toggles.get('freq_limits', True)
    if _check_and_invalidate_engine_cache(pitch_engine, instrument, switch_prob, enable_freq_limits):
        st.session_state.pop('extracted_unp', None)
        st.session_state.pop('extracted_plg', None)
        st.session_state.pop('analysis_results_unplugged', None)
        st.session_state.pop('analysis_results_plugged', None)

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
    _check_and_invalidate_cache(file_unplugged, 'file_unplugged_name', ['analysis_results_unplugged', 'extracted_unp'])
    _check_and_invalidate_cache(file_plugged, 'file_plugged_name', ['analysis_results_plugged', 'extracted_plg'])
    _check_and_invalidate_cache(file_midi, 'file_midi_name', ['analysis_results_midi', 'analysis_results_midi_timing'])

    # Detect Parameter Changes to Invalidate Cache
    current_params = {
        'instrument': instrument,
        'reference_pitch_hz': reference_pitch_hz,
        'switch_prob': switch_prob,
        'rms_threshold': rms_threshold,
        'min_frames': min_frames,
        'max_pitch_slope': max_pitch_slope,
        'toggles': toggles,
        'target_track': target_track
    }
    
    if 'last_params' not in st.session_state:
        st.session_state['last_params'] = {}
        
    if st.session_state['last_params'] != current_params:
        st.session_state['analyze_clicked'] = False
        st.session_state['last_params'] = current_params
        # Clear all cached extractions and results so the analysis reruns with new settings
        keys_to_clear = [
            'analysis_results_unplugged', 'extracted_unp', 
            'analysis_results_plugged', 'extracted_plg', 
            'analysis_results_midi', 'analysis_results_midi_timing'
        ]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
            
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
            
            from src.pitch_engine import extract_pitch_and_rms
            
            # Extract and cache
            enable_freq_limits = toggles.get('freq_limits', True)
            if file_unplugged is not None and 'extracted_unp' not in st.session_state:
                with st.spinner("Extracting Pitch (Unplugged) using pYIN..."):
                    st.session_state['extracted_unp'] = extract_pitch_and_rms(file_unplugged, instrument, switch_prob, enable_freq_limits, pitch_engine=pitch_engine)

            if file_plugged is not None and 'extracted_plg' not in st.session_state:
                with st.spinner("Extracting Pitch (Plugged) using pYIN..."):
                    st.session_state['extracted_plg'] = extract_pitch_and_rms(file_plugged, instrument, switch_prob, enable_freq_limits, pitch_engine=pitch_engine)

            if file_midi is not None and 'analysis_results_midi' not in st.session_state:
                with st.spinner("Parsing MIDI Reference Sequence..."):
                    st.session_state['analysis_results_midi'] = parse_midi(file_midi, target_track=target_track)
                    st.session_state['analysis_results_midi_timing'] = parse_midi_with_timing(file_midi, target_track=target_track)
            
            # Fast analysis logic
            if file_unplugged is not None:
                with st.spinner("Processing 'Unplugged' Intonation..."):
                    y, sr, f0, voiced_flag, rms, voicing_prob = st.session_state['extracted_unp']
                    res_unp = analyze_intonation(y, sr, f0, voiced_flag, rms, rms_threshold, min_frames, max_pitch_slope, toggles, voicing_prob, confidence_threshold, reference_pitch_hz)
                    res_unp.update(analyze_amplitude(y, sr))
                    st.session_state['analysis_results_unplugged'] = res_unp

            if file_plugged is not None:
                with st.spinner("Processing 'Plugged' Intonation..."):
                    y, sr, f0, voiced_flag, rms, voicing_prob = st.session_state['extracted_plg']
                    res_plg = analyze_intonation(y, sr, f0, voiced_flag, rms, rms_threshold, min_frames, max_pitch_slope, toggles, voicing_prob, confidence_threshold, reference_pitch_hz)
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
                    from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics
                    from src.visualization import plot_alignment_diagnostics
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
                        time_array_unp, expected_unp, warped_unp, expected_note_index_unp, folded_f0_hz_unp, folded_f0_midi_unp, strict_mask_unp, correction_array_unp = process_dtw_alignment(
                            midi_timing, res_unp['f0'], res_unp['y'], res_unp['sr'], res_unp['final_mask'], toggles, max_pitch_slope
                        )
                        
                        fig_unp_dtw = plot_alignment_diagnostics(
                            time_array_unp, folded_f0_midi_unp, expected_unp, strict_mask_unp, 
                            expected_note_index_unp, show_target, show_extraneous, show_matched
                        )
                        st.plotly_chart(fig_unp_dtw, use_container_width=True)
                        
                        dtw_metrics_unp = calculate_dtw_metrics(midi_timing, time_array_unp, folded_f0_hz_unp, res_unp['rms'], res_unp['final_mask'], warped_unp, correction_array_unp, res_unp.get('voicing_prob'), reference_pitch_hz)
                    
                    if plg_ok:
                        st.write("**Plugged Alignment:**")
                        time_array_plg, expected_plg, warped_plg, expected_note_index_plg, folded_f0_hz_plg, folded_f0_midi_plg, strict_mask_plg, correction_array_plg = process_dtw_alignment(
                            midi_timing, res_plg['f0'], res_plg['y'], res_plg['sr'], res_plg['final_mask'], toggles, max_pitch_slope
                        )
                        
                        fig_plg_dtw = plot_alignment_diagnostics(
                            time_array_plg, folded_f0_midi_plg, expected_plg, strict_mask_plg, 
                            expected_note_index_plg, show_target, show_extraneous, show_matched
                        )
                        st.plotly_chart(fig_plg_dtw, use_container_width=True)
                        
                        dtw_metrics_plg = calculate_dtw_metrics(midi_timing, time_array_plg, folded_f0_hz_plg, res_plg['rms'], res_plg['final_mask'], warped_plg, correction_array_plg, res_plg.get('voicing_prob'), reference_pitch_hz)
                        
                    excluded_indices = render_dtw_results_table(dtw_metrics_unp, dtw_metrics_plg)
                    render_dtw_summary_table(dtw_metrics_unp, dtw_metrics_plg, excluded_indices,
                                             pitch_engine=pitch_engine)

                    # Distribution + Bland-Altman diagnostics for the shape statistics
                    # reported in the summary table above.
                    from src.midi_alignment import included_note_deviations, pair_note_deviations
                    from src.visualization import render_distribution_diagnostics

                    series = {}
                    if dtw_metrics_unp:
                        series["Unplugged"] = included_note_deviations(dtw_metrics_unp, excluded_indices)
                    if dtw_metrics_plg:
                        series["Plugged"] = included_note_deviations(dtw_metrics_plg, excluded_indices)

                    paired = None
                    if dtw_metrics_unp and dtw_metrics_plg:
                        dev_unp, dev_plg, note_labels = pair_note_deviations(
                            dtw_metrics_unp, dtw_metrics_plg, excluded_indices
                        )
                        if dev_unp.size >= 2:
                            paired = (dev_unp, dev_plg, "Unplugged", "Plugged", note_labels)

                    # DTW deviations are per-note medians of frame values, so they
                    # sit on a 5-cent lattice rather than the raw 10-cent frame grid.
                    from src.stats_summary import PYIN_NOTE_MEDIAN_RESOLUTION_CENTS
                    render_distribution_diagnostics(series, paired=paired, unit="cents",
                                                    key_prefix="dtw",
                                                    bin_width=PYIN_NOTE_MEDIAN_RESOLUTION_CENTS)
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

                # Distribution diagnostics. No Bland-Altman here: legacy mode
                # produces an unordered list of frame deviations per condition with
                # no note-level correspondence between them, so the two conditions
                # cannot be paired and a Bland-Altman plot would be meaningless.
                from src.visualization import render_distribution_diagnostics
                import numpy as _np

                legacy_series = {}
                if unp_ok:
                    legacy_series["Unplugged"] = _np.asarray(res_unp['deviation_cents_list'], dtype=float)
                if plg_ok:
                    legacy_series["Plugged"] = _np.asarray(res_plg['deviation_cents_list'], dtype=float)
                from src.stats_summary import PYIN_RESOLUTION_CENTS
                render_distribution_diagnostics(legacy_series, unit="cents", key_prefix="legacy",
                                                bin_width=PYIN_RESOLUTION_CENTS)

                # Pitch Tracks
                render_pitch_track_visualizations(unp_ok, plg_ok, res_unp, res_plg)

if __name__ == "__main__":
    main()
