# pedal-ffb-motor-yaz-l-m-
ACC, LMU ve iRacing için Arduino Uno (CH340) ve L293D Motor Shield tabanlı, yerel çalışan ücretsiz DIY pedal titreşim (haptic) uygulaması.
pedal Haptic — ACC, LMU ve iRacing oyunları için evde hazırlanan DIY pedal titreşim (FFB) kitlerine özel, tamamen ücretsiz ve yalnızca yerel (offline) çalışan kontrol uygulamasıdır.

Gaz da TC ve Tekerlek kayması, Frende ABS ve Tekerlek kilitlenmesi eklenmiştir.

Donanım Uyumu: Arduino Uno R3 SMD (CH340), L293D Motor Sürücü Shield ve 6–12V titreşim motorları (MTR.TIT.01.000014) ile uyumludur.

Gereksinim: Bilgisayarda Python kurulu olmalıdır (pyserial kütüphanesi kurulum betiği ile otomatik yüklenir).

Test Durumu: Uygulama yapay zeka yardımıyla geliştirilmiş olup şu an için yalnızca Assetto Corsa Competizione (ACC) üzerinde test edilip onaylanmıştır. LMU ve iRacing destekleri deneyseldir.
KURULUM

1. Dosyaları hazırla
PedalHaptic klasörünü masaüstüne koy. Arduino IDE kodu açarken PedalHaptic.ino'nun aynı adlı bir klasör içinde olmasını ister. Bu madde hazır sekildedir dosyayı direk zipten çıkarabilirsiniz.

2. Python'u kur
·	python.org/downloads adresinden indir.
·	Kurulumun ilk ekranında Add python.exe to PATH kutusunu işaretle, sonra Install Now.

3. Kütüphaneyi kur
  1_kurulum.bat dosyasına çift tıkla. "Successfully installed pyserial" yazarsa tamam. Bu adım bir kere yapılır.

4. Arduino'ya kodu yükle

     1.	SimHub açıksa tamamen kapat, sağ alttaki simgeden de çık.(arduinoya simhubdan farklı kod yükleyeceğinden simhubda çalışmayacaktır, tekrar simhuba kalibre etmek isterseniz simhub içinden sürücüyü güncelleştir yaparak kullanabilirsiniz)

     2.	Arduino IDE'yi aç (yoksa arduino.cc'den ücretsiz indir). Arduino USB'ye takılı olsun.

     3.	PedalHaptic.ino dosyasını aç.

     4.	Sketch > Include Library > Manage Libraries: "Adafruit Motor Shield library" ara ve V1 olanı kur (adında V2 yazan değil).

     5.	Tools > Board > Arduino AVR Boards > Arduino Uno.

     6.	Tools > Port: Arduino'nun portunu seç (örneğin COM3).

    7.	Upload (ok) tuşuna bas. "Done uploading" yazınca IDE'yi kapat, yoksa portu tutar.
    
    8. Dosya içindeki arduino	PedalHaptic.ino dosyasını kullanarak veya içindeki kodu kopyala yapıştır yaparak yukleyiniz karta.
    
  Uygulamayı başlat

1.	2_baslat.bat dosyasına çift tıkla.

2.	Arduino portunu seç ve Baglan'a bas. İki saniye sonra "Bagli" yazar, sağda gecikme görünür.

3.	Sağ üstten oyunu seç: ACC, LMU veya iRacing
 ZİP DOSYASINI İNDİREREK TĞM DOSYALARI İNDİRMİŞ OLURSUNUZ.

DİKKAT EDİLMESİ GEREKENLER

 İlk testte eşiklerin ve değerlerin ayarlanması gerekebilir.
Titreşim motorları dönmeye başlarken 30-80 ms gecikir. Yazılım gecikmesi buna eklenmez ama bu fiziksel gecikme sıfırlanamaz.

Seri gecikme sağ üstte canlı görünür. Motorun kendi gecikmesini içermez.

Bilgisayar bağlantıyı keserse motorlar 150 ms içinde kendiliğinden durur.

Ve Uygulama içinde Arduino ve port seçme kısmında otomatik seçecektir ama seçmezse veya yanlış portu seçmesi durumunda buradan kendi cihazınız hangi porttayse seçebilirsiniz

Motor shielde motorları bağlarken 
M1: fren motoru
M2: gaz motoru olacak sekilde bağlanılmıştır.
Gaz da TC ve Tekerlek kayması, Frende ABS ve Tekerlek kilitlenmesi eklenmiştir.

ELİMDEN GELDİĞİNCE YARDIMCI OLMAYA ÇALIŞIYORUM, UYGULAMAYI KULLANARAK TÜM SORUMLULUĞU KABUL ETMİŞ OLURSUNUZ 
