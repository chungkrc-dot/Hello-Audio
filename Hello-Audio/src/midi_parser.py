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

def parse_midi(audio_file):
    """
    Parses a MIDI file and returns a chronological array of detected note names.
    This works by extracting Note-On events (with velocity > 0) sequentially.
    """
    audio_file.seek(0)
    data = audio_file.read()
    
    idx = 0
    if data[idx:idx+4] != b'MThd':
        return []
    
    idx += 4
    header_len = int.from_bytes(data[idx:idx+4], 'big')
    idx += 4
    fmt = int.from_bytes(data[idx:idx+2], 'big')
    ntracks = int.from_bytes(data[idx+2:idx+4], 'big')
    idx += header_len
    
    # We will gather all note events with their absolute timing to sort them chronologically
    # In MIDI, delta times are relative to the previous event in the same track.
    all_notes = []
    
    for _ in range(ntracks):
        if idx >= len(data): break
        # Skip unknown chunks until we find MTrk
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
            # Delta time
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
                    # Invalid MIDI state, skip byte
                    idx += 1
                    continue
                    
            if status == 0xFF:
                # Meta event
                meta_type = data[idx]
                idx += 1
                meta_len, idx = read_vlq(data, idx)
                idx += meta_len
            elif status in (0xF0, 0xF7):
                # SysEx
                sysex_len, idx = read_vlq(data, idx)
                idx += sysex_len
            else:
                event_type = status >> 4
                if event_type in (0x8, 0x9, 0xA, 0xB, 0xE):
                    param1 = data[idx]
                    param2 = data[idx+1]
                    idx += 2
                    
                    if event_type == 0x9 and param2 > 0:
                        # Note On with velocity > 0
                        all_notes.append((absolute_time, param1))
                        
                elif event_type in (0xC, 0xD):
                    param1 = data[idx]
                    idx += 1
                    
    # Sort notes by chronological absolute time across all tracks
    all_notes.sort(key=lambda x: x[0])
    
    note_sequence = [note[1] for note in all_notes]
    
    return [librosa.midi_to_note(n) for n in note_sequence]

def parse_midi_with_timing(audio_file):
    """
    Parses a MIDI file and returns a list of dictionaries containing
    'Start_Time', 'End_Time', and 'Pitch' for each note.
    Timing is converted from ticks to seconds using a default 120 BPM tempo.
    """
    audio_file.seek(0)
    data = audio_file.read()
    
    idx = 0
    if data[idx:idx+4] != b'MThd':
        return []
    
    idx += 4
    header_len = int.from_bytes(data[idx:idx+4], 'big')
    idx += 4
    fmt = int.from_bytes(data[idx:idx+2], 'big')
    ntracks = int.from_bytes(data[idx+2:idx+4], 'big')
    tickdiv = int.from_bytes(data[idx+4:idx+6], 'big')
    idx += header_len
    
    # Calculate seconds per tick assuming 120 BPM (500,000 microseconds per quarter note)
    ticks_per_quarter = tickdiv if tickdiv > 0 else 480
    seconds_per_tick = 500000 / (ticks_per_quarter * 1000000)
    
    midi_notes = []
    
    for _ in range(ntracks):
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
        
        # Keep track of active notes to find their end times
        active_notes = {}
        
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
                
                # If Set Tempo (0x51), we could dynamically update seconds_per_tick here
                if meta_type == 0x51 and meta_len == 3:
                    tempo_usec = int.from_bytes(data[idx:idx+3], 'big')
                    seconds_per_tick = tempo_usec / (ticks_per_quarter * 1000000)
                    
                idx += meta_len
            elif status in (0xF0, 0xF7):
                sysex_len, idx = read_vlq(data, idx)
                idx += sysex_len
            else:
                event_type = status >> 4
                if event_type in (0x8, 0x9, 0xA, 0xB, 0xE):
                    param1 = data[idx]
                    param2 = data[idx+1]
                    idx += 2
                    
                    if event_type == 0x9 and param2 > 0:
                        # Note On
                        if param1 not in active_notes:
                            active_notes[param1] = absolute_time * seconds_per_tick
                    elif event_type == 0x8 or (event_type == 0x9 and param2 == 0):
                        # Note Off
                        if param1 in active_notes:
                            start_time = active_notes.pop(param1)
                            end_time = absolute_time * seconds_per_tick
                            midi_notes.append({
                                'Start_Time': start_time,
                                'End_Time': end_time,
                                'Pitch': param1
                            })
                            
                elif event_type in (0xC, 0xD):
                    idx += 1
                    
    # Sort chronologically
    midi_notes.sort(key=lambda x: x['Start_Time'])
    return midi_notes
