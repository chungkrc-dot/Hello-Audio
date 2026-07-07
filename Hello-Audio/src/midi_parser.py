import librosa

def read_vlq(data, idx):
    value = 0
    while True:
        if idx >= len(data):
            break
        byte = data[idx]
        idx += 1
        value = (value << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            break
    return value, idx

def _iter_midi_events(audio_file, target_track=None):
    """
    Core generator that parses MIDI bytes and yields structured events.
    Yields: (trk_idx, event_type, absolute_time_ticks, param1, param2, meta_type, meta_data)
    """
    audio_file.seek(0)
    data = audio_file.read()
    
    idx = 0
    if data[idx:idx+4] != b'MThd':
        return
        
    idx += 4
    header_len = int.from_bytes(data[idx:idx+4], 'big')
    idx += 4
    fmt = int.from_bytes(data[idx:idx+2], 'big')
    ntracks = int.from_bytes(data[idx+2:idx+4], 'big')
    tickdiv = int.from_bytes(data[idx+4:idx+6], 'big')
    idx += header_len
    
    yield ('header', fmt, ntracks, tickdiv, None, None, None)
    
    for trk_idx in range(ntracks):
        if idx >= len(data): break
        while idx < len(data) and data[idx:idx+4] != b'MTrk':
            idx += 1
            
        if idx >= len(data): break
        
        idx += 4
        trk_len = int.from_bytes(data[idx:idx+4], 'big')
        idx += 4
        end_idx = idx + trk_len
        
        running_status = None
        absolute_time = 0
        
        while idx < end_idx:
            delta, idx = read_vlq(data, idx)
            absolute_time += delta
            
            if idx >= end_idx: break
            
            event_byte = data[idx]
            if event_byte >= 0x80:
                status = event_byte
                idx += 1
                if status < 0xF0:
                    running_status = status
            else:
                status = running_status
                if status is None:
                    idx += 1
                    continue
                    
            if status == 0xFF:
                meta_type = data[idx]
                idx += 1
                meta_len, idx = read_vlq(data, idx)
                meta_data = data[idx:idx+meta_len]
                idx += meta_len
                yield (trk_idx, 'meta', absolute_time, None, None, meta_type, meta_data)
            elif status in (0xF0, 0xF7):
                sysex_len, idx = read_vlq(data, idx)
                idx += sysex_len
            else:
                event_type = status >> 4
                if event_type in (0x8, 0x9, 0xA, 0xB, 0xE):
                    param1 = data[idx]
                    param2 = data[idx+1]
                    idx += 2
                    if target_track is None or trk_idx == target_track:
                        yield (trk_idx, event_type, absolute_time, param1, param2, None, None)
                elif event_type in (0xC, 0xD):
                    idx += 1

def parse_midi(audio_file, target_track=None):
    all_notes = []
    for trk_idx, event_type, abs_time, p1, p2, meta_type, meta_data in _iter_midi_events(audio_file, target_track):
        if event_type == 0x9 and p2 > 0:
            all_notes.append((abs_time, p1))
    
    all_notes.sort(key=lambda x: x[0])
    return [librosa.midi_to_note(n[1]) for n in all_notes]

def parse_midi_with_timing(audio_file, target_track=None):
    generator = _iter_midi_events(audio_file, target_track)
    try:
        header = next(generator)
        if header[0] != 'header':
            return []
        tickdiv = header[3]
    except StopIteration:
        return []
        
    ticks_per_quarter = tickdiv if tickdiv > 0 else 480
    seconds_per_tick = 500000 / (ticks_per_quarter * 1000000)
    
    midi_notes = []
    active_notes = {}
    
    for trk_idx, event_type, abs_time, p1, p2, meta_type, meta_data in generator:
        if event_type == 'meta' and meta_type == 0x51 and len(meta_data) == 3:
            tempo_usec = int.from_bytes(meta_data, 'big')
            seconds_per_tick = tempo_usec / (ticks_per_quarter * 1000000)
        elif event_type == 0x9 and p2 > 0:
            if p1 not in active_notes:
                active_notes[p1] = abs_time * seconds_per_tick
        elif event_type == 0x8 or (event_type == 0x9 and p2 == 0):
            if p1 in active_notes:
                start_time = active_notes.pop(p1)
                end_time = abs_time * seconds_per_tick
                midi_notes.append({
                    'Start_Time': start_time,
                    'End_Time': end_time,
                    'Pitch': p1
                })
                
    midi_notes.sort(key=lambda x: x['Start_Time'])
    return midi_notes

def get_midi_tracks(audio_file):
    track_info = {}
    for trk_idx, event_type, abs_time, p1, p2, meta_type, meta_data in _iter_midi_events(audio_file):
        if event_type == 0x9 and p2 > 0:
            track_info[trk_idx] = track_info.get(trk_idx, 0) + 1
            
    return {trk_idx: f"Track {trk_idx} ({count} notes)" for trk_idx, count in track_info.items()}

def get_midi_tempo(midi_file_path):
    with open(midi_file_path, 'rb') as f:
        for trk_idx, event_type, abs_time, p1, p2, meta_type, meta_data in _iter_midi_events(f):
            if event_type == 'meta' and meta_type == 0x51 and len(meta_data) == 3:
                tempo_usec = int.from_bytes(meta_data, 'big')
                return 60000000 / tempo_usec
    return 120.0
