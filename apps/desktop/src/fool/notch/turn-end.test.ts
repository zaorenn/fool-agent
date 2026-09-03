import { describe, expect, it } from 'vitest'

import { turnEndAction } from './turn-end'

describe('tur SES bitince biter, metin bitince degil', () => {
  it('metin bittiyse ama ses SURUYORSA turu ayakta tutuyor', () => {
    expect(
      turnEndAction({ playbackIdle: false, replyComplete: true, status: 'speaking' })
    ).toBe('hold-for-audio')
  })

  it('ses de bittiyse turu bitiriyor', () => {
    expect(turnEndAction({ playbackIdle: true, replyComplete: true, status: 'speaking' })).toBe('end')
  })

  it('metin hala akiyorsa bir sey yapmiyor', () => {
    expect(
      turnEndAction({ playbackIdle: true, replyComplete: false, status: 'speaking' })
    ).toBe('wait')
  })

  it('kullanici DINLIYORSA turu bitirmiyor -- kaydini keserdi', () => {
    // Araya girdi ya da eller serbest mikrofonu yeniden acti.
    expect(
      turnEndAction({ playbackIdle: true, replyComplete: true, status: 'listening' })
    ).toBe('wait')
  })

  it('dusunme evresinde ses yoksa tur biter', () => {
    // Arac-yalniz tur: hic seslendirilecek metin gelmedi.
    expect(
      turnEndAction({ playbackIdle: true, replyComplete: true, status: 'thinking' })
    ).toBe('end')
  })
})
