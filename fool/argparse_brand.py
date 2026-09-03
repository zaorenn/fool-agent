"""argparse yardım metinlerini tek noktadan markalar.

Sorun
-----
CLI'nin ``--help`` çıktısındaki onlarca metin ("Update Hermes Agent to the
latest version", "Back up Hermes home directory to a zip file", …) ``_parser.py``
içinde düz string olarak duruyor. Her birini ayrı ayrı düzenlemek onlarca dikiş
demek — ve upstream her yeni komut eklediğinde markalaşma yeniden bozulur.

Çözüm
-----
argparse'ın metin **kabul ettiği** üç noktayı sarmalıyoruz. Böylece hem mevcut
hem de upstream'in gelecekte ekleyeceği tüm yardım metinleri otomatik markalanır.
Tek dikiş, sıfır bakım.

Neden güvenli
-------------
Yalnızca ``description`` / ``epilog`` / ``help`` alanlarına dokunuyoruz — yani
insana gösterilen metne. Argüman **adları**, ``dest`` değerleri, ``choices``
ve ayrıştırılan veri hiç ellenmiyor. Dolayısıyla komut satırı sözleşmesi aynen
korunuyor.

Bu yaklaşım bilinçli olarak stdout sarmalamaya tercih edildi: ``tui_gateway``
stdout üzerinden JSON-RPC konuşuyor ve oradaki baytları yeniden yazmak protokolü
bozardı. argparse yaması ise yalnızca yardım metadatasına dokunuyor.
"""

from __future__ import annotations

import argparse
from typing import Any

from fool.branding import brand_text

_INSTALLED = False


def _brand_kwarg(kwargs: dict[str, Any], key: str) -> None:
    value = kwargs.get(key)
    if isinstance(value, str):
        kwargs[key] = brand_text(value)


def install() -> None:
    """argparse'ı markalanmış yardım metinleri üretecek şekilde yamala.

    Birden çok kez çağrılabilir; yalnızca ilki iş yapar.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    # 1) ArgumentParser(description=..., epilog=...)
    _orig_init = argparse.ArgumentParser.__init__

    def _init(self, *args: Any, **kwargs: Any) -> None:
        _brand_kwarg(kwargs, "description")
        _brand_kwarg(kwargs, "epilog")
        _brand_kwarg(kwargs, "usage")
        _orig_init(self, *args, **kwargs)

    argparse.ArgumentParser.__init__ = _init  # type: ignore[method-assign]

    # 2) parser.add_argument(..., help=...)
    _orig_add_argument = argparse._ActionsContainer.add_argument

    def _add_argument(self, *args: Any, **kwargs: Any) -> Any:
        _brand_kwarg(kwargs, "help")
        _brand_kwarg(kwargs, "metavar")
        return _orig_add_argument(self, *args, **kwargs)

    argparse._ActionsContainer.add_argument = _add_argument  # type: ignore[method-assign]

    # 3) subparsers.add_parser(..., help=..., description=...)
    _orig_add_parser = argparse._SubParsersAction.add_parser

    def _add_parser(self, name: str, **kwargs: Any) -> Any:
        _brand_kwarg(kwargs, "help")
        _brand_kwarg(kwargs, "description")
        _brand_kwarg(kwargs, "epilog")
        return _orig_add_parser(self, name, **kwargs)

    argparse._SubParsersAction.add_parser = _add_parser  # type: ignore[method-assign]

    # 4) add_argument_group(title=..., description=...)
    _orig_add_group = argparse._ActionsContainer.add_argument_group

    def _add_group(self, *args: Any, **kwargs: Any) -> Any:
        _brand_kwarg(kwargs, "title")
        _brand_kwarg(kwargs, "description")
        return _orig_add_group(self, *args, **kwargs)

    argparse._ActionsContainer.add_argument_group = _add_group  # type: ignore[method-assign]
