"""KaraokeTool modules.

Building karaoke videos for carnival parodies. A song is split into an
instrumental and a vocal track, the vocal is transcribed with Whisper,
the official lyrics are timed against that transcription word by word,
and a second text can be laid over exactly the same timing. Words left
behind in a bought karaoke track can be damped instead of removed.
"""

__version__ = "1.0.11"
