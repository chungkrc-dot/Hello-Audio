"""
validate_haydn_crosscorpus.py
-----------------------------
Cross-corpus generalisation check for the pitch/DTW pipeline on a SECOND,
independent string dataset: the anechoic multi-channel recordings of the Haydn
String Quartet Op.76 No.1 (Gomes, Lachenmayr, Thilakan & Kob, I3DA 2021;
Zenodo 4955282, CC-BY-NC-4.0). URMP (Appendices A, F, L) is a Rochester corpus;
this audio is from a different lab, room, instruments and players, so agreement
here is evidence the pipeline is not tuned to URMP's recording characteristics.

Configuration is the RESEARCH configuration, identical to
validate_short_excerpts.py (Appendix L): Subsequence DTW, Adaptive RMS off,
static gate, pYIN, short excerpts. Results are therefore directly comparable to
Appendix L's URMP numbers.

Ground truth is the WRITTEN score (OpenScore CC0 MusicXML of Op.76 No.1), parsed
with music21 and trimmed *deterministically by the documented bar ranges* of
each recorded excerpt — never tuned to yield. Because it is the written score
(not a repeat-expanded MIDI), "without repetitions" excerpts map cleanly.

There is no independent per-note F0 here (unlike URMP's Notes files), so this
validates detection yield, inclusion yield and the deviation distribution vs the
score — not cents-vs-independent-truth. Double stops (~1-2% of notes) are reduced
to their top note, the pitch a monophonic tracker is expected to recover; this
makes the quartet a harder test than URMP's single melodic lines.
"""
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "2")

import sys
import gc
import csv
import argparse
import warnings
import numpy as np

warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

import soundfile as sf
from music21 import converter, chord as m21chord, note as m21note

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics, is_note_excluded

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
DATA = os.path.join(ROOT, 'dataset (Haydn anechoic)')
AUDIO = os.path.join(DATA, 'audio')
SCORE_XML = os.path.join(DATA, 'haydn_op76n1.musicxml')

# Research configuration (identical to validate_short_excerpts.py).
CFG = dict(switch_prob=0.005, rms_threshold=0.005, min_frames=2, max_pitch_slope=0.50)
TOGGLES = {'freq_limits': True, 'slope_filter': True, 'duration_filter': True,
           'locked_target': True, 'harmonic_folding': True, 'force_global': False}  # Subsequence
ADAPTIVE_RMS = False  # static gate

LEAD = 0.10

# Movement boundaries in the flattened per-part measure list (from music21:
# measure-number resets at indices 227, 322, 400). Each movement carries one
# tempo, so quarterLength offsets are proportional to real time within an excerpt.
MOV_BOUNDS = [(0, 227), (227, 322), (322, 400), (400, 602)]
MOV_BPM = [144.0, 71.0, 187.0, 144.0]  # notated tempi; absolute scale is absorbed by DTW

# The five recorded excerpts. Selection is by written bar NUMBER where the Zenodo
# description gives bar ranges (Mov1/2/4), and by movement-local measure INDEX for
# the Minuet/Trio split (unambiguous at the double-bar boundary). Ranges inclusive.
EXCERPTS = {
    'Mov1':        dict(mov=0, by='bars', lo=1,  hi=87),   # bars 1..first beat of 88
    'Mov2':        dict(mov=1, by='bars', lo=1,  hi=15),   # bars 1..first beat of 16
    'Mov3_Minuet': dict(mov=2, by='idx',  lo=0,  hi=41),   # Menuetto..Fine
    'Mov3_Trio':   dict(mov=2, by='idx',  lo=42, hi=76),   # Trio..before da capo
    'Mov4':        dict(mov=3, by='bars', lo=94, hi=137),  # bars 94..first note of 138
}
INSTR = {'Violin1': 0, 'Violin2': 1, 'Viola': 2, 'Cello': 3}       # -> part index
INSTR_NAME = {'Violin1': 'Violin', 'Violin2': 'Violin', 'Viola': 'Viola', 'Cello': 'Cello'}


def load_parts():
    """Parse the written score once; return the 4 parts' ordered measure lists."""
    s = converter.parse(SCORE_XML)
    return [list(p.getElementsByClass('Measure')) for p in s.parts]


def score_notes_for(part_measures, exc):
    """Deterministic note list {Start_Time, End_Time, Pitch} for one excerpt of one
    part, from the written score. Chords -> top note. Times from the notated tempo,
    rebased so the excerpt begins at LEAD. Never tuned to the audio."""
    a, b = MOV_BOUNDS[exc['mov']]
    mov = part_measures[a:b]
    if exc['by'] == 'bars':
        chosen = [m for m in mov if m.number is not None and exc['lo'] <= m.number <= exc['hi']]
    else:  # movement-local index
        chosen = mov[exc['lo']:exc['hi'] + 1]

    spm = 60.0 / MOV_BPM[exc['mov']]  # seconds per quarter note
    notes = []
    for m in chosen:
        base = m.offset  # quarterLength offset of the measure within the movement
        for el in m.recurse().notes:
            if isinstance(el, m21chord.Chord):
                midi = max(p.midi for p in el.pitches)  # top note of a double stop
            elif isinstance(el, m21note.Note):
                midi = el.pitch.midi
            else:
                continue
            on = (base + el.offset) * spm
            off = on + max(el.quarterLength, 1e-3) * spm
            notes.append({'Start_Time': on, 'End_Time': off, 'Pitch': int(midi)})
    notes.sort(key=lambda n: n['Start_Time'])
    if not notes:
        return notes, 0.0
    shift = notes[0]['Start_Time'] - LEAD
    for n in notes:
        n['Start_Time'] = max(0.0, n['Start_Time'] - shift)
        n['End_Time'] = n['End_Time'] - shift
    span = notes[-1]['End_Time']
    return notes, span


def normalize_span(sco, target_s):
    """Linearly scale the score timeline so its total span equals the audio
    duration. The OpenScore notated tempo is arbitrary, and a gross global
    tempo mismatch (e.g. an Adagio played 3x slower than notated) would make
    Subsequence DTW match the short score to a sub-window of the long audio
    rather than stretching across it. This uses ONLY the audio's total duration
    (a single scalar) — not its pitch content, onsets or amplitude — so it fixes
    the global alignment without touching relative note spacing or any pitch, and
    cannot bias the deviation measurement. It is the timeline a user's score MIDI
    would already have if authored near the performance tempo."""
    span = sco[-1]['End_Time'] if sco else 0.0
    if span <= 0 or target_s <= 0:
        return sco
    k = target_s / span
    for n in sco:
        n['Start_Time'] *= k
        n['End_Time'] *= k
    return sco


def load_mono(path, channel):
    """Load one channel of the 16-channel anechoic WAV as mono. Anechoic + single
    source => f0 is identical across channels; channel choice is documented, not
    tuned. Default channel is selected once, globally, by RMS energy on Mov2 violin."""
    y, sr = sf.read(path, always_2d=True)
    ch = min(channel, y.shape[1] - 1)
    return np.ascontiguousarray(y[:, ch]), sr


def score_stem(audio_mono, sr, sco, instrument, tmp_wav):
    sf.write(tmp_wav, audio_mono, sr)
    with open(tmp_wav, 'rb') as af:
        y, sr2, f0, vf, rms, vp = extract_pitch_and_rms(
            af, instrument=instrument, switch_prob=CFG['switch_prob'],
            enable_freq_limits=True, pitch_engine='pYIN')
    res = analyze_intonation(y, sr2, f0, vf, rms, rms_threshold=CFG['rms_threshold'],
                             min_frames=CFG['min_frames'], max_pitch_slope=CFG['max_pitch_slope'],
                             toggles={**TOGGLES, 'adaptive_rms': ADAPTIVE_RMS}, voicing_prob=vp)
    fm = res['final_mask']
    ta, ex, wp, eni, ff, ffm, sm, ca = process_dtw_alignment(
        sco, f0, y, sr2, fm, TOGGLES, CFG['max_pitch_slope'])
    metrics = calculate_dtw_metrics(sco, ta, ff, rms, fm, wp, ca, voicing_prob=vp)

    tot = len(sco)
    detected = [m for m in metrics if not np.isnan(m['Deviation_Cents'])]
    included = [m for m in detected if not is_note_excluded(m)]
    devs = np.abs([m['Deviation_Cents'] for m in included]) if included else np.array([])
    return dict(total=tot, detected=len(detected), included=len(included),
                det_yield=len(detected) / tot * 100 if tot else np.nan,
                inc_yield=len(included) / len(detected) * 100 if detected else np.nan,
                n_dev=len(devs), dev_mae=float(np.mean(devs)) if devs.size else np.nan,
                dev_median=float(np.median(devs)) if devs.size else np.nan)


FIELDS = ['stem', 'excerpt', 'instrument', 'part', 'channel', 'score_notes', 'audio_s',
          'score_s', 'total', 'detected', 'included', 'det_yield', 'inc_yield',
          'n_dev', 'dev_mae', 'dev_median']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--channel', type=int, default=0, help='which of the 16 mics to use')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__), 'haydn_crosscorpus_results.csv'))
    args = ap.parse_args()

    parts = load_parts()

    done = set()
    if args.resume and os.path.exists(args.out):
        with open(args.out, newline='') as f:
            done = {r['stem'] for r in csv.DictReader(f)}
    write_header = not (args.resume and os.path.exists(args.out))
    csv_f = open(args.out, 'w' if write_header else 'a', newline='')
    writer = csv.DictWriter(csv_f, fieldnames=FIELDS)
    if write_header:
        writer.writeheader(); csv_f.flush()

    tmp_wav = os.path.join(os.path.dirname(args.out), '_tmp_haydn.wav')
    stems = [(exc, inst) for exc in EXCERPTS for inst in INSTR]
    print(f'{len(stems)} stems, channel {args.channel}, threads={os.environ.get("OMP_NUM_THREADS")}')

    for exc, inst in stems:
        key = f'{exc}_{inst}'
        if key in done:
            print(f'  {key:<28} (skipped)'); continue
        wav = os.path.join(AUDIO, f'{exc}_{inst}_Haydn_StringQuartet_op76_n1.wav')
        if not os.path.exists(wav):
            print(f'  {key:<28} MISSING AUDIO'); continue
        sco, score_s = score_notes_for(parts[INSTR[inst]], EXCERPTS[exc])
        audio_mono, sr = load_mono(wav, args.channel)
        audio_s = len(audio_mono) / sr
        sco = normalize_span(sco, audio_s)  # match template tempo to the take (content-blind)
        r = score_stem(audio_mono, sr, sco, INSTR_NAME[inst], tmp_wav)
        r.update(stem=key, excerpt=exc, instrument=INSTR_NAME[inst], part=inst,
                 channel=args.channel, score_notes=len(sco),
                 audio_s=round(audio_s, 1), score_s=round(score_s, 1))
        writer.writerow({k: r.get(k) for k in FIELDS}); csv_f.flush()
        print(f'  {key:<28} sco={len(sco):>3} audio={audio_s:5.1f}s score={score_s:5.1f}s '
              f'det={r["det_yield"]:5.1f}% inc={r["inc_yield"]:5.1f}% |dev|MAE={r["dev_mae"]:.1f}c', flush=True)
        del audio_mono, sco, r
        gc.collect()

    csv_f.close()
    if os.path.exists(tmp_wav):
        os.remove(tmp_wav)

    with open(args.out, newline='') as f:
        rows = list(csv.DictReader(f))
    print('\n=== Aggregate by instrument (research config) ===')
    for inst in ['Violin', 'Viola', 'Cello']:
        ir = [r for r in rows if r['instrument'] == inst]
        if not ir:
            continue
        dy = np.nanmean([float(r['det_yield']) for r in ir])
        iy = np.nanmean([float(r['inc_yield']) for r in ir if r['inc_yield'] not in ('', 'nan')])
        dm = np.nanmean([float(r['dev_mae']) for r in ir if r['dev_mae'] not in ('', 'nan')])
        print(f'  {inst:<7} n={len(ir):>2}  det={dy:5.1f}%  inc={iy:5.1f}%  |dev|MAE={dm:.1f}c')
    if rows:
        dy = np.nanmean([float(r['det_yield']) for r in rows])
        iy = np.nanmean([float(r['inc_yield']) for r in rows if r['inc_yield'] not in ('', 'nan')])
        print(f'  {"Overall":<7} n={len(rows):>2}  det={dy:5.1f}%  inc={iy:5.1f}%')
    print(f'\n{len(rows)} stems in {args.out}')


if __name__ == '__main__':
    main()
