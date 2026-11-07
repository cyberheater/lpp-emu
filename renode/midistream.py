"""DIN output bytes -> MIDI with every status byte present.

The firmware's DIN outputs use running status (a channel message with the same status as the last one is sent
without it). Tests read the stream one byte at a time; expand() puts the omitted status bytes back so their simple
"status, data, data" parsers keep working. Real-time bytes pass straight through without affecting running status.
"""

_status = {}   # port -> current running status (0 = none)
_count = {}    # port -> data bytes seen since that status


def _data_len(status):
    return 1 if status & 0xF0 in (0xC0, 0xD0) else 2


def expand(port, b):
    """Feed one byte received on `port`; returns the bytes to log (the omitted status first, when needed)."""
    if b >= 0xF8:
        return [b]
    if b >= 0x80:
        _status[port] = b if b < 0xF0 else 0
        _count[port] = 0
        return [b]
    status = _status.get(port, 0)
    if not status:
        return [b]
    out = []
    if _count.get(port, 0) == _data_len(status):
        out.append(status)   # a new message under running status
        _count[port] = 0
    out.append(b)
    _count[port] = _count.get(port, 0) + 1
    return out
