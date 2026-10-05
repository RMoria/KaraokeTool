"""One choice instead of a row of model settings (v1.0.15, B606).

The owner's wish: the settings tab had a Whisper model, a way of
separating and a handful of switches for the listening paths, and what
he really chooses is how much time a song may cost. Three stands:

* **High performance** (the default): the best models and every path
  that measured as a gain - it takes long;
* **Normal**: somewhat faster models, fewer paths;
* **Quick and dirty**: the fastest models and only the path tested
  best.

What a stand holds changes only after asking the owner: when a test
(1.5.14, 1.5.15) or the monthly look at new models points at something
better, the question goes to him first - the same rule as for model
updates.

A project keeps the stand it was first made with, like the way it
separates (B591): changing the stand only counts for new projects. A
project that was already worked on before v1.0.15 keeps the settings it
had then, taken over once from the settings of that moment.
"""
from __future__ import annotations

#: The stands, in the order the settings tab shows them.
NAMES = ("high", "normal", "quick")

#: What each stand sets. ``separation`` is a value of
#: ``separation.METHODS``. High performance is large-v3 and every path,
#: whatever an older settings file still says (the settings tab no
#: longer offers those choices, so a model once set to "small" could
#: not be put back). v1.0.28: 1.5.14 measured the Demucs blend (the
#: plain and the careful way joined) a little better than the plain way
#: - most line starts hit, least singing unheard - at about twice the
#: time; the owner chose it for High and Normal, Quick stays plain. And
#: then: where the Roformer environment is installed, the two Roformer
#: models for clean music - the cleanest music, the same timing - with
#: the Demucs blend as the fallback (``separation.FALLBACK``).
PROFILES: dict[str, dict] = {
    "high": {"whisper_model": "large-v3", "separation": "music_clean",
             "chunked_transcription": True, "gap_text": True,
             "forced_alignment": True, "vocal_analysis": True},
    "normal": {"whisper_model": "distil-large-v3",
               "separation": "music_clean",
               "chunked_transcription": False, "gap_text": False,
               "forced_alignment": True, "vocal_analysis": True},
    "quick": {"whisper_model": "small", "separation": "standard",
              "chunked_transcription": False, "gap_text": False,
              "forced_alignment": True, "vocal_analysis": False},
}

#: The fields a project remembers.
FIELDS = ("whisper_model", "separation", "chunked_transcription",
          "gap_text", "forced_alignment", "vocal_analysis")

#: The meta key in ``project.json``.
META = "profile"


def settings_for(name: str) -> dict:
    """The settings of a stand; an unknown one is High performance."""
    name = name if name in PROFILES else "high"
    return dict(PROFILES[name], profile=name)


def legacy_from(config) -> dict:
    """The settings a project made before v1.0.15 was made with: what the
    settings were at the moment it is first opened in this version."""
    advanced = config.advanced
    return {"profile": "legacy",
            "whisper_model": str(config.whisper.model),
            "separation": "standard",
            "chunked_transcription": bool(advanced.chunked_transcription),
            "gap_text": bool(getattr(advanced, "gap_text", True)),
            "forced_alignment": bool(advanced.forced_alignment),
            "vocal_analysis": bool(advanced.vocal_analysis)}


def valid(stored) -> bool:
    """Is this a complete remembered set?"""
    return isinstance(stored, dict) and all(key in stored for key in FIELDS)
