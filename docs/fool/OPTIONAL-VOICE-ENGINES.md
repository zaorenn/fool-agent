# Optional voice engines

The Fool ships the engines it can ship. Some good ones it cannot, because their
model licence forbids redistribution or commercial use. Those are documented
here instead: install them yourself, on your own machine, under their own terms.

Nothing on this page is bundled. Nothing on this page is downloaded unless you
run the commands yourself.

---

## Why IndexTTS2 is not built in

[IndexTTS2](https://github.com/index-tts/index-tts) is, as of this writing, the
best open model for what a companion voice actually needs: it separates
**emotion from timbre**, so one cloned voice can be angry, gentle, excited or
sad without the voice stopping being *hers*. Chatterbox has a single intensity
knob; IndexTTS2 takes an eight-dimensional emotion vector, a separate emotional
reference clip, or a plain text description of the mood.

It is also faster — RTF 0.33 on a 4090 in fp16, against the 0.72 measured for
Chatterbox on a 4070 Ti SUPER.

The blocker is the licence. IndexTTS2 is released under the **bilibili Model Use
License Agreement**, not Apache 2.0 (some third-party summaries say otherwise —
[read the LICENSE](https://github.com/index-tts/index-tts/blob/main/LICENSE)).
Commercial use requires prior written authorisation from bilibili. Shipping it
inside The Fool would put every user of a distributed build in that position
without their knowledge, so it stays out of the box.

If you are using The Fool personally, that restriction may not apply to you.
That is your call to make, not ours to make for you.

---

## Installing IndexTTS2 yourself

**What it costs:** roughly 6–8 GB of VRAM at inference and ~40 GB of disk during
setup. It shares your GPU with whatever language model you are running, so on a
16 GB card plan for one 7–9B model *or* IndexTTS2 comfortably, not both at full
size.

### 1. Create the sidecar environment

Engines live in their own interpreter so their dependencies never touch the
agent's (see `fool/sidecar.py`). Engines are **machine-level**, shared by every
profile (see `fool/machine_assets.py`), so this is done once:

```bash
uv venv --python 3.11 "$FOOL_HOME/sidecars/indextts2"
```

On Windows `$FOOL_HOME` defaults to `%LOCALAPPDATA%\fool`.

### 2. Install the engine

Run these from a directory **outside** this repository. The repo's
`pyproject.toml` carries a `[tool.uv] exclude-newer` pin that uv applies to any
command run inside the tree, and it will refuse to resolve current PyTorch
wheels:

```bash
uv pip install --no-config --python "$FOOL_HOME/sidecars/indextts2/Scripts/python.exe" \
  --index-url https://download.pytorch.org/whl/cu126 torch torchaudio

uv pip install --no-config --python "$FOOL_HOME/sidecars/indextts2/Scripts/python.exe" \
  "indextts @ git+https://github.com/index-tts/index-tts.git"
```

Use `bin/python` instead of `Scripts/python.exe` on macOS and Linux.

Verify CUDA actually reached the sidecar — a CPU build installs happily and then
runs at a tenth of the speed:

```bash
"$FOOL_HOME/sidecars/indextts2/Scripts/python.exe" -c "import torch; print(torch.cuda.is_available())"
```

### 3. Fetch the weights

```bash
huggingface-cli download IndexTeam/IndexTTS-2 --local-dir "$FOOL_HOME/voices/indextts2"
```

### 4. Add the provider plugin

Write it to `$FOOL_HOME/plugins/fool-indextts2/`, **not** into this repository —
user plugins are discovered from there, and keeping it outside the tree is what
keeps the engine out of a distributed build.

Two files. `plugin.yaml`:

```yaml
name: fool-indextts2
version: 1.0.0
kind: backend
provides_tts_providers:
  - indextts2
```

And `__init__.py`, for which `plugins/tts/fool-chatterbox/__init__.py` is the
closest starting point — both clone from a reference clip, so the shape is the
same. Four things change:

- `SIDECAR_NAME` becomes `"indextts2"`,
- the readiness probe imports `indextts`,
- synthesis calls `IndexTTS2.infer(spk_audio_prompt=…, text=…, output_path=…,
  emo_vector=…)`,
- there is no default voice, so a missing `voice_sample` must raise rather than
  fall through — the engine cannot speak without a reference clip and silence
  with no explanation is the worst outcome.

Two details are easy to get wrong quietly. Load the model with
`use_qwen_emo=False` unless you want its text-to-emotion model on the same card;
the delivery tag already carries the mood. And pass the device preference
through **raw** rather than resolving it in the main process — the agent's
environment has no CUDA-enabled torch, so every `cuda.is_available()` asked
there answers `False` and a user who picked CUDA silently runs on CPU.

The emotion vector is eight floats in this order:

```
[happy, angry, sad, afraid, disgusted, melancholic, surprised, calm]
```

(Confirmed against `indextts/infer_v2.py::normalize_emo_vec`, which also caps
the sum at 0.8.) `emo_alpha` (0.0–1.0) scales the whole thing. This is the part
Chatterbox cannot do: the vector changes per utterance while `spk_audio_prompt`
keeps the voice constant.

Per-sentence delivery reaches the plugin as `tts.indextts2.emotion` — one of the
tag names in `fool/voice_emotion.py`, written per request rather than stored.
Map the names you care about to vectors and ignore the rest; an unrecognised
name should send **no** vector at all, so the fallback is the reference clip's
own tone rather than a wrong emotion.

### 5. Select it

```yaml
tts:
  provider: indextts2
  indextts2:
    device: cuda
    voice_sample: ~/.fool/voices/clones/your-voice.wav
    emo_alpha: 0.9
```

Remember that voice settings are **per profile**. Selecting an engine while the
`persona` profile is active writes to that profile's `config.yaml`, not the
main one — and user plugins are read from the *active profile's* directory too,
so the plugin folder has to exist under each profile that uses the engine.

Sentence-by-sentence streaming works for it without any extra step: the check
that decides which engines can be streamed reads the plugin registry as well as
the built-in catalogue, precisely so an engine that cannot ship is not quietly
demoted to the slow whole-reply path.

---

## Engines that are built in

| Engine | Clone | Emotion control | Licence |
|---|---|---|---|
| Piper | no | no | MIT |
| Kokoro | no | no | Apache 2.0 |
| StyleTTS 2 | reference clip | no | MIT |
| Kyutai | no | no | CC-BY |
| F5-TTS | reference clip | no | MIT |
| Chatterbox | reference clip | intensity knob (`exaggeration`) | MIT |
| Qwen3-TTS | no | no | Apache 2.0 |

Chatterbox is the default recommendation for a character voice: it clones from
about ten seconds of clean audio and its `exaggeration` / `cfg_weight` pair can
be varied per call, which is enough to shift delivery with the situation even
though it has no inline emotion tags. Both knobs are editable in
**Settings → Voice**, under the engine.

### A note on laughter

No bundled engine takes an inline `[laughs]` marker — Chatterbox in particular
has no tag parser at all, so writing one puts the literal word into the speech.
Written laughter (`hehe`, `haha`) plus a raised `exaggeration` is the practical
route. Engines with real non-verbal tags exist —
[Orpheus](https://github.com/canopyai/Orpheus-TTS) supports `<laugh>`,
`<chuckle>` and `<sigh>` under Apache 2.0 — but its own README notes the
pretrained model "hasn't been explicitly trained on the zero-shot voice cloning
objective", so it is a poor fit when the voice has to stay *hers*.
