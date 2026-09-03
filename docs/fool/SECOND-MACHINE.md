# Running The Fool on a second, weaker machine

The models live on one computer. Everything else — memory, settings, sessions,
voice — lives on whichever machine you are sitting at. A laptop that could never
load a 9B model can still hold its own conversation, because the only thing it
borrows is the answer.

This is not a remote-desktop arrangement and not a shared account. The laptop is
a full install with its own `config.yaml` and its own memory database. It just
points at another machine for inference.

---

## On the strong machine (the one with the GPU)

**1. Let LM Studio answer the network.** By default its server binds to
localhost, so nothing outside that machine can reach it. In LM Studio →
Developer → Server, turn on **Serve on Local Network**, and note the port (1234
unless you changed it).

**2. Find its address.**

```bash
ipconfig
```

Take the IPv4 address of the adapter you actually use — usually something like
`192.168.1.x`. On macOS or Linux use `ifconfig` or `ip addr`.

**3. Load the model you want to serve** and leave LM Studio running. The Fool on
the other machine will not load models for you; it asks the endpoint for
whatever is there.

**4. Check the firewall once.** Windows will normally have prompted when LM
Studio first bound to the network. If the laptop cannot reach it, this is the
first thing to check — from the laptop:

```bash
curl http://192.168.1.x:1234/v1/models
```

A JSON list means you are done here.

---

## On the laptop

Install The Fool normally, then point it at the other machine. Either in the
first-run screen ("I have an API key" → the local/custom endpoint option) or in
`config.yaml`:

```yaml
model:
  base_url: http://192.168.1.x:1234/v1
  default: <the model id LM Studio reports>
  api_key: lm-studio
```

`api_key` is required by the OpenAI-compatible protocol but LM Studio does not
check it; any non-empty string works.

That is the whole change. The laptop keeps:

- its own memory (`<fool home>/memories/recall.db` — nothing is shared),
- its own settings, profiles and sessions,
- its own voice engines.

---

## Voice on the laptop

Speech recognition and speech synthesis run **locally**, not on the strong
machine — they are separate engines with their own weights, and the LM Studio
endpoint has nothing to do with them.

That is usually fine: Piper synthesises in about 120 ms per sentence on CPU and
Whisper's small models transcribe faster than people talk. Pick from the smaller
end of Settings → Voice on a laptop; Chatterbox and Kyutai want a real GPU and
will be painfully slow without one.

If you want the laptop to sound like the desktop, the honest answer today is to
install the same engine on both. Serving TTS across the network is not something
The Fool does.

---

## What changes because the provider is remote

**Model residency enforcement is skipped.** On a single machine The Fool keeps
exactly one chat model resident, because the language model and the voice
engines share one card and a forgotten second model costs several gigabytes
(measured on the author's 16 GB card: 12.88 GB held, ~3 GB left, and the voice
engines silently falling back to CPU).

That rule cannot apply from here. Unloading runs through the local `lms`
command, so a laptop acting on the desktop's list of loaded models would be
closing models on the wrong computer. The check is loopback-only — an endpoint
on the LAN counts as another machine, even though it is "local" for other
purposes like timeout tuning — so on the laptop this whole mechanism stays out
of the way. Manage residency on the desktop, where the card is.

**Latency is the network plus the model.** On a wired LAN this is not
noticeable; over WiFi with a busy access point it can be. Nothing in The Fool
retries a slow endpoint differently because it is remote.

**The desktop must be awake.** There is no wake-on-LAN, no queueing, and no
fallback to a local model. If LM Studio is not answering, the laptop tells you
the endpoint is unreachable rather than quietly degrading.
