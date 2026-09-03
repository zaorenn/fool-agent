; Kaldirirken KALINTI birakma.
;
; Olculen hal (kullanicinin ikinci makinesi): Denetim Masasi'ndan uygulama
; kaldirildi ama ``%LOCALAPPDATA%\fool`` oldugu gibi kaldi -- depo, venv,
; yarim yapilandirma. Yeniden kurmak da duzeltmedi: kalan runtime
; "kullanilabilir" sayilip kurulum ekrani atlaniyordu, yani kullanici bozuk
; bir kuruluma kilitleniyordu ve cikis yolu yoktu.
;
; SORULUYOR, sessizce silinmiyor: o klasorde oturumlar, hafiza ve
; yapilandirma da duruyor. Kaldirmak ile "her seyimi sil" ayni sey degil --
; ama kullanicinin bunu SECEBILMESI gerekiyor, ve secmezse en azindan nerede
; oldugunu bilmesi.
!macro customUnInstall
  ${ifNot} ${isUpdated}
    MessageBox MB_YESNO|MB_ICONQUESTION \
      "The Fool'un verilerini de silmek ister misiniz?$\r$\n$\r$\n\
$LOCALAPPDATA\fool$\r$\n$\r$\n\
Bu klasorde sohbet oturumlariniz, hafiza ve ayarlariniz var.$\r$\n\
Hayir derseniz klasor oldugu gibi kalir ve tekrar kurdugunuzda kullanilir." \
      /SD IDNO IDNO keepUserData

    RMDir /r "$LOCALAPPDATA\fool"

    keepUserData:
  ${endIf}
!macroend
