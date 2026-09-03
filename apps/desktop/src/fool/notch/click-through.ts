/**
 * Çentiğin tıkla-geçir kapısı.
 *
 * Ölçülen kırıklık
 * ----------------
 * Çentik penceresi ana süreçte KOŞULSUZ tıkla-geçir yapılıyordu::
 *
 *     win.setIgnoreMouseEvents(true, { forward: true })
 *
 * ...ve bir daha hiç kapatılmıyordu (pet overlay ve HUD'un aksine, onların
 * IPC ile açılıp kapanan birer kapısı var). Çentikteki PTT düğmesi ise
 * çiziliyor, hover efekti veriyor, ipucu gösteriyor -- ve tıklanınca HİÇBİR
 * ŞEY olmuyordu.
 *
 * Düğmenin yanındaki yorum ``pointerEvents: 'auto'`` ile bunun çözüldüğünü
 * söylüyordu. Çözmüyor: ``pointer-events`` SAYFA düzeyinde bir özellik, oysa
 * tıklama sayfaya hiç ulaşmıyor -- işletim sistemi penceresi onu daha önce
 * altta kalana veriyor. HUD'un kendi ``app/hud/click-through.ts`` dosyası tam
 * bu yanılgıyı yazıyor: "that is a page-level property, and the click never
 * reaches the page."
 *
 * Neden HUD'unkinin kopyası değil
 * -------------------------------
 * HUD'un kuralı "bir şeyin üzerindeysen KATI ol": rectangle'ının çoğu okunan
 * bir metin ve tıklanabilir yeri çok. Çentik bunun tersi -- ekranın en üst
 * kenarında duruyor ve orada tarayıcı sekmeleri, menü çubuğu, pencere
 * düğmeleri var. Aynı kuralı buraya taşımak, çentiğin o tıklamaları yutması
 * demekti; masaüstünü işgal etmeme kararı bu dosyanın var olma sebebiyle aynı
 * kadar önemli.
 *
 * O yüzden kural TERSİNE çevrildi: varsayılan tıkla-geçir, ve YALNIZCA imleç
 * açıkça işaretlenmiş (``data-notch-interactive``) bir öğenin üzerindeyken
 * pencere katılaşıyor. Yeni bir tıklanabilir parça eklemek işareti eklemeyi
 * gerektiriyor -- yani unutulursa düğme ölür, ama çentik ASLA ekranın üstünü
 * yutmaz. İki başarısızlıktan ucuz olanı bu.
 *
 * ``forward: true`` şart: tıkla-geçir açıkken de ``mousemove`` renderer'a
 * gelmeye devam ediyor, yoksa imleç düğmeye geldiğinde yeniden katılaşmayı
 * tetikleyecek hiçbir olay olmazdı.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useEffect } from 'react'

/** Tıklanabilir olduğu AÇIKÇA işaretlenmiş parçalar. */
export const NOTCH_INTERACTIVE_ATTR = 'data-notch-interactive'

/**
 * Pencere fareyi altta kalana devretmeli mi?
 *
 * Saf ve DOM'suz sınanabilir: karar burada, ölçüm çağıranda.
 */
export function notchIgnoresMouse(hit: Element | null): boolean {
  if (!hit) {
    // İmlecin nerede olduğunu bilmiyoruz. Katı kalmak, çentiğin ekranın üst
    // kenarını süresiz yutması demek olurdu -- bilinmeyende geçirgen ol.
    return true
  }

  return hit.closest(`[${NOTCH_INTERACTIVE_ATTR}]`) === null
}

/**
 * Tıkla-geçir kapısını imlecin altındakine göre sür.
 *
 * Hit-test ediliyor, öğeler SAYILMIYOR: stylesheet neyin tıklanabilir olduğuna
 * karar veren tek yer kalsın diye (HUD'la aynı gerekçe).
 */
export function useNotchClickThrough(): void {
  useEffect(() => {
    // KOK REF'I ALINMIYOR: karar yalnizca imlecin altindaki ogeye bakiyor ve
    // o ``document.elementFromPoint`` ile geliyor. Kullanilmayan bir ref
    // tasimak, HUD'un kancasina benzesin diye tasinan olu bir bagimlilik
    // olurdu.
    const setIgnoreMouse = window.foolDesktop?.notch?.setIgnoreMouse

    if (!setIgnoreMouse) {
      return
    }

    let ignoring: null | boolean = null
    // İmlecin son görüldüğü yer: odak/çizim değişince yeni bir hareket
    // beklemeden yeniden karar verilebilsin.
    let point: null | { x: number; y: number } = null

    const apply = () => {
      const hit = point ? document.elementFromPoint(point.x, point.y) : null
      const next = notchIgnoresMouse(hit)

      // YALNIZCA kenarlarda IPC: her ``mousemove``de mesaj yollamak, imleç
      // çentiğin üzerinden geçen her saniyede onlarca IPC demekti.
      if (ignoring !== next) {
        ignoring = next
        setIgnoreMouse(next)
      }
    }

    const onMove = (event: MouseEvent) => {
      point = { x: event.clientX, y: event.clientY }
      apply()
    }

    // İmleç pencereden çıktı: katı kalmak, çentiğin altındaki sekmeleri
    // tıklanamaz bırakırdı.
    const onLeave = () => {
      point = null
      apply()
    }

    apply()
    window.addEventListener('mousemove', onMove)
    document.addEventListener('mouseleave', onLeave)
    window.addEventListener('blur', onLeave)

    return () => {
      // Sökülürken GEÇİRGEN bırak: katı bir çentik, çizilmediği hâlde ekranın
      // üst kenarını yutan görünmez bir şerit olurdu.
      setIgnoreMouse(true)
      window.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseleave', onLeave)
      window.removeEventListener('blur', onLeave)
    }
  }, [])
}
