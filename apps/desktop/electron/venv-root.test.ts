/**
 * Sanal ortam kökü, seçilen yorumlayıcıdan türemeli.
 *
 * ``.venv``li bir klonda yorumlayıcı doğru seçilirken ortam ``<root>/venv``e
 * göre kuruluyordu. En kötü sonucu espeak: ``ESPEAK_DATA_PATH`` hiç
 * ayarlanmıyor, Python tarafındaki kapı boş görüp geri dönüyor, Piper
 * yükleniyor ve espeak-ng C tarafında ``exit()`` çağırıp arka ucu komple
 * öldürüyor.
 */

import { describe, expect, it } from 'vitest'

import { venvRootForPython } from './venv-root'

const SEP = String.fromCharCode(92)

/** Windows yol semantiği — ters bölü. */
const win = {
  basename: (target: string) => target.split(SEP).pop() ?? '',
  dirname: (target: string) => target.split(SEP).slice(0, -1).join(SEP),
  join: (...segments: string[]) => segments.join(SEP)
}

/** POSIX yol semantiği. */
const posix = {
  basename: (target: string) => target.split('/').pop() ?? '',
  dirname: (target: string) => target.split('/').slice(0, -1).join('/'),
  join: (...segments: string[]) => segments.join('/')
}

const w = (...parts: string[]) => parts.join(SEP)

describe('venvRootForPython', () => {
  it('NOKTALI .venv dogru cozuluyor', () => {
    // Regresyonun kendisi: burasi eskiden ``C:\repo\venv`` donerdi.
    expect(venvRootForPython(w('C:', 'repo', '.venv', 'Scripts', 'python.exe'), w('C:', 'repo'), win)).toBe(
      w('C:', 'repo', '.venv')
    )
  })

  it('kurucunun venv duzeni de dogru', () => {
    expect(venvRootForPython(w('C:', 'repo', 'venv', 'Scripts', 'python.exe'), w('C:', 'repo'), win)).toBe(
      w('C:', 'repo', 'venv')
    )
  })

  it('POSIX bin duzeni', () => {
    expect(venvRootForPython('/home/u/repo/.venv/bin/python', '/home/u/repo', posix)).toBe('/home/u/repo/.venv')
  })

  it('SISTEM Pythonu varsayilana dusuyor', () => {
    // Sistem Python'unun kendi ``Lib`` agacini venv koku saymak, onu piper
    // agirliklari icin taranan yer yapardi.
    expect(venvRootForPython(w('C:', 'Python313', 'python.exe'), w('C:', 'repo'), win)).toBe(w('C:', 'repo', 'venv'))
  })

  it('kok adi ne olursa olsun calisiyor', () => {
    // Kurulum dizini ``fool-agent``, gelistirici klonu baska bir ad -- karar
    // yorumlayicinin YERINE bakiyor, kokun adina degil.
    expect(
      venvRootForPython(w('C:', 'thefool-desktop', '.venv', 'Scripts', 'python.exe'), w('C:', 'thefool-desktop'), win)
    ).toBe(w('C:', 'thefool-desktop', '.venv'))
  })

  it('BUYUK harfli Scripts de taniniyor', () => {
    expect(venvRootForPython(w('C:', 'repo', '.venv', 'SCRIPTS', 'python.exe'), w('C:', 'repo'), win)).toBe(
      w('C:', 'repo', '.venv')
    )
  })
})
