import assert from 'node:assert/strict'
import path from 'node:path'

import { test } from 'vitest'

import {
  appendUniquePathEntries,
  buildDesktopBackendEnv,
  buildDesktopBackendPath,
  foolManagedNodePathEntries,
  normalizeFoolHomeRoot,
  pathEnvKey,
  POSIX_SANE_PATH_ENTRIES
} from './backend-env'

test('desktop backend PATH adds The Fool-managed bins and missing POSIX sane entries', () => {
  const result = buildDesktopBackendPath({
    foolHome: '/Users/test/.fool',
    venvRoot: '/Users/test/.fool/hermes-agent/venv',
    currentPath: '/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin',
    platform: 'darwin',
    pathModule: path.posix
  })

  const entries = result.split(':')
  // Both managed-Node layouts lead, POSIX-native shape first, then the venv.
  assert.deepEqual(entries.slice(0, 3), [
    '/Users/test/.fool/node/bin',
    '/Users/test/.fool/node',
    '/Users/test/.fool/hermes-agent/venv/bin'
  ])
  assert.ok(entries.includes('/opt/homebrew/bin'), 'Apple Silicon Homebrew bin is added')
  assert.ok(entries.includes('/opt/homebrew/sbin'), 'Apple Silicon Homebrew sbin is added')
  assert.ok(entries.includes('/usr/local/sbin'), 'missing standard sbin is added')

  for (const expected of POSIX_SANE_PATH_ENTRIES) {
    assert.ok(entries.includes(expected), `${expected} should be present`)
  }
})

test('managed Node dirs lead with the platform-native layout but always offer both', () => {
  const posix = foolManagedNodePathEntries('/Users/test/.fool', {
    platform: 'darwin',
    pathModule: path.posix
  })

  const windows = foolManagedNodePathEntries('C:\\Users\\test\\AppData\\Local\\fool', {
    platform: 'win32',
    pathModule: path.win32
  })

  // install.sh uses node/bin; install.ps1 unpacks node.exe into node\ itself.
  // Both shapes are always emitted so migrated installs keep resolving.
  assert.deepEqual(posix, ['/Users/test/.fool/node/bin', '/Users/test/.fool/node'])
  assert.deepEqual(windows, [
    'C:\\Users\\test\\AppData\\Local\\fool\\node',
    'C:\\Users\\test\\AppData\\Local\\fool\\node\\bin'
  ])
})

test('managed Node dirs are empty without a Fool home', () => {
  assert.deepEqual(foolManagedNodePathEntries(undefined, { platform: 'darwin', pathModule: path.posix }), [])
  assert.deepEqual(foolManagedNodePathEntries('', { platform: 'win32', pathModule: path.win32 }), [])
})

test('every managed Node dir outranks the inherited PATH on both platforms', () => {
  for (const [platform, pathModule, home, inherited, delimiter] of [
    ['darwin', path.posix, '/Users/test/.fool', '/usr/local/bin:/usr/bin', ':'],
    ['win32', path.win32, 'C:\\fool', 'C:\\Program Files\\nodejs;C:\\Windows\\System32', ';']
  ] as const) {
    const entries = buildDesktopBackendPath({
      foolHome: home,
      venvRoot: null,
      currentPath: inherited,
      platform,
      pathModule
    }).split(delimiter)

    const managed = foolManagedNodePathEntries(home, { platform, pathModule })
    const firstInherited = Math.min(...inherited.split(delimiter).map(entry => entries.indexOf(entry)))

    for (const dir of managed) {
      assert.ok(
        entries.indexOf(dir) >= 0 && entries.indexOf(dir) < firstInherited,
        `${dir} must precede the inherited PATH on ${platform}`
      )
    }
  }
})

test('desktop backend PATH preserves first occurrence and avoids duplicates', () => {
  const result = buildDesktopBackendPath({
    foolHome: '/Users/test/.fool',
    venvRoot: '/Users/test/.fool/hermes-agent/venv',
    currentPath: '/opt/homebrew/bin:/usr/bin:/opt/homebrew/bin:/bin',
    platform: 'darwin',
    pathModule: path.posix
  })

  const entries = result.split(':')
  assert.equal(entries.filter(entry => entry === '/opt/homebrew/bin').length, 1)
  assert.ok(
    entries.indexOf('/opt/homebrew/bin') < entries.indexOf('/opt/homebrew/sbin'),
    'existing Homebrew bin keeps its precedence over appended missing sane entries'
  )
})

test('buildDesktopBackendEnv extends PYTHONPATH and backend PATH together', () => {
  const env = buildDesktopBackendEnv({
    foolHome: '/Users/test/.fool',
    pythonPathEntries: ['/repo/hermes-agent'],
    venvRoot: '/Users/test/.fool/hermes-agent/venv',
    currentEnv: {
      PATH: '/usr/bin:/bin',
      PYTHONPATH: '/existing/pythonpath'
    },
    platform: 'darwin',
    pathModule: path.posix
  })

  assert.equal(env.PYTHONPATH, '/repo/hermes-agent:/existing/pythonpath')
  assert.ok(
    env.PATH.startsWith(
      '/Users/test/.fool/node/bin:/Users/test/.fool/node:/Users/test/.fool/hermes-agent/venv/bin:'
    )
  )
  assert.ok(env.PATH.includes('/opt/homebrew/bin'))
})

test('buildDesktopBackendEnv forces PYTHONUTF8 unless the user set it explicitly', () => {
  const defaulted = buildDesktopBackendEnv({
    foolHome: '/Users/test/.fool',
    currentEnv: { PATH: '/usr/bin' },
    platform: 'darwin',
    pathModule: path.posix
  })

  assert.equal(defaulted.PYTHONUTF8, '1')

  const optedOut = buildDesktopBackendEnv({
    foolHome: '/Users/test/.fool',
    currentEnv: { PATH: '/usr/bin', PYTHONUTF8: '0' },
    platform: 'darwin',
    pathModule: path.posix
  })

  assert.equal(optedOut.PYTHONUTF8, '0')
})

test('normalizeFoolHomeRoot maps profile homes back to the global Fool root', () => {
  assert.equal(
    normalizeFoolHomeRoot('/Users/test/.fool/profiles/oracle', { pathModule: path.posix }),
    '/Users/test/.fool'
  )
  assert.equal(
    normalizeFoolHomeRoot('C:\\Users\\test\\AppData\\Local\\fool\\profiles\\oracle', { pathModule: path.win32 }),
    'C:\\Users\\test\\AppData\\Local\\fool'
  )
  assert.equal(normalizeFoolHomeRoot('/Users/test/.fool', { pathModule: path.posix }), '/Users/test/.fool')
})

test('Windows PATH casing and delimiter are preserved without POSIX sane entries', () => {
  const env = buildDesktopBackendEnv({
    foolHome: 'C:\\Users\\test\\AppData\\Local\\fool',
    pythonPathEntries: ['C:\\repo\\hermes-agent'],
    venvRoot: 'C:\\Users\\test\\AppData\\Local\\fool\\hermes-agent\\venv',
    currentEnv: {
      Path: 'C:\\Windows\\System32;C:\\Windows',
      PYTHONPATH: 'C:\\existing\\pythonpath'
    },
    platform: 'win32',
    pathModule: path.win32
  })

  assert.equal(pathEnvKey({ Path: 'x' }, 'win32'), 'Path')
  assert.equal(env.PATH, undefined)
  // Windows leads with the portable layout (install.ps1 unpacks node.exe
  // straight into node\, no bin\), then the POSIX shape for migrated installs.
  assert.ok(
    env.Path.startsWith(
      'C:\\Users\\test\\AppData\\Local\\fool\\node;C:\\Users\\test\\AppData\\Local\\fool\\node\\bin;'
    )
  )
  assert.ok(env.Path.includes('\\venv\\Scripts;'))
  assert.ok(env.Path.includes(';C:\\Windows\\System32;C:\\Windows'))
  assert.equal(env.Path.includes('/opt/homebrew/bin'), false)
})

test('appendUniquePathEntries drops empty entries and keeps first occurrence', () => {
  assert.equal(appendUniquePathEntries([':/a::/b', ['/a', '/c']], { delimiter: ':' }), '/a:/b:/c')
})

// ---------------------------------------------------------------------------
// ESPEAK_DATA_PATH — bir ses motorunun arka ucu ÖLDÜRMESİNİ engelleyen kapı
// ---------------------------------------------------------------------------

test('ASCII olmayan bir yolda espeak ASCII kisa yolu aliyor', () => {
  // Ölçülen hata (kullanıcının laptopu, Windows hesabı ``Birhan Oğurlu``):
  //
  //     Error processing file '.../piper/espeak-ng-data/phontab':
  //       Illegal byte sequence.
  //     The Fool backend exited (1)
  //
  // Yol doğru, dosya yerinde -- taşınamayan şey ``ğ``. espeak-ng bir C
  // kütüphanesi, yolu bayt olarak alıyor. Veri yüklemesi başarısız olduğunda
  // C tarafında ``exit()`` çağırıyor: hiçbir Python try/except yakalayamaz,
  // arka uç komple ölür. Kullanıcının gördüğü on saniyede bir "backend
  // stopped" idi.
  //
  // Bu karar BURADA (paketin içinde) veriliyor, Python tarafında değil: Python
  // düzeltmesi runtime checkout'unda yaşıyor ve oraya ancak yükleyici
  // koştuktan sonra ulaşıyor. Buradaki satır kurulur kurulmaz geçerli.
  const env = buildDesktopBackendEnv({
    foolHome: 'C:/Users/Birhan Oğurlu/AppData/Local/fool',
    venvRoot: 'C:/Users/Birhan Oğurlu/AppData/Local/fool/fool-agent/venv',
    currentEnv: {},
    platform: 'win32',
    pathModule: path.win32,
    // Gerçek dosya sistemi yok: ``phontab`` VAR sayılıyor.
    fs: { existsSync: () => true },
    shortPath: () => 'C:/Users/BIRHAN~1/AppData/Local/fool/fool-agent/venv/Lib/site-packages/piper/espeak-ng-data'
  })

  assert.ok(env.ESPEAK_DATA_PATH, 'espeak yolu hic verilmemis')
  assert.ok(
    [...env.ESPEAK_DATA_PATH].every(ch => ch.charCodeAt(0) < 128),
    'espeak hala ASCII olmayan bir yol aliyor'
  )
})

test('ASCII bir yola DOKUNULMUYOR', () => {
  // Kısa adlar okunaksız; sorunu olmayan makinede bu bedeli ödemek gereksiz.
  let shortAsked = false

  const env = buildDesktopBackendEnv({
    foolHome: 'C:/Users/dev/AppData/Local/fool',
    venvRoot: 'C:/Users/dev/AppData/Local/fool/fool-agent/venv',
    currentEnv: {},
    platform: 'win32',
    pathModule: path.win32,
    fs: { existsSync: () => true },
    shortPath: () => {
      shortAsked = true

      return null
    }
  })

  assert.equal(shortAsked, false, 'ASCII yol icin kisa ad istenmemeli')
  assert.match(env.ESPEAK_DATA_PATH, /espeak-ng-data$/)
})

test('KULLANICININ ayari eziliyor DEGIL', () => {
  const env = buildDesktopBackendEnv({
    foolHome: 'C:/Users/dev/AppData/Local/fool',
    venvRoot: 'C:/Users/dev/AppData/Local/fool/fool-agent/venv',
    currentEnv: { ESPEAK_DATA_PATH: 'D:/my-espeak' },
    platform: 'win32',
    pathModule: path.win32,
    fs: { existsSync: () => true }
  })

  assert.equal(env.ESPEAK_DATA_PATH, undefined, 'kullanicinin degeri korunmali (spread ile gelmemeli)')
})

test('veri YOKSA hicbir sey iddia edilmiyor', () => {
  // Yarım bir kurulumu göstermek, hiçbir şey göstermemekle aynı hatayı verirdi.
  const env = buildDesktopBackendEnv({
    foolHome: 'C:/Users/dev/AppData/Local/fool',
    venvRoot: 'C:/Users/dev/AppData/Local/fool/fool-agent/venv',
    currentEnv: {},
    platform: 'win32',
    pathModule: path.win32,
    fs: { existsSync: () => false }
  })

  assert.equal(env.ESPEAK_DATA_PATH, undefined)
})

test('POSIX ETKILENMIYOR', () => {
  const env = buildDesktopBackendEnv({
    foolHome: '/home/u/.fool',
    venvRoot: '/home/u/.fool/fool-agent/venv',
    currentEnv: {},
    platform: 'linux',
    pathModule: path.posix,
    fs: { existsSync: () => true }
  })

  assert.equal(env.ESPEAK_DATA_PATH, undefined)
})
