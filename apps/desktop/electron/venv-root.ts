/**
 * Seçilen yorumlayıcının sanal ortam KÖKÜ — saf, sınanabilir.
 *
 * Neden ayrı bir karar
 * --------------------
 * ``findPythonForRoot`` bir klonda önce ``.venv``e, sonra ``venv``e bakıyor:
 * ``.venv`` uv'nin ve pratikte her geliştirici klonunun düzeni, ``venv`` ise
 * kurucunun yarattığı. Ortamı kuran taraf ise ``venvRoot``u KOŞULSUZ
 * ``<root>/venv`` diye yazıyordu -- yani ad iki yerde ayrı ayrı duruyordu ve
 * ``.venv``li her klonda ikisi ayrışıyordu.
 *
 * Ölçülen sonuç sessiz değil, ölümcül
 * -----------------------------------
 * ``backend-env.ts::espeakDataEnv`` ağırlıkları ``<venvRoot>/Lib/site-packages/
 * piper/espeak-ng-data/phontab`` altında arıyor. Kök yanlışsa dosyayı bulamıyor
 * ve ``{}`` dönüyor: ``ESPEAK_DATA_PATH`` HİÇ ayarlanmıyor. Python tarafındaki
 * kapı (``tools/tts_tool.py::_refuse_piper_on_unreadable_espeak_path``) da o
 * değişkeni okuyup boş görünce geri dönüyor -- Piper yükleniyor, espeak-ng
 * ASCII olmayan kendi yolunu açamıyor ve C tarafında ``exit()`` çağırıyor.
 * Hiçbir Python ``try/except`` bunu yakalayamaz: arka uç komple ölüyor.
 *
 * Yani ``espeakDataEnv``in önlemek için yazıldığı hatanın ta kendisi,
 * yalnızca ``.venv`` düzeninde geri gelmiş hâli.
 *
 * Tek doğru kaynak yorumlayıcının KENDİ yeri.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

export interface VenvRootDeps {
  dirname: (target: string) => string
  basename: (target: string) => string
  join: (...segments: string[]) => string
}

/**
 * ``<venv>/Scripts/python.exe`` -> ``<venv>``, ``<venv>/bin/python`` -> ``<venv>``.
 *
 * Yorumlayıcı bir sanal ortamda DEĞİLSE (sistem Python'u) ``root/venv``
 * varsayılanına düşüyor: kurulumun yaratacağı yer orası, ve sistem Python'unun
 * kendi ``Lib`` ağacını venv köküymüş gibi göstermek onu piper ağırlıkları için
 * taranan yer yapardı.
 */
export function venvRootForPython(python: string, root: string, deps: VenvRootDeps): string {
  const parent = deps.dirname(python)
  const name = deps.basename(parent).toLowerCase()

  if (name === 'scripts' || name === 'bin') {
    return deps.dirname(parent)
  }

  return deps.join(root, 'venv')
}
