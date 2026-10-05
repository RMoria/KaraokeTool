"""What an NVIDIA card is good for on this computer (v1.0.20).

The helpers found this out for themselves since v1.0.18; the program
itself used to take the card the moment Whisper's library counted one,
without the libraries Whisper needs on it and without asking whether
the card can do half precision - on a computer with an NVIDIA card the
first transcription could stop with a missing ``cublas64_12.dll``.

Now the launcher installs the versions that work on a card when it sees
one, and asks this module once, in a process of its own, what the card
really does (``python -m modules.cuda --write <config>/cuda.json``): a
real sum in PyTorch (Demucs and Roformer) and a second of silence
through Whisper on the card, with the fastest compute type the card does
well. The program reads that file at its start (:func:`use_card_file`)
and takes the card only for what worked. Without a file, or without a
card, everything stays on the processor. And should Whisper still fail
on the card while it runs, :mod:`modules.whisper` goes over to the
processor for the rest of the session.

v1.0.23 (B641): a card with less memory than :data:`MIN_CARD_GB` is not
used at all. Pav's GTX 1650 has 4 GB: three Roformer models on it ran
for nine hours and, a night later, so hot that the laptop switched
itself off. The test still says what the card is and what it did; it is
only not taken - on a helper the owner can still say otherwise per
computer (``lanes.txt``, see ``tools/helper.py``).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

#: Below this much card memory the card is not used (v1.0.23).
MIN_CARD_GB = 6.0

#: Of the compute types the card offers, the first one in this order.
_COMPUTE_ORDER = ("float16", "int8_float16", "int8", "float32")

#: What the card test found, as read at the start: ``None`` is "no card
#: to use".
_CARD: dict | None = None
#: Whether a card file was read at all. A helper reads none: its lanes
#: decide about the card themselves (``tools/helper.py``).
_READ = False


def choose_compute(supported) -> str:
    """The compute type Whisper uses on the card: the fastest the card
    does well. An older card has no fast half precision."""
    offered = set(supported or ())
    for kind in _COMPUTE_ORDER:
        if kind in offered:
            return kind
    return "float32"


def add_cuda_libraries() -> None:
    """Whisper's CUDA libraries come as pip packages (nvidia-cublas,
    nvidia-cudnn) and PyTorch brings its own; Windows looks for them on
    the DLL path, so both are put there."""
    import site

    folders = []
    try:
        bases = site.getsitepackages()
    except AttributeError:          # an old virtualenv
        bases = []
    for base in bases:
        base = Path(base)
        folders += sorted(base.glob("nvidia/*/bin"))
        folders += [base / "torch" / "lib"]
    for folder in folders:
        if folder.is_dir():
            try:
                os.add_dll_directory(str(folder))
            except (AttributeError, OSError):
                pass
            os.environ["PATH"] = str(folder) + os.pathsep + \
                os.environ.get("PATH", "")


def gpu_check() -> tuple[bool, str]:
    """Can this computer compute on the card with PyTorch? ``(ok, what)``:
    the card's name, or why not. A real sum, because a card that is there
    can still be too old for the PyTorch installed."""
    add_cuda_libraries()
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        return False, f"torch: {exc}"[:200]
    try:
        if not torch.cuda.is_available():
            return False, "torch.cuda.is_available() = False"
        name = torch.cuda.get_device_name(0)
        (torch.ones(8, device="cuda") * 2).sum().item()
    except Exception as exc:  # noqa: BLE001 - an old card fails here
        return False, f"{type(exc).__name__}: {exc}"[:200]
    return True, name


def whisper_on_card() -> tuple[str, str]:
    """``(device, compute type)`` for Whisper, found out by really loading
    a small model on the card and listening to a second of silence: a
    card ctranslate2 counts can still lack the CUDA libraries it needs,
    and then every transcription would fail at its end."""
    add_cuda_libraries()
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() <= 0:
            return "cpu", "int8"
        compute = choose_compute(
            ctranslate2.get_supported_compute_types("cuda"))
        import numpy as np
        from faster_whisper import WhisperModel

        model = WhisperModel("tiny", device="cuda", compute_type=compute)
        segments, _info = model.transcribe(
            np.zeros(16000, dtype=np.float32), language="nl")
        list(segments)
        return "cuda", compute
    except Exception:  # noqa: BLE001 - then Whisper listens on the processor
        return "cpu", "int8"


def card_memory_gb() -> float | None:
    """How much memory the card has, in GB; ``None`` when not known."""
    try:
        import torch

        if torch.cuda.is_available():
            return round(torch.cuda.get_device_properties(0).total_memory
                         / 2 ** 30, 1)
    except Exception:  # noqa: BLE001 - then it is not known
        return None
    return None


def _driver_memory_gb() -> float | None:
    """The card's memory as its driver says it (when PyTorch cannot)."""
    import subprocess

    from . import proc

    try:
        done = proc.run(["nvidia-smi", "--query-gpu=memory.total",
                         "--format=csv,noheader,nounits"], check=False,
                        timeout=30)
        return round(float(done.stdout.split()[0]) / 1024.0, 1)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def big_enough(found: dict) -> bool:
    """Is the card of a test's result big enough to be used (v1.0.23)?
    Unknown memory counts as big enough: the test said the card works."""
    memory = found.get("memory_gb")
    return memory is None or float(memory) >= MIN_CARD_GB


def probe(whisper_too: bool = True) -> dict:
    """The whole card test. ``torch``: PyTorch computes on the card (the
    separations); ``device``/``compute``: where Whisper listens;
    ``memory_gb``: how much memory the card has (v1.0.23)."""
    gpu_ok, what = gpu_check()
    device, compute = (whisper_on_card() if whisper_too
                       else ("cpu", "int8"))
    return {"gpu_ok": gpu_ok or device == "cuda", "torch": gpu_ok,
            "card": what, "device": device, "compute": compute,
            "memory_gb": (card_memory_gb() if gpu_ok else None)
            or (_driver_memory_gb() if device == "cuda" else None)}


def for_the_program(found: dict) -> dict:
    """What the program itself may use of a test's result: nothing of a
    card that is too small (v1.0.23), and it says why."""
    if not found.get("gpu_ok") or big_enough(found):
        return dict(found)
    return dict(found, gpu_ok=False, torch=False, device="cpu",
                compute="int8", too_small=True)


def use_card_file(path: Path) -> dict | None:
    """Read what the card test found (at the program's start). Returns it
    when there is a card to use, else ``None``."""
    global _CARD, _READ
    _READ = True
    try:
        found = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        found = None
    _CARD = found if isinstance(found, dict) and found.get("gpu_ok") \
        else None
    if _CARD is not None:
        add_cuda_libraries()
    return _CARD


def whisper_device() -> tuple[str, str]:
    """Where Whisper listens when its setting is ``auto``."""
    if _CARD is not None and _CARD.get("device") == "cuda":
        return "cuda", str(_CARD.get("compute") or "float16")
    return "cpu", "int8"


def torch_on_card() -> bool:
    """May the separations (Demucs, Roformer) use the card?"""
    return bool(_CARD is not None and _CARD.get("torch"))


def processor_only_env(env: dict | None = None) -> dict:
    """An environment for a separation that must stay off the card: a
    card PyTorch counts but cannot use would stop it."""
    env = dict(os.environ if env is None else env)
    if _READ and not torch_on_card():
        env["CUDA_VISIBLE_DEVICES"] = "-1"
    return env


def torch_failed() -> None:
    """A separation failed on the card (out of memory, say): the rest of
    this session separates on the processor."""
    global _CARD
    if _CARD is not None:
        _CARD = dict(_CARD, torch=False)


def main(argv: list[str]) -> int:
    """``--write <file>``: run the card test and write what it found;
    ``--none <file>``: write that there is no card (no NVIDIA driver)."""
    if len(argv) != 2 or argv[0] not in ("--write", "--none"):
        print("usage: python -m modules.cuda --write|--none <cuda.json>")
        return 2
    found = for_the_program(probe()) if argv[0] == "--write" else {
        "gpu_ok": False, "torch": False, "card": "-", "device": "cpu",
        "compute": "int8"}
    Path(argv[1]).parent.mkdir(parents=True, exist_ok=True)
    Path(argv[1]).write_text(json.dumps(found, indent=1), encoding="utf-8")
    print(json.dumps(found), flush=True)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
