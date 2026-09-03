import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

// Match the POSIX fallback surface used by the Python terminal environment.
// macOS apps launched from Finder/Dock often inherit only /usr/bin:/bin:/usr/sbin:/sbin,
// which misses Apple Silicon Homebrew and user-installed CLI tools such as codex.
const POSIX_SANE_PATH_ENTRIES = Object.freeze([
  '/opt/homebrew/bin',
  '/opt/homebrew/sbin',
  '/usr/local/sbin',
  '/usr/local/bin',
  '/usr/sbin',
  '/usr/bin',
  '/sbin',
  '/bin'
])

function delimiterForPlatform(platform = process.platform) {
  return platform === 'win32' ? ';' : ':'
}

function pathModuleForPlatform(platform = process.platform) {
  return platform === 'win32' ? path.win32 : path.posix
}

function pathEnvKey(env = process.env, platform = process.platform) {
  if (platform !== 'win32') {
    return 'PATH'
  }

  return Object.keys(env || {}).find(key => key.toUpperCase() === 'PATH') || 'PATH'
}

function currentPathValue(env = process.env, platform = process.platform) {
  const key = pathEnvKey(env, platform)

  return env?.[key] || ''
}

function appendUniquePathEntries(entries, { delimiter = path.delimiter } = {}) {
  const seen = new Set()
  const ordered = []

  for (const entry of entries) {
    if (!entry) {
      continue
    }

    const parts = Array.isArray(entry) ? entry : String(entry).split(delimiter)

    for (const part of parts) {
      if (!part || seen.has(part)) {
        continue
      }

      seen.add(part)
      ordered.push(part)
    }
  }

  return ordered.join(delimiter)
}

/**
 * The Fool-managed Node.js directories, in preferred lookup order.
 *
 * There are two on-disk layouts. `scripts/install.ps1` unpacks portable Node
 * straight into `%LOCALAPPDATA%\fool\node` (node.exe at the root, no `bin\`);
 * `scripts/install.sh` and the node-bootstrap helper use the POSIX
 * `$FOOL_HOME/node/bin`. Emit BOTH on every platform so mixed and migrated
 * installs resolve, leading with the layout native to the current platform.
 *
 * This is the single source of truth for the ordering rule on the Node side —
 * `main.ts` imports it rather than keeping its own copy. Mirrors
 * `iter_hermes_node_dirs()` in fool_constants.py, which the Electron main
 * process cannot import.
 */
function foolManagedNodePathEntries(
  foolHome,
  { platform = process.platform, pathModule = pathModuleForPlatform(platform) }: any = {}
) {
  if (!foolHome) {
    return []
  }

  const root = pathModule.join(foolHome, 'node')
  const bin = pathModule.join(root, 'bin')

  return platform === 'win32' ? [root, bin] : [bin, root]
}

function buildDesktopBackendPath({
  foolHome,
  venvRoot,
  currentPath = '',
  platform = process.platform,
  pathModule = pathModuleForPlatform(platform)
}: any = {}) {
  const delimiter = delimiterForPlatform(platform)
  const foolNodeDirs = foolManagedNodePathEntries(foolHome, { platform, pathModule })
  const venvBin = venvRoot ? pathModule.join(venvRoot, platform === 'win32' ? 'Scripts' : 'bin') : null
  const saneEntries = platform === 'win32' ? [] : POSIX_SANE_PATH_ENTRIES

  return appendUniquePathEntries([foolNodeDirs, venvBin, currentPath, saneEntries], { delimiter })
}

function normalizeFoolHomeRoot(foolHome, { pathModule = pathModuleForPlatform(process.platform) }: any = {}) {
  if (!foolHome) {
    return foolHome
  }

  const resolved = pathModule.resolve(String(foolHome))
  const parent = pathModule.dirname(resolved)

  if (pathModule.basename(parent).toLowerCase() === 'profiles') {
    return pathModule.dirname(parent)
  }

  return resolved
}

// FOOL-SEAM: espeak-ascii-path
//
// espeak-ng'ye ASCII OLMAYAN bir yol verilirse ARKA UC TAMAMEN OLUYOR.
//
// Olculen hata (kullanicinin laptopu, Windows hesabi ``Birhan Oğurlu``)::
//
//     Error processing file '...\piper\espeak-ng-data\phontab':
//       Illegal byte sequence.
//     The Fool backend exited (1)
//
// Yol DOGRU, dosya YERINDE. Tasinamayan sey ``ğ``: espeak-ng bir C
// kutuphanesi, yolu bayt olarak aliyor ve kod sayfasi donusumu karakteri
// bozuyor. Olumcul olmasinin sebebi ayri -- espeak-ng veri yuklemesi
// basarisiz olunca C tarafinda ``exit()`` cagiriyor, yani hicbir Python
// ``try/except`` yakalayamiyor.
//
// Kullanicinin gordugu: acilir acilmaz "backend stopped", read-aloud'da
// ECONNREFUSED, gateway "checking" -> offline, %1'de donan indirmeler, ve
// Ayarlar'da BOS bir ses bolumu (motor listesini sunan arka uc olu).
//
// NEDEN BURADA, Python tarafinda degil
// ------------------------------------
// Python duzeltmesi runtime checkout'unda yasiyor ve oraya ancak yukleyici
// kostuktan sonra ulasiyor. Bu satir ise PAKETIN ICINDE: kullanici yeni
// surumu kurar kurmaz, runtime hala eski olsa bile gecerli. Python tarafi
// ``ESPEAK_DATA_PATH`` zaten ayarliysa ona DOKUNMUYOR, yani iki taraf
// catismiyor -- burasi kazaniyor ve dogrusunu veriyor.
/** Yol saf ASCII mi? espeak-ng baytla calisiyor; digerini acamiyor. */
function isAsciiPath(value) {
  for (const ch of String(value)) {
    if (ch.charCodeAt(0) > 127) {
      return false
    }
  }

  return true
}

function espeakDataEnv(
  venvRoot,
  { platform = process.platform, pathModule = path, fs: fsImpl = fs, shortPath = shortPathSync }: any = {}
) {
  if (!venvRoot || platform !== 'win32') {
    return {}
  }

  const data = pathModule.join(venvRoot, 'Lib', 'site-packages', 'piper', 'espeak-ng-data')

  try {
    // ``phontab`` sinaniyor, klasorun kendisi degil: yarim bir kurulumu
    // gostermek hicbir sey gostermemekle ayni hatayi verirdi.
    if (!fsImpl.existsSync(pathModule.join(data, 'phontab'))) {
      return {}
    }
  } catch {
    return {}
  }

  // ASCII ise oldugu gibi: kisa adlar okunaksiz ve sorunu olmayan makinede
  // bu bedeli odemek gereksiz.
   
  if (isAsciiPath(data)) {
    return { ESPEAK_DATA_PATH: data }
  }

  const short = shortPath(data)

  // Kisa ad uretimi birimde kapali olabilir; o zaman elimizde daha iyisi yok.
  // Yanlis bir yol vermek yerine hic vermiyoruz -- Python tarafindaki kapi
  // o durumu yakalayip Piper'i hic yuklemiyor.
   
  return short && isAsciiPath(short) ? { ESPEAK_DATA_PATH: short } : {}
}

/** Windows 8.3 kisa yolu; alinamazsa ``null``. */
function shortPathSync(target) {
  try {
    const out = execFileSync(
      'cmd.exe',
      ['/d', '/c', 'for %I in ("' + target + '") do @echo %~sI'],
      { encoding: 'utf8', windowsHide: true, timeout: 5000 }
    )

    const line = String(out || '').trim().split('\n').pop()

    return line || null
  } catch {
    return null
  }
}

function buildDesktopBackendEnv({
  foolHome,
  pythonPathEntries = [],
  venvRoot,
  currentEnv = process.env,
  platform = process.platform,
  pathModule = pathModuleForPlatform(platform),
  fs: fsImpl = fs,
  shortPath = shortPathSync
}: any = {}): Record<string, string> {
  const delimiter = delimiterForPlatform(platform)
  const currentPythonPath = currentEnv?.PYTHONPATH || ''
  const key = pathEnvKey(currentEnv, platform)

  return {
    PYTHONPATH: appendUniquePathEntries([...pythonPathEntries, currentPythonPath], { delimiter }),
    // Force PEP 540 UTF-8 mode in the spawned Python backend so its stdio and
    // subprocess defaults are UTF-8 even on non-UTF-8 Windows locales (GBK,
    // cp1252, ...). fool_bootstrap sets this inside the child too, but only
    // after import — anything emitted earlier (interpreter startup errors,
    // pre-bootstrap tracebacks) still decodes with the locale default without
    // this. User's explicit setting wins. Re-port of PR #56499 (echoriver89).
    PYTHONUTF8: currentEnv?.PYTHONUTF8 ?? '1',
    [key]: buildDesktopBackendPath({
      foolHome,
      venvRoot,
      currentPath: currentPathValue(currentEnv, platform),
      platform,
      pathModule
    }),
    // Kullanicinin acikca ayarladigi deger EZILMIYOR.
    ...(currentEnv?.ESPEAK_DATA_PATH
      ? {}
      : espeakDataEnv(venvRoot, { platform, pathModule, fs: fsImpl, shortPath }))
  }
}

export {
  appendUniquePathEntries,
  buildDesktopBackendEnv,
  buildDesktopBackendPath,
  delimiterForPlatform,
  foolManagedNodePathEntries,
  normalizeFoolHomeRoot,
  pathEnvKey,
  POSIX_SANE_PATH_ENTRIES
}
