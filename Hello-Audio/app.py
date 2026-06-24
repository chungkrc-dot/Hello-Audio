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
    It isolates steady-state notes using pYIN and RMS amplitude thresholding, and utilizes a digital MIDI score as a reference to calculate intonation deviation.
    """)
    
    # 1. Sidebar
    instrument, switch_prob, rms_threshold, min_frames, max_pitch_slope = render_sidebar_parameters()
    
    # 2. File Uploads
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
            
    # 3. Execution Engine
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
    with col_btn1:
        dtw_clicked = st.button("Run DTW Alignment", type="primary")
    with col_btn2:
        legacy_clicked = st.button("Run Legacy Analysis", type="primary")

    if dtw_clicked or legacy_clicked:
        if file_unplugged is None and file_plugged is None:
            st.error("Please upload at least one audio file to run the analysis.")
        else:
            st.session_state['active_view'] = 'dtw' if dtw_clicked else 'legacy'
            st.session_state['analyze_clicked'] = True
            
            status_container = st.empty()
            status_container.info("Processing... If this is the first run, pitch extraction may take a moment.")
            
            from pitch_engine import extract_pitch_and_rms
            
            # Extract and cache
            if file_unplugged is not None and 'extracted_unp' not in st.session_state:
                with st.spinner("Extracting Pitch (Unplugged) using pYIN..."):
                    st.session_state['extracted_unp'] = extract_pitch_and_rms(file_unplugged, instrument, switch_prob)
                    
            if file_plugged is not None and 'extracted_plg' not in st.session_state:
                with st.spinner("Extracting Pitch (Plugged) using pYIN..."):
                    st.session_state['extracted_plg'] = extract_pitch_and_rms(file_plugged, instrument, switch_prob)

            if file_midi is not None and 'analysis_results_midi' not in st.session_state:
                with st.spinner("Parsing MIDI Reference Sequence..."):
                    st.session_state['analysis_results_midi'] = parse_midi(file_midi)
                    st.session_state['analysis_results_midi_timing'] = parse_midi_with_timing(file_midi)
            
            # Fast analysis logic
            if file_unplugged is not None:
                with st.spinner("Processing 'Unplugged' Intonation..."):
                    y, sr, f0, voiced_flag, rms = st.session_state['extracted_unp']
                    res_unp = analyze_intonation(y, sr, f0, voiced_flag, rms, rms_threshold, min_frames, max_pitch_slope)
                    res_unp.update(analyze_amplitude(y, sr))
                    st.session_state['analysis_results_unplugged'] = res_unp

            if file_plugged is not None:
                with st.spinner("Processing 'Plugged' Intonation..."):
                    y, sr, f0, voiced_flag, rms = st.session_state['extracted_plg']
                    res_plg = analyze_intonation(y, sr, f0, voiced_flag, rms, rms_threshold, min_frames, max_pitch_slope)
                    res_plg.update(analyze_amplitude(y, sr))
                    st.session_state['analysis_results_plugged'] = res_plg

            status_container.success("Processing complete!")

    # 4. Display Results
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
                    from midi_alignment import get_alignment_mask
                    from visualization import plot_alignment_diagnostics
                    st.subheader("DTW Alignment Diagnostics")
                    
                    if unp_ok:
                        st.write("**Unplugged Alignment:**")
                        time_array_unp = librosa.times_like(res_unp['f0'], sr=res_unp['sr'], hop_length=512)
                        f0_midi_unp = librosa.hz_to_midi(res_unp['f0'])
                        mask_unp, expected_unp = get_alignment_mask(midi_timing, time_array_unp, res_unp['y'], res_unp['sr'], hop_length=512)
                        strict_mask_unp = mask_unp & res_unp['final_mask']
                        fig_unp_dtw = plot_alignment_diagnostics(time_array_unp, f0_midi_unp, expected_unp, strict_mask_unp)
                        st.pyplot(fig_unp_dtw)
                    
                    if plg_ok:
                        st.write("**Plugged Alignment:**")
                        time_array_plg = librosa.times_like(res_plg['f0'], sr=res_plg['sr'], hop_length=512)
                        f0_midi_plg = librosa.hz_to_midi(res_plg['f0'])
                        mask_plg, expected_plg = get_alignment_mask(midi_timing, time_array_plg, res_plg['y'], res_plg['sr'], hop_length=512)
                        strict_mask_plg = mask_plg & res_plg['final_mask']
                        fig_plg_dtw = plot_alignment_diagnostics(time_array_plg, f0_midi_plg, expected_plg, strict_mask_plg)
                        st.pyplot(fig_plg_dtw)
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
