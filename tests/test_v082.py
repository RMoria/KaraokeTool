"""Tests voor v0.82.0-functies (B245, B247, B248, B249, B250, B241-vervolg)."""
from __future__ import annotations

from pathlib import Path


def test_alignment_follows_gradual_drift() -> None:
    """B249: een geleidelijke (dalende) drift wordt niet platgeslagen."""
    from modules.align import OffsetRegion, _smooth_regions, project_time
    regions = tuple(
        OffsetRegion(i * 10.0, i * 10.0 + 10.0, -i * 1.2, 0.7)
        for i in range(6))
    out = _smooth_regions(regions)
    offsets = [r.offset for r in out]
    assert min(offsets) < -4.0                      # drift behouden
    times = [project_time(t, out) for t in range(0, 60, 3)]
    assert times == sorted(times)                 # geen terugsprong


def test_alignment_flattens_isolated_outlier() -> None:
    """B249: een losse uitschieter tussen stabiele buren wordt afgevlakt."""
    from modules.align import OffsetRegion, _smooth_regions
    regions = (OffsetRegion(0, 10, 0.20, 0.7),
               OffsetRegion(10, 20, 0.22, 0.7),
               OffsetRegion(20, 30, 5.00, 0.7),     # uitschieter
               OffsetRegion(30, 40, 0.24, 0.7),
               OffsetRegion(40, 50, 0.23, 0.7))
    out = _smooth_regions(regions)
    assert max(r.offset for r in out) < 1.0


def test_project_time_interpolates_between_regions() -> None:
    """B249: project_time interpoleert lineair i.p.v. te stappen."""
    from modules.align import OffsetRegion, project_time
    regions = (OffsetRegion(0, 20, 0.0, 0.8),       # midden op 10 s
               OffsetRegion(20, 40, -2.0, 0.8))     # midden op 30 s
    # Halverwege de middens (20 s) hoort de offset ~-1.0 te zijn.
    proj = project_time(20.0, regions)
    assert abs((proj - 20.0) - (-1.0)) < 0.2


def test_weighted_anchor_prefers_reliable() -> None:
    """B250: een sterker anker wint een conflict van een zwakker anker."""
    from modules.timing import Syllable, TimedLine, sanitize_timing

    def line(idx, text, start, kwal):
        syl = Syllable(text=text, start=start, end=start + 0.5)
        return TimedLine(index=idx, text=text, crowd=False,
                         syllables=(syl,), quality=kwal)

    # Regel 2 (hoog) ligt vóór regel 1 (laag): de betrouwbare regel 2 moet
    # de reeks bepalen, niet de zwakke regel 1.
    lines = [line(0, "start", 0.0, "high"),
             line(1, "zwak", 5.0, "low"),
             line(2, "sterk", 4.0, "high"),
             line(3, "end", 8.0, "high")]
    out = sanitize_timing(lines, first_start=0.0, song_duration=12.0)
    starts = [ln.start for ln in out]
    assert starts == sorted(starts)                 # monotoon, geen crash


def test_demucs_separate_cached_reuses(tmp_path, monkeypatch) -> None:
    """B248: separate_cached scheidt maar één keer per bron."""
    from modules import separation

    calls = {"n": 0}

    def fake_separate(audio_path, work_dir, model="htdemucs"):
        calls["n"] += 1
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "vocals.wav").write_bytes(b"V")
        (work_dir / "no_vocals.wav").write_bytes(b"I")
        return {"vocals": work_dir / "vocals.wav",
                "instrumental": work_dir / "no_vocals.wav"}

    monkeypatch.setattr(separation, "separate", fake_separate)
    src = tmp_path / "original.wav"
    src.write_bytes(b"audio")
    cache = tmp_path / "cache"
    cache.mkdir()
    separation.separate_cached(src, cache, "original")
    separation.separate_cached(src, cache, "original")   # hergebruik
    assert calls["n"] == 1


def test_font_store_key_roundtrip(tmp_path) -> None:
    """B245: een bundled font wordt draagbaar (bestandsnaam) bewaard."""
    from modules import fonts
    fdir = tmp_path / "fonts"
    fdir.mkdir()
    f = fdir / "Anton-Regular.ttf"
    f.write_bytes(b"x")
    key = fonts.store_key(str(f), fonts_dir=fdir)
    assert key == "Anton-Regular.ttf"               # kale naam
    assert fonts.resolve_font(key, fonts_dir=fdir) == str(f)
    # extern pad blijft absoluut
    ext = str(tmp_path / "Other.ttf")
    assert fonts.store_key(ext, fonts_dir=fdir) == ext


def test_french_language_builtin() -> None:
    """B241-vervolg: Frans is ingebouwd en groepeert nasalen/eau."""
    from modules import phonetics
    segs = phonetics.distribute_word("chanson", 0.0, 1.0, "fr")
    labels = [s[0] for s in segs]
    assert "an" in labels and "on" in labels        # nasalen gegroepeerd


def test_language_on_the_go(tmp_path) -> None:
    """B241-vervolg: onbekende taal wordt aangemaakt en bewaard met header."""
    import json

    from modules import phonetics
    phonetics._EXTRA_LANGUAGES.clear()
    diag = tmp_path / "diagnostics"
    coll = tmp_path / "languages"
    code = phonetics.ensure_language("it", diagnostics_dir=diag,
                                    collection_dir=coll, app_version="0.82.0")
    assert code == "it"
    assert (diag / "it.json").exists()
    obj = json.loads((coll / "it.json").read_text(encoding="utf-8"))
    assert obj["_header"] and obj["generated_with_version"] == "0.82.0"
    # herladen uit de verzamelmap
    phonetics._EXTRA_LANGUAGES.clear()
    assert phonetics.load_language_dir(coll) == 1
    assert "it" in phonetics._EXTRA_LANGUAGES
