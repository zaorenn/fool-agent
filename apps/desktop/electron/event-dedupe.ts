// Cross-window de-dupe for one-shot side-effects (OS notifications, the turn-end
// sound, spoken replies). Every desktop window is its own renderer process, so N
// open windows each independently react to the same backend event. The main
// process is the one place they all share and it handles IPC serially, so it's
// the race-free owner: the first window to claim a key within the interval wins;
// peers see it's taken and stay quiet. Pure + injectable clock, so it's
// unit-testable without Electron.

const DEDUPE_INTERVAL_MS = 1000

// Returns true when `key` was already claimed within the interval (caller drops
// this one). Self-evicting: stale keys are pruned on every call, so the map
// can't grow unbounded.
export function createEventDeduper(intervalMs = DEDUPE_INTERVAL_MS) {
  const lastSeenAt = new Map<string, number>()
  const holdFor = new Map<string, number>()

  // Per-claim hold, because one interval cannot serve both callers.
  //
  // Measured: a spoken reply was claimed TWICE and the user heard the same
  // sentences again. The notch claims at the first token; the composer claims
  // only when the reply COMPLETES — many seconds later. With a single 1s
  // interval the first claim had long expired, so the second one won too and
  // both surfaces spoke.
  //
  // The 1s default stays right for what it was built for (a notification or
  // the turn-end sound arriving in N windows at once). Speech needs a claim
  // that lasts as long as the turn it covers, so the caller says how long.
  return function isDuplicate(key: string, now = Date.now(), ttlMs?: number): boolean {
    for (const [k, at] of lastSeenAt) {
      if (now - at >= (holdFor.get(k) ?? intervalMs)) {
        lastSeenAt.delete(k)
        holdFor.delete(k)
      }
    }

    if (lastSeenAt.has(key)) {
      return true
    }

    lastSeenAt.set(key, now)

    if (typeof ttlMs === 'number' && ttlMs > 0) {
      holdFor.set(key, ttlMs)
    } else {
      holdFor.delete(key)
    }

    return false
  }
}
