"""
validate_short_excerpts.py
--------------------------
Validates the RESEARCH configuration (Subsequence DTW + static RMS gate) on URMP
string material re-formatted to mimic the study's recording protocol: short
(<= max-length) excerpts cut at rests, trimmed to the notes.

Sources (all from the authoritative full URMP release, which is self-consistent):
  audio  : AuSep_<part>_<inst>_<piece>.wav
  score  : Sco_<piece>.mid, track = <part>   (matches Notes/F0s 1:1)
  truth  : Notes_<part>_<inst>_<piece>.txt    (onset_s, freq_Hz, dur_s) -- audio-aligned

Reports, per excerpt and aggregated by instrument:
  - detection yield  (detected / expected MIDI notes)
  - inclusion yield  (passing is_note_excluded, / detected)
  - pitch-recovery accuracy: signed/abs cents error between the pipeline's
    per-note detected pitch and the URMP ground-truth performed pitch for the
    SAME note (this is the metrological check the annotations make possible).

The score MIDI is the reference the pipeline aligns to (as in the app); the Notes
frequency is an INDEPENDENT ground truth for what was actually played, so
detected-vs-Notes measures whether the pipeline recovers the performed pitch.
"""
import os

# --- Resource restraint (MUST run before numpy / librosa import) ---
# Cap native-library thread pools so the batch stays gentle on low-core / low-RAM
# machines and leaves the desktop responsive. pYIN's heavy lifting is in these
# BLAS/FFT pools; limiting them both lowers CPU pressure and reduces the peak
# memory taken by parallel work buffers. Override by exporting the vars yourself.
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

import librosa
import soundfile as sf

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_parser import parse_midi_with_timing
from src.midi_alignment import process_dtw_alignment, calculate_dtw_metrics, is_note_excluded

URMP_ROOT = os.path.expanduser('~/Downloads/Dataset')
LOCAL_CORPUS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'dataset (Strings only)'))
INST_MAP = {'vn': 'Violin', 'va': 'Viola', 'vc': 'Cello'}

# Research configuration (the intended study settings).
CFG = dict(switch_prob=0.005, rms_threshold=0.005, min_frames=2, max_pitch_slope=0.50)
TOGGLES = {'freq_limits': True, 'slope_filter': True, 'duration_filter': True,
           'locked_target': True, 'harmonic_folding': True, 'force_global': False}  # Subsequence
ADAPTIVE_RMS = False  # static gate

REST_MIN = 0.20        # s; a gap >= this counts as a rest we can cut at
LEAD = 0.10            # s of leading margin kept around each cut


def discover_stems():
    """Return the string stems present in the local 41-stem corpus, mapped to
    authoritative URMP source paths. Keeps continuity with Appendix A's selection
    while drawing clean MIDI/annotations from the full release."""
    stems = []
    for root, _dirs, files in os.walk(LOCAL_CORPUS):
        for fn in files:
            if fn.startswith('AuSep_') and fn.endswith('.wav'):
                key = fn[len('AuSep_'):-len('.wav')]         # e.g. 5_vc_44_K515
                parts = key.split('_')
                part_idx, inst = int(parts[0]), parts[1]
                if inst not in INST_MAP:
                    continue
                piece = '_'.join(parts[2:])                  # 44_K515
                # locate the piece folder in the URMP release
                piece_dir = None
                for d in os.listdir(URMP_ROOT):
                    if d.startswith(piece + '_') or d == piece:
                        piece_dir = os.path.join(URMP_ROOT, d)
                        break
                if not piece_dir:
                    continue
                sco = [f for f in os.listdir(piece_dir) if f.startswith('Sco_') and f.endswith('.mid')]
                notes = os.path.join(piece_dir, f'Notes_{key}.txt')
                audio = os.path.join(piece_dir, f'AuSep_{key}.wav')
                if sco and os.path.exists(notes) and os.path.exists(audio):
                    stems.append(dict(key=key, part_idx=part_idx, inst=inst,
                                      instrument=INST_MAP[inst], piece=piece,
                                      audio=audio, sco=os.path.join(piece_dir, sco[0]), notes=notes))
    return sorted(stems, key=lambda s: s['key'])


def load_stem(s):
    with open(s['sco'], 'rb') as f:
        sco_notes = parse_midi_with_timing(f, target_track=s['part_idx'])
    gt = np.loadtxt(s['notes'])
    if gt.ndim == 1:
        gt = gt.reshape(1, -1)
    return sco_notes, gt  # gt columns: onset, freq_hz, dur


def align_sco_gt(sco_notes, gt):
    """Align the score note sequence to the ground-truth transcription by pitch,
    via DTW, so the two can differ by a few inserted/dropped notes. Returns
    gt_freq_by_sco[i] = ground-truth performed frequency (Hz) for score note i
    (np.nan if unmatched), plus gt2sco mapping each gt index to a score index."""
    sp = np.array([n['Pitch'] for n in sco_notes], dtype=float)
    gp = librosa.hz_to_midi(gt[:, 1])
    _D, wp = librosa.sequence.dtw(X=sp[None, :], Y=gp[None, :], metric='euclidean', subseq=False)
    wp = wp[::-1]  # ascending order; columns (sco_idx, gt_idx)
    from collections import defaultdict
    s2g, g2s = defaultdict(list), defaultdict(list)
    for si, gi in wp:
        s2g[int(si)].append(int(gi)); g2s[int(gi)].append(int(si))
    gt_freq_by_sco = np.full(len(sco_notes), np.nan)
    for si, gis in s2g.items():
        gi = int(np.median(gis))
        # accept the match only if pitches agree within a semitone (else it's a gap)
        if abs(sp[si] - gp[gi]) <= 1.0:
            gt_freq_by_sco[si] = gt[gi, 1]
    gt2sco = {gi: int(np.median(sis)) for gi, sis in g2s.items()}
    return gt_freq_by_sco, gt2sco


def choose_cut_indices(gt, audio_dur, max_len):
    """Pick end-of-segment note indices (in GT/audio order) so each excerpt is
    <= max_len seconds. Greedy: cut at the latest rest that keeps the running
    segment within max_len. Falls back to the latest note boundary if a stretch
    has no rest within max_len."""
    onset, dur = gt[:, 0], gt[:, 2]
    end = onset + dur
    n = len(gt)
    if end[-1] - onset[0] <= max_len:
        return []  # single segment, no cut
    gaps = onset[1:] - end[:-1]  # gap after note k (k = 0..n-2)

    cuts = []
    seg_start_t = onset[0]
    last_rest = None
    for k in range(n - 1):
        if gaps[k] >= REST_MIN:
            last_rest = k
        # would including note k+1 overrun the segment?
        if end[k + 1] - seg_start_t > max_len:
            cut = last_rest if (last_rest is not None and last_rest > (cuts[-1] if cuts else -1)) else k
            cuts.append(cut)
            seg_start_t = onset[cut + 1]
            last_rest = None
    return cuts


def segment_stem(y, sr, sco_notes, gt, gt_freq_by_sco, gt2sco, max_len):
    """Yield (audio_slice, sco_slice_rebased, gt_freq_slice, (sa, sb)) per excerpt.
    Cuts are chosen in the GT (audio) domain and mapped to score indices via the
    pitch alignment, so score/GT note-count differences do not misalign the cuts."""
    cuts_gt = choose_cut_indices(gt, len(y) / sr, max_len)
    onset = gt[:, 0]
    end = gt[:, 0] + gt[:, 2]
    gt_keys = np.array(sorted(gt2sco.keys()))

    def map_gt_to_sco(kg):
        if kg in gt2sco:
            return gt2sco[kg]
        return gt2sco[int(gt_keys[np.argmin(np.abs(gt_keys - kg))])]

    cuts_sco = [map_gt_to_sco(kg) for kg in cuts_gt]
    gt_bounds = [-1] + cuts_gt + [len(gt) - 1]
    sco_bounds = [-1] + cuts_sco + [len(sco_notes) - 1]

    for (ga, gb), (sa, sb) in zip(
            zip([b + 1 for b in gt_bounds[:-1]], gt_bounds[1:]),
            zip([b + 1 for b in sco_bounds[:-1]], sco_bounds[1:])):
        if gb < ga or sb < sa:
            continue
        a_start = max(0.0, onset[ga] - LEAD)
        a_end = min(len(y) / sr, end[gb] + LEAD)
        audio_slice = y[int(a_start * sr):int(a_end * sr)]
        shift = sco_notes[sa]['Start_Time'] - LEAD
        sco_slice = [{'Start_Time': max(0.0, n['Start_Time'] - shift),
                      'End_Time': n['End_Time'] - shift, 'Pitch': n['Pitch']}
                     for n in sco_notes[sa:sb + 1]]
        gt_freq_slice = gt_freq_by_sco[sa:sb + 1]
        yield audio_slice, sco_slice, gt_freq_slice, (sa, sb)


def score_excerpt(audio_slice, sr, sco_slice, gt_freq_slice, instrument, tmp_wav):
    sf.write(tmp_wav, audio_slice, sr)
    with open(tmp_wav, 'rb') as af:
        y, sr2, f0, vf, rms, vp = extract_pitch_and_rms(
            af, instrument=instrument, switch_prob=CFG['switch_prob'], enable_freq_limits=True, pitch_engine='pYIN')
    res = analyze_intonation(y, sr2, f0, vf, rms, rms_threshold=CFG['rms_threshold'],
                             min_frames=CFG['min_frames'], max_pitch_slope=CFG['max_pitch_slope'],
                             toggles={**TOGGLES, 'adaptive_rms': ADAPTIVE_RMS}, voicing_prob=vp)
    fm = res['final_mask']
    ta, ex, wp, eni, ff, ffm, sm, ca = process_dtw_alignment(
        sco_slice, f0, y, sr2, fm, TOGGLES, CFG['max_pitch_slope'])
    metrics = calculate_dtw_metrics(sco_slice, ta, ff, rms, fm, wp, ca, voicing_prob=vp)

    tot = len(sco_slice)
    detected = [m for m in metrics if not np.isnan(m['Deviation_Cents'])]
    included = [m for m in detected if not is_note_excluded(m)]

    # pitch-recovery accuracy vs ground truth: detected pitch of score note i
    # compared to the aligned ground-truth performed pitch for that note.
    acc_cents = []
    for m in detected:
        i = m['Note_Index'] - 1  # local score-slice index
        if 0 <= i < len(gt_freq_slice):
            gf = gt_freq_slice[i]
            if not np.isnan(gf) and gf > 0 and m['Median_Detected_Pitch_Hz'] > 0:
                acc_cents.append(1200.0 * np.log2(m['Median_Detected_Pitch_Hz'] / gf))
    acc = np.abs(acc_cents) if acc_cents else np.array([])
    return dict(total=tot, detected=len(detected), included=len(included),
                det_yield=len(detected) / tot * 100 if tot else np.nan,
                inc_yield=len(included) / len(detected) * 100 if detected else np.nan,
                n_acc=len(acc), acc_mae=float(np.mean(acc)) if acc.size else np.nan,
                acc_median=float(np.median(acc)) if acc.size else np.nan,
                acc_p90=float(np.percentile(acc, 90)) if acc.size else np.nan)


FIELDS = ['stem', 'instrument', 'notes_a', 'notes_b', 'dur_s', 'total', 'detected',
          'included', 'det_yield', 'inc_yield', 'n_acc', 'acc_mae', 'acc_median', 'acc_p90']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-len', type=float, default=120.0)
    ap.add_argument('--limit', type=int, default=None, help='process only first N stems (smoke test)')
    ap.add_argument('--resume', action='store_true',
                    help='skip stems already present in --out (survives an OOM restart)')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__), 'short_excerpt_results.csv'))
    args = ap.parse_args()

    stems = discover_stems()
    if args.limit:
        stems = stems[:args.limit]

    # Resume: read stems already written so an interrupted run can be re-launched.
    done = set()
    if args.resume and os.path.exists(args.out):
        with open(args.out, newline='') as f:
            done = {row['stem'] for row in csv.DictReader(f)}
        print(f'Resume: {len(done)} stems already recorded, will be skipped.')
    write_header = not (args.resume and os.path.exists(args.out))
    csv_f = open(args.out, 'w' if write_header else 'a', newline='')
    writer = csv.DictWriter(csv_f, fieldnames=FIELDS)
    if write_header:
        writer.writeheader(); csv_f.flush()

    print(f'Discovered {len(stems)} string stems (threads capped at '
          f'{os.environ.get("OMP_NUM_THREADS")}).')

    tmp_wav = os.path.join(os.path.dirname(args.out), '_tmp_excerpt.wav')
    for si, s in enumerate(stems, 1):
        if s['key'] in done:
            print(f'[{si}/{len(stems)}] {s["key"]:<24} (skipped, already done)')
            continue
        sco_notes, gt = load_stem(s)
        gt_freq_by_sco, gt2sco = align_sco_gt(sco_notes, gt)
        n_matched = int(np.sum(~np.isnan(gt_freq_by_sco)))
        print(f'[{si}/{len(stems)}] {s["key"]:<24} Sco={len(sco_notes)} GT={len(gt)} '
              f'matched={n_matched}/{len(sco_notes)}', flush=True)
        y, sr = librosa.load(s['audio'], sr=None)
        for audio_slice, sco_slice, gt_freq_slice, (a, b) in segment_stem(
                y, sr, sco_notes, gt, gt_freq_by_sco, gt2sco, args.max_len):
            r = score_excerpt(audio_slice, sr, sco_slice, gt_freq_slice, s['instrument'], tmp_wav)
            r.update(stem=s['key'], instrument=s['instrument'], notes_a=a, notes_b=b,
                     dur_s=round(len(audio_slice) / sr, 1))
            writer.writerow({k: r.get(k) for k in FIELDS}); csv_f.flush()  # persist per excerpt
            print(f'      seg[{a:>3}-{b:>3}] {r["dur_s"]:>5}s  det={r["det_yield"]:5.1f}%  '
                  f'inc={r["inc_yield"]:5.1f}%  |acc|MAE={r["acc_mae"]:.1f}c (n={r["n_acc"]})', flush=True)
            del audio_slice, sco_slice, gt_freq_slice, r
        del y, sco_notes, gt, gt_freq_by_sco, gt2sco
        gc.collect()  # release the stem's audio before loading the next

    csv_f.close()
    if os.path.exists(tmp_wav):
        os.remove(tmp_wav)

    # Aggregate from the CSV (works whether or not this run resumed).
    with open(args.out, newline='') as f:
        rows = list(csv.DictReader(f))
    print('\n=== Aggregate by instrument ===')
    for inst in ['Violin', 'Viola', 'Cello']:
        ir = [r for r in rows if r['instrument'] == inst]
        if not ir:
            continue
        dy = np.nanmean([float(r['det_yield']) for r in ir])
        iy = np.nanmean([float(r['inc_yield']) for r in ir])
        am = np.nanmean([float(r['acc_mae']) for r in ir if r['acc_mae'] not in ('', 'nan')])
        print(f'  {inst:<7} n_excerpts={len(ir):>3}  det={dy:5.1f}%  inc={iy:5.1f}%  |acc|MAE={am:.1f}c')
    print(f'\nTotal {len(rows)} excerpt rows in {args.out}')


if __name__ == '__main__':
    main()
