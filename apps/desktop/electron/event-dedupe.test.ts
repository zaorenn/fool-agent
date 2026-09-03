import assert from 'node:assert/strict'

import { test } from 'vitest'

import { createEventDeduper } from './event-dedupe'

test('collapses the same key inside the window (two windows, one event)', () => {
  const isDup = createEventDeduper(1000)

  assert.equal(isDup('input:s1', 0), false, 'first window claims')
  assert.equal(isDup('input:s1', 5), true, 'second window is deduped')
})

test('distinct keys are independent', () => {
  const isDup = createEventDeduper(1000)

  assert.equal(isDup('input:s1', 0), false)
  assert.equal(isDup('approval:s1', 0), false, 'different kind')
  assert.equal(isDup('input:s2', 0), false, 'different session')
})

test('re-fires once the window elapses', () => {
  const isDup = createEventDeduper(1000)

  assert.equal(isDup('turnDone:s1', 0), false)
  assert.equal(isDup('turnDone:s1', 999), true, 'still within window')
  assert.equal(isDup('turnDone:s1', 1000), false, 'window elapsed → fires again')
})

test('prunes stale keys so the map cannot grow unbounded', () => {
  const isDup = createEventDeduper(1000)

  for (let i = 0; i < 100; i += 1) {
    // Each far-apart key is pruned before the next, so none linger as duplicates.
    assert.equal(isDup(`turnDone:s${i}`, i * 2000), false)
  }
})

// Olculen hata (kullanicinin bildirdigi "hala 2 kere okuyor cevaplari"): tek
// bir 1 saniyelik aralik iki cagirani birden karsilayamiyordu. Centik ILK
// TOKEN'da talep ediyor, besteci ise cevap TAMAMLANINCA -- aradan saniyeler
// geciyor, ilk talep dusmus oluyor ve ikincisi de kazaniyordu.

test('default interval is still one second (notifications, turn-end sound)', () => {
  const isDup = createEventDeduper()

  assert.equal(isDup('notify:1', 0), false)
  assert.equal(isDup('notify:1', 500), true)
  assert.equal(isDup('notify:1', 1_500), false)
})

test('a caller can hold a claim for longer (a spoken turn)', () => {
  const isDup = createEventDeduper()

  assert.equal(isDup('speak:u1', 0, 600_000), false)
  assert.equal(isDup('speak:u1', 60_000), true)
})

test('a long hold does not extend other keys', () => {
  const isDup = createEventDeduper()

  isDup('speak:u1', 0, 600_000)

  assert.equal(isDup('notify:1', 0), false)
  assert.equal(isDup('notify:1', 2_000), false)
})

test('the key can be claimed again once its hold expires', () => {
  const isDup = createEventDeduper()

  isDup('speak:u1', 0, 1_000)

  assert.equal(isDup('speak:u1', 2_000), false)
})
