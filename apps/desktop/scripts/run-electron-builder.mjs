// Resolve electronDist at runtime (#38673, #47917): electron-builder 26.8.x can
// re-unpack a broken Electron.app; reusing the installed dist dodges that.
// npm workspace hoisting is non-deterministic — require.resolve finds electron
// wherever it landed. Dist present → -c.electronDist=<abs>/dist; absent → let
// electron-builder fetch via @electron/get (electronVersion + ELECTRON_MIRROR).

import fs from "node:fs"
import path from "node:path"
import { spawnSync } from "node:child_process"
import { createRequire } from "node:module"
import { fileURLToPath } from "node:url"

const require = createRequire(import.meta.url)

function electronDistDir() {
  try {
    return path.join(path.dirname(require.resolve("electron/package.json")), "dist")
  } catch {
    return null
  }
}

function distBinary(dist) {
  if (process.platform === "darwin") {
    return path.join(dist, "Electron.app", "Contents", "MacOS", "Electron")
  }
  if (process.platform === "win32") {
    return path.join(dist, "electron.exe")
  }
  return path.join(dist, "electron")
}

function electronBuilderCli() {
  const pkgJson = require.resolve("electron-builder/package.json")
  const bin = require(pkgJson).bin
  const rel = typeof bin === "string" ? bin : bin["electron-builder"]
  return path.join(path.dirname(pkgJson), rel)
}

const dist = electronDistDir()
const args = []
if (dist && fs.existsSync(distBinary(dist))) {
  args.push(`-c.electronDist=${dist}`)
} else {
  console.warn(
    "[run-electron-builder] no local electron dist; electron-builder will fetch " +
      "via @electron/get (electronVersion + ELECTRON_MIRROR)."
  )
}
args.push(...process.argv.slice(2))

// Eslik kipi YAYINLANAN pakette olmamali -- ve bu, uretilen dosyaya bakilarak
// dogrulaniyor.
//
// Neden niyet yetmiyor: izin artik bu makinede duran bir isaret dosyasi
// (`apps/desktop/.companion-local`, bkz. vite.config.ts). Isaret dururken
// dalginlikla `npm run dist` calistirmak, esilik kipini iceren bir paketi
// yayina gonderirdi. Bir kez oldugunda geri alinamaz: paket disarida.
//
// Bu yuzden yayin yolunda paket TARANIYOR. Aranan seyler bilesenin kendi
// metinleri; koda dokunulmadigi surece ikisi birlikte degismez.
const COMPANION_FINGERPRINTS = ["Not met yet", "things unresolved"]

function isPublishing(argv) {
  // `--publish never` yayin degil. Diger her bicim (`--publish always`,
  // `--publish=onTag`, ciplak `-p always`) yayin sayilir.
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === "--publish" || arg === "-p") {
      return (argv[i + 1] ?? "") !== "never"
    }
    if (arg.startsWith("--publish=")) {
      return arg.slice("--publish=".length) !== "never"
    }
  }
  return false
}

function companionLeakedInto(dir) {
  let stack = [dir]
  const hits = []
  while (stack.length > 0) {
    const current = stack.pop()
    let entries
    try {
      entries = fs.readdirSync(current, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      const full = path.join(current, entry.name)
      if (entry.isDirectory()) {
        stack.push(full)
      } else if (/\.(js|html|css)$/i.test(entry.name)) {
        let text
        try {
          text = fs.readFileSync(full, "utf8")
        } catch {
          continue
        }
        if (COMPANION_FINGERPRINTS.some((needle) => text.includes(needle))) {
          hits.push(full)
        }
      }
    }
  }
  return hits
}

if (isPublishing(process.argv.slice(2))) {
  // `fileURLToPath` sart: ciplak `new URL(...).pathname` Windows'ta
  // `/C:/...` veriyor ve `%20` gibi kacislari cozmuyor -- tarama sessizce bos
  // bir dizine bakar, hicbir sey bulamaz ve koruma VAR gorunurken YOK olur.
  const rendererDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "dist")
  const leaks = companionLeakedInto(rendererDir)
  if (leaks.length > 0) {
    console.error(
      "[run-electron-builder] YAYIN DURDURULDU: eslik kipi uretilen pakette bulundu.\n" +
        leaks.map((f) => "  " + f).join("\n") +
        "\n\nBu paket bu makineye ozel (.companion-local) uretilmis. Yayin icin temiz\n" +
        "bir paket gerekiyor:\n\n" +
        "  cross-env VITE_COMPANION=0 npm run build && npm run builder -- <yayin argumanlari>\n"
    )
    process.exit(1)
  }
  console.log("[run-electron-builder] yayin denetimi: eslik kipi pakette YOK, devam ediliyor.")
}

// NODE_OPTIONS BURADA veriliyor, `cross-env` ile DEGIL.
//
// Olculen hata: `cross-env` paketi node_modules'te duruyor ama `.bin` kisayolu
// yok (yarim kalmis bir npm install). Sonuc, paketlemeyi ve deponun KENDI
// fresh-install sinavini komple durduran bir satir:
//
//     'cross-env' is not recognized as an internal or external command
//     npm error Lifecycle script `builder` failed
//
// Bu betik zaten Node; alt sureci kendisi doguruyor, yani ortam degiskenini
// dogrudan verebilir. Bir bagimliligi kritik yoldan cikarmak, onu onarmaktan
// daha saglam: kirilmasi mumkun olmayan sey en iyi calisan seydir.
//
// Deger disaridan gelirse ona saygi gosteriliyor -- yalnizca YOKSA konuyor.
const builderEnv = {
  ...process.env,
  NODE_OPTIONS: process.env.NODE_OPTIONS || "--max-old-space-size=16384",
}

const result = spawnSync(process.execPath, [electronBuilderCli(), ...args], {
  env: builderEnv,
  stdio: "inherit",
})
if (result.error) {
  console.error(`[run-electron-builder] spawn failed: ${result.error.message}`)
  process.exit(1)
}
process.exit(result.status == null ? 1 : result.status)
