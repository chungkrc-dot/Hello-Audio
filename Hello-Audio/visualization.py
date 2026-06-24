import streamlit as st
import numpy as np
import librosa
import plotly.graph_objects as go
import matplotlib.pyplot as plt

def render_plotly_fig(res_dict, title_suffix, show_raw, show_steady, show_target):
    """
    Renders an interactive Plotly graph of the pitch tracks vs time.
    """
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

def render_pitch_track_visualizations(unp_ok, plg_ok, res_unp, res_plg):
    """
    Sets up the Streamlit UI for the Plotly graphs and renders them based on checkboxes.
    """
    st.subheader("Pitch Track Visualizations")
    
    col_t1, col_t2, col_t3 = st.columns(3)
    show_raw = col_t1.checkbox("Show Raw pYIN f0 (voiced)", value=True)
    show_steady = col_t2.checkbox("Show Isolated Steady Notes", value=True)
    show_target = col_t3.checkbox("Show Target Pitch", value=True)

    if unp_ok and plg_ok:
        tab1, tab2 = st.tabs(["Unplugged Recording", "Plugged Recording"])
        with tab1:
            fig_unp = render_plotly_fig(res_unp, "Unplugged", show_raw, show_steady, show_target)
            st.plotly_chart(fig_unp, use_container_width=True)
        with tab2:
            fig_plg = render_plotly_fig(res_plg, "Plugged", show_raw, show_steady, show_target)
            st.plotly_chart(fig_plg, use_container_width=True)
    elif unp_ok:
        fig_unp = render_plotly_fig(res_unp, "Unplugged", show_raw, show_steady, show_target)
        st.plotly_chart(fig_unp, use_container_width=True)
    elif plg_ok:
        fig_plg = render_plotly_fig(res_plg, "Plugged", show_raw, show_steady, show_target)
        st.plotly_chart(fig_plg, use_container_width=True)


def plot_alignment_diagnostics(time_array, f0_midi, expected_audio_pitch, valid_dtw_mask):
    """
    Renders a diagnostic plot showing the DTW expected pitch path natively 
    overlaid on the detected pYIN pitch curve using Matplotlib.
    Matched pitches (inside mask) are Blue, extraneous pitches (outside mask) are Yellow.
    """
    fig, ax = plt.subplots(figsize=(10, 4))
    
    # 1. Plot the continuous expected MIDI pitch (the grey staircase)
    ax.plot(time_array, expected_audio_pitch, color='grey', linewidth=3, alpha=0.5, label='DTW Bridge Target')
    
    # 2. Plot the raw pYIN f0. We break it into two groups based on the DTW mask.
    # Group A: Extraneous notes (outside the DTW mask). Yellow.
    extraneous_f0 = np.copy(f0_midi)
    extraneous_f0[valid_dtw_mask] = np.nan
    ax.plot(time_array, extraneous_f0, color='gold', linewidth=1.5, alpha=0.8, label='Extraneous F0')
    
    # Group B: Matched notes (inside the DTW mask). Blue.
    matched_f0 = np.copy(f0_midi)
    matched_f0[~valid_dtw_mask] = np.nan
    ax.plot(time_array, matched_f0, color='blue', linewidth=1.5, alpha=0.9, label='Matched F0')

    ax.set_title("Absolute-Time Bridge Diagnostics")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Pitch (MIDI)")
    ax.legend(loc='upper right')
    
    # Clean up bounds dynamically based on active data
    valid_data = f0_midi[~np.isnan(f0_midi)]
    if len(valid_data) > 0:
        ax.set_ylim([np.min(valid_data) - 2, np.max(valid_data) + 2])
        
    plt.tight_layout()
    return fig
