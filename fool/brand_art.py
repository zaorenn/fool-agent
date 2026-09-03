"""Markanın ÇİZİMİ — tek kaynak.

Neden ayrı bir dosya
--------------------
Harfler ``█`` karakterinden çiziliyor, yani içinde "Hermes" DİZESİ geçmiyor.
Marka denetimi bu yüzden onu göremiyor: yeniden adlandırma aracı değişken adını
``FOOL_AGENT_LOGO`` yaptı ama çizim "HERMES-AGENT" yazmaya devam etti. Altındaki
şekil de Caduceus'tu -- Hermes'in asası. Hiçbir metin taraması bir sembolü
yakalayamaz.

``cli.py`` bir noktada elle düzeltildi, ``fool_cli/banner.py`` düzeltilmedi ve
CANLI olan ikincisiydi: ``fool`` yazan herkesin gördüğü ilk ekran dev harflerle
HERMES-AGENT diyordu. İki kopya olduğu sürece yine ayrışırlar.

Bu yüzden çizim BURADA duruyor ve iki taraf da buradan içe aktarıyor. Tek
kopya, ayrışacak ikinci bir yer yok.

Zone A: upstream bu dosyayı bilmiyor.
"""

WORDMARK = """[bold #E8365A]████████╗██╗  ██╗███████╗    ███████╗ ██████╗  ██████╗ ██╗
[bold #E8365A]╚══██╔══╝██║  ██║██╔════╝    ██╔════╝██╔═══██╗██╔═══██╗██║
[#D01A3F]   ██║   ███████║█████╗      █████╗  ██║   ██║██║   ██║██║
[#D01A3F]   ██║   ██╔══██║██╔══╝      ██╔══╝  ██║   ██║██║   ██║██║
[#8E1129]   ██║   ██║  ██║███████╗    ██║     ╚██████╔╝╚██████╔╝███████╗
[#8E1129]   ╚═╝   ╚═╝  ╚═╝╚══════╝    ╚═╝      ╚═════╝  ╚═════╝ ╚══════╝[/]"""

#: The Fool'un işareti -- sol panele sığan kompakt biçim.
#
# Onceki cizim Caduceus'tu: Hermes'in asasi. Marka degisiminde en gozden
# kacan sey, cunku hicbir metin taramasi bir sembolu yakalayamaz.
MARK = """[#8E1129]        ╱╲
[#8E1129]       ╱  ╲
[#D01A3F]      ╱ ╱╲ ╲
[#D01A3F]     ╱ ╱  ╲ ╲
[#E8365A]    ╱ ╱ ╱╲ ╲ ╲
[#E8365A]   ╱ ╱ ╱  ╲ ╲ ╲
[#E8365A]  ╱ ╱ ╱ ╱╲ ╲ ╲ ╲
[#D01A3F] ╱ ╱ ╱ ╱  ╲ ╲ ╲ ╲
[#D01A3F]╱ ╱ ╱ ╱ ╱╲ ╲ ╲ ╲ ╲
[#8E1129]╲ ╲ ╲ ╲ ╲╱ ╱ ╱ ╱ ╱
[#8E1129] ╲ ╲ ╲ ╲  ╱ ╱ ╱ ╱
[#D01A3F]  ╲ ╲ ╲ ╲╱ ╱ ╱ ╱
[#D01A3F]   ╲ ╲ ╲  ╱ ╱ ╱
[#E8365A]    ╲ ╲ ╲╱ ╱ ╱
[#E8365A]     ╲ ╲  ╱ ╱
[#E8365A]      ╲ ╲╱ ╱
[#D01A3F]       ╲  ╱
[#8E1129]        ╲╱[/]"""
