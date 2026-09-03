"""Sistemde kurulu bir Chromium tarayıcısı bul.

Neden
-----
Upstream'de ``browser.backend`` varsayılanı **Browser Use** (bulut servisi).
API anahtarı yoksa çalışmaz — ve daha kötüsü, bu mod açıkken YERLEŞİK
``browser_*`` araçları da devre dışı kalır. Sonuç: ajanın elinde hiç tarayıcı
kalmaz ve her şeyi *computer use* ile yapmaya çalışır: ekran görüntüsü alıp
piksel koordinatına tıklamak. YouTube'da bir şarkıyı oynatmak bile beceremez.

Yerel-önce bir üründe bu varsayılan yanlış. The Fool yerleşik yığını kullanır
(``browser.backend: off``) ve tarayıcı ikilisini burada arar.

``agent-browser`` bir Chromium'a ihtiyaç duyuyor ve şu üç yoldan birini kabul
ediyor: ``AGENT_BROWSER_EXECUTABLE_PATH``, PATH'teki chrome/chromium, ya da
Playwright'ın indirdiği yapı. Çoğu Windows makinesinde Edge zaten kurulu —
Chromium tabanlı olduğu için aynı işi görür ve kullanıcıya 200 MB'lık ikinci
bir indirme yaptırmaz.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

#: agent-browser'ın resmi yolu.
ENV_VAR: Final[str] = "AGENT_BROWSER_EXECUTABLE_PATH"

#: Sıra bir tercih: gerçek Chrome > Edge > diğer Chromium türevleri.
#: Hepsi Chromium tabanlı, hepsi CDP konuşuyor.
_WINDOWS_CANDIDATES: Final[tuple[str, ...]] = (
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
)

_MACOS_CANDIDATES: Final[tuple[str, ...]] = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)

#: POSIX'te PATH üzerinden aranacak adlar.
_POSIX_NAMES: Final[tuple[str, ...]] = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "brave-browser",
)


def detect() -> str | None:
    """Kurulu bir Chromium ikilisinin tam yolunu döndür, yoksa ``None``."""
    # Kullanıcı zaten elle ayarlamışsa ona dokunma.
    existing = os.environ.get(ENV_VAR, "").strip()
    if existing and Path(existing).is_file():
        return existing

    if sys.platform == "win32":
        for template in _WINDOWS_CANDIDATES:
            path = Path(os.path.expandvars(template))
            if path.is_file():
                return str(path)
        return None

    if sys.platform == "darwin":
        for candidate in _MACOS_CANDIDATES:
            if Path(candidate).is_file():
                return candidate
        # macOS'ta da PATH'e düşmüş olabilir.

    for name in _POSIX_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def describe() -> str:
    """Teşhis için tek satır."""
    found = detect()
    return f"Chromium: {found}" if found else "Chromium: bulunamadi"
