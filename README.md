# PressTrail

Seçtiğiniz Türkçe RSS ve Atom yayınlarından haber toplayan yerel bir OSINT çalışma alanı. Her yayın ayrı bir gözlem olarak saklanır. Bir olay adayını incelerken metin benzerliğini, kaynağın bildirdiği yayın sırasını, sistemin gözlem sırasını ve metinden çıkan bağlantıları ayrı ayrı görebilirsiniz. Uygulama kesin ilk kaynak, kopyalama veya haber doğruluğu kararı vermez.

## Docker Compose

Python ve Node.js kurmadan çalıştırmak için Docker ve Compose eklentisi gerekir.

```sh
docker compose up --build -d
docker compose ps
docker compose exec api python -m app.demo
```

Ana sayfa [127.0.0.1:5173](http://127.0.0.1:5173) adresinde açılır. **Uygulamayı aç** bağlantısı araştırma paneline götürür. API belgeleri [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) adresindedir. API başlangıçta Alembic migration’ını çalıştırır. PostgreSQL ve API hazır olduğunda worker başlar. `docker compose down` servisleri durdurur ve veritabanı hacmini korur.

İlk imaj derlemesi paket ve imaj kayıtlarına erişir. İmajlar hazırlandıktan sonra `app.demo` ile örnekleri yüklemek ve incelemek internet gerektirmez. Komut tekrar çalıştırılabilir. Örnek kaynaklar duraklatılmıştır, kurgusal olarak etiketlenir ve gerçek kaynaklarla aynı gruba girmez.

## Kaynak ekleme ve araştırma akışı

1. **Kaynaklar** sayfasında yayın adını, RSS ya da Atom adresini ve kontrol aralığını girin. İzin verilen haber sayfalarını da toplamak istiyorsanız tam metin seçeneğini açın.
2. Kaynağı kaydedin. Aktif kaynaklar worker tarafından planlanır. **Şimdi kontrol et** düğmesi bir işi kuyruğa alır veya bekleyen aynı işi döndürür.
3. **Toplama geçmişi** bölümünde denemeleri, iş durumunu, yeni sürümleri ve atlanan kayıtları izleyin. Kısmi başarı, geçerli kayıtların işlendiğini ve bazı girdilerin atlandığını veya özetle devam edildiğini gösterir.
4. **Haber grupları** sayfasından bir grubu açın. Zaman çizelgesinde iki haber seçerek metinleri karşılaştırın. Haber detayında eski sürümleri açabilir, grup üyeliğini onaylayabilir, başka gruba taşıyabilir, yeni gruba ayırabilir veya haberin gruptan çıkarılmasını kaydedebilirsiniz.

Kaynağı duraklatınca yeni işler planlanmaz. Bir yayının RSS adresi değiştirildiğinde geçmiş haberlerin kayıtlı adresi korunur. Aynı yayın ve normalize haber URL’si, bir haber kaydıdır. Tekil feed kimliği, aynı RSS adresindeki haber URL’si değişikliklerinde ikinci bir eşleştirme işaretidir. Sürüm parmak izi son sürümle karşılaştırılır. A → B → A gözlem dizisinde üçüncü sürüm saklanır.

## Haberin evrimi ve iddia takibi

1. **Haber detayı → Sürümleri karşılaştır** bölümünden aynı haberin iki kaydını seçin. Fark ekranı iki kaynak sürümüne bağlanır, toplama zamanlarını gösterir ve ekleme, kaldırma, taşıma ile kelime ve cümle değişikliklerini ayırır. Çıkarıcı veya kapsam farklıysa uyarı gösterilir.
2. **İddia ve düzeltme adayları** bölümünde seçili sürümün önerilerini inceleyin. Elle aday oluşturmak için alanı seçip salt okunur kaynak metninden bir alıntı işaretleyin. Sistem alıntıyı sürüm, alan ve Unicode karakter aralığıyla doğrular. Aday ayrıntısı kaynak bağlamını ve çıkarılan sayı, birim, tarih veya alıntıyı gösterir.
3. **Grup detayı → İddia karşılaştırma** bölümünde iki farklı haberden aday seçin veya bir eşleştirme önerisini açın. Eşleştirmeyi onaylamak yalnızca adayları birlikte inceleme kararını kaydeder. Üyelik sonradan değişirse eşleştirmenin ilk grup bağlamı korunur.
4. Haber, sürüm, fark ve aday sayfalarında **Araştırmacı notları** oluşturun. Notları düzenleyebilir, silebilir, etiketleyebilir ve inceleme durumunu değiştirebilirsiniz. Notlar alıntılanan kaynak metninden ayrı saklanır.
5. Bir haber ya da grupta **Takip et** seçeneğini açın. **Takip** ekranı yeni grup üyesi, değişen içerik ve yeni düzeltme adayı bildirimlerini gösterir. Takibi bırakmak geçmiş bildirimleri silmez. Olay anahtarı tekrar bildirimleri önler ve olay anındaki grup adı saklanır.
6. **Grup detayı → HTML araştırma raporu** bölümünde dahil edilecek kısa alıntıları, farkları ve notları seçin. Rapor bağlantılar, bildirilen yayın ve toplama zamanları, seçim kapsamı, oluşturulma zamanı ve sınırlamalarla birlikte indirilir. Dosya ağ bağlantısı olmadan okunabilir.

Mevcut kurulumda API ve worker’ı yeni kodla çalıştırmadan önce `cd backend` ve `python -m alembic upgrade head` çalıştırın. Compose, API başlarken migration’ı uygular. Worker eski sürümleri küçük işlemler halinde tarar. Bu geçmiş taraması bildirim üretmez. Ardışık sürümlerin farkları toplama sırasında hazırlanır. Diğer çiftler API tarafından sıraya alınır ve worker tarafından hesaplanır.

Fark yöntemi NFC ve boşluk normalizasyonu kullanır. Aynı normalize metne sahip tekil paragraflar taşınmış olarak tanınabilir. Metin kaydı ham HTML biçimlendirmesini içermez. Paragraf analizi her alan için ilk 500 paragrafla, kelime analizi paragraf başına ilk 1.200 belirteçle sınırlıdır. Kural tabanlı tarama Türkçe tarih, sayısal ifade, tırnaklı alıntı ve belirli yayıncı güncelleme kalıplarını arar. Genel anahtar kelime kullanımları tek başına aday oluşturmaz. Tarih ve sayı ifadeleri kaynak metnindeki biçimleriyle saklanır. Her sürümde en çok 120 iddia ve 120 düzeltme adayı üretilir. Otomatik eşleştirme, aynı gruptaki diğer haberlerden son kaydedilen en fazla 300 aday içinde normalize metni aynı olan alıntıları önerir. Araştırmacı farklı ifadeleri elle eşleştirebilir. Bir inceleme durumu veya eşleştirme, iddianın doğruluğunu ya da yayıncının güvenilirliğini ölçmez.

## Yerel geliştirme

Python 3.12, Node.js 22 ve PostgreSQL kullanın. Windows PowerShell ve Unix kabukları için ortam değişkeni sözdizimleri aşağıdadır.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
$env:DATABASE_URL = "postgresql+psycopg://haber:parola@127.0.0.1:5432/haber"
python -m alembic upgrade head
python -m app.demo
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Unix kabuğunda sanal ortamı `source .venv/bin/activate` ile etkinleştirin ve `export DATABASE_URL='postgresql+psycopg://haber:parola@127.0.0.1:5432/haber'` kullanın. Worker için ayrı terminalde aynı dizin, sanal ortam ve veritabanı ayarlarıyla `python -m app.worker` çalıştırın. Yerel bir önizleme için `DATABASE_URL` olmadan SQLite kullanılabilir. Kuyruğun eşzamanlı süreç garantileri PostgreSQL’e dayanır.

Frontend için ayrı terminalde:

```sh
cd frontend
npm ci
npm run dev
```

Vite `/api` isteklerini yerel 8000 portuna iletir. Compose’da aynı görevi Nginx üstlenir. Üretim Python bağımlılıkları `requirements.lock`, test bağımlılıkları `requirements-dev.lock`, frontend bağımlılıkları `package-lock.json` ile sabitlenir.

| Değişken | İşlev |
| --- | --- |
| `POSTGRES_PASSWORD` | Compose veritabanı parolası. Örnek yerel değer değiştirilebilir. URL’de özel anlamı olmayan karakterler kullanın. |
| `DATABASE_URL` | API, worker ve Alembic bağlantı adresi. Compose bu değeri servisler için oluşturur. |
| `MATCH_WINDOW_HOURS` | Aday haber zaman penceresi. Varsayılan 72 saat. |
| `API_PORT`, `FRONTEND_PORT` | Compose’un localhost’a açtığı portlar. Varsayılan 8000 ve 5173. |
| `HABER_API_URL` | Yerel Vite proxy hedefi. API farklı bir portta çalışıyorsa ayarlayın. |
| `TEST_DATABASE_URL` | İsteğe bağlı PostgreSQL test adresi. Test rolünün geçici şema oluşturma yetkisi olmalıdır. |

Compose değerlerini değiştirmek için `.env.example` dosyasını `.env` olarak kopyalayın.

## Mimari

| Modül | Görev |
| --- | --- |
| `backend/app/api.py` | Kaynak ayarları, iş tetikleme, araştırma sorguları, metin karşılaştırma ve manuel kararlar |
| `backend/app/models.py`, `migrations/` | Kaynak, iş, haber, sürüm, bağlantı, grup ve üyelik şeması |
| `backend/app/queue.py` | Zamanlama, kaynak başına tek bekleyen iş, PostgreSQL satır kilidi, iş sahipliği ve yeniden deneme |
| `backend/app/network.py` | Doğrudan HTTP/TLS, DNS/IP kontrolü, robots kuralları, istek hızı ve yanıt sınırları |
| `backend/app/collectors.py` | Güvenli XML ön denetimi, RSS/Atom ayrıştırma, tarih okuma, ana metin ve bağlantı çıkarımı |
| `backend/app/worker.py` | Toplama, özetle devam etme, tekrar kontrolü, sürümleme ve sonuç yazma |
| `backend/app/analysis.py` | Türkçe normalizasyon, SHA-256, TF-IDF, kosinüs ve grup üyeliği |
| `backend/app/version_diff.py` | Paragraf hizalama, taşıma, kelime ve cümle farkları, sayı ve tarih ifadeleri |
| `backend/app/research.py`, `evolution_models.py` | Kaynak sürümüne bağlı analiz, bekleyen farklar, adaylar ve tekilleştirilmiş takip olayları |
| `backend/app/evolution_api.py` | Sayfalanan bulgular, inceleme kararları, notlar, takip ve bildirimler |
| `backend/app/report.py` | Seçili grup kanıtlarından bağımsız ve güvenli HTML raporu |
| `frontend/src/` | React sayfaları, ortak görünümler, API istemcisi, yükleme ve yenileme akışı |

API ve worker aynı veritabanı modellerini kullanır. Toplama için HTTP isteği yalnızca kuyruğa yazar. Worker işi `FOR UPDATE SKIP LOCKED` ile alır. Beş dakikalık sahiplik süresi ve işlem kimliği, yeniden alınan işte eski worker’ın sonuç yazmasını engeller. Geçici hatalar en fazla üç deneme alır. Ağ işlemleri açık veritabanı işlemi olmadan yürür. Sonuçlar, sürümler ve üyelikler tek veritabanı işleminde yazılır. Grup yazımları ve araştırmacı kararları aynı PostgreSQL işlem kilidiyle sıralanır.

## Metin analizi ve zaman

Türkçe büyük/küçük harf dönüşümü ve Unicode NFC, Türkçe harfleri korur. SHA-256 birebir içerik eşleşmesini bulur. Diğer karşılaştırmalarda tek ve ikili sözcüklerden TF-IDF oluşturulur. Bir puanlama işlemi içindeki tüm metinler aynı vektör uzayına girer. Sekiz sözcüğün altı puanlanmaz. Grup adayı seçilirken dil, örnek veri kapsamı ve bilinen yayın zamanı ya da ilk görülme zamanı kullanılır. Bir grup ancak mevcut üyelerin tamamı zaman penceresine giriyor ve yeni haberle en az 0,48 metin benzerliğine ulaşıyorsa genişler. Birden çok uygun grup varsa en zayıf üye eşleşmesi en yüksek olan grup seçilir.

Metin karşılaştırma ekranı iki metinle yeniden vektör uzayı oluşturur. Bu yüzden ekrandaki ikili puan ile daha geniş aday kümesinde hesaplanmış grup puanı farklı olabilir. Sürüm değişince otomatik üyelik tekrar değerlendirilir. Onaylanan, taşınan veya çıkarılan üyelikler araştırmacı kararına bağlı kalır.

Kaynağın bildirdiği yayın ve güncelleme zamanları, ilk gözlem ve her sürümün toplama zamanı ayrı alanlardır. Bilinen tarihler UTC saklanır ve İstanbul saatinde gösterilir. Ham tarihler tutulur. Saat dilimi belirsiz tarihler yayın sıralamasında bilinen zaman olarak kullanılmaz.

Ana metindeki açık kaynak etiketleri ve belirsiz bağlantılar ayrı gösterilir. Bağlantı URL’si toplanmış bir haberin URL’siyle eşleşirse ilgili habere geçilebilir. Benzerlik puanı bağlantı veya atıf oluşturmaz.

## Güvenlik ve sınırlar

- Ağ erişimi HTTP/HTTPS ve standart portlarla sınırlıdır. Kullanıcı bilgisi içeren URL’ler reddedilir. DNS sonuçları IPv4 ve IPv6 için denetlenir ve gerçek TCP bağlantısı denetlenen sayısal adrese açılır. TLS doğrulamasında URL’nin ana makine adı kullanılır. Her yönlendirme ve robots isteği aynı kontrolden geçer. Ortam proxy ayarları kullanılmaz.
- Ağ aşamalarında zaman ve yönlendirme sınırları vardır. Ham ve açılmış yanıtlar 2 MiB ile sınırlanır. XML’de DTD ve dış varlıklar engellenir. Ana metin tarayıcıya düz metin olarak verilir. [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html) eşleşme kuralları için [Protego](https://github.com/scrapy/protego) kullanılır.
- Tek worker, alan adı başına en az bir saniye bekler ve desteklenen robots hız kurallarını dikkate alır. Engeller, erişim kısıtları ve başarısız çıkarımlar özet kapsamına düşer. Metin çıkarımı HTTP ile sunulan HTML ile sınırlıdır. JavaScript çalıştırılmaz. URL sorgu parametreleri korunur, canonical beyanı haber kimliğini değiştirmez.
- Başlık/özet modunda ETag ve Last-Modified kullanılır. Tam metin modunda feed içeriği tekrar okunur. Böylece feed aynı kalsa da sayfadaki değişiklikler, haber feed’de kaldığı sürece gözlenebilir. Toplama başına en fazla 100 feed girdisi ve analiz başına en fazla 300 aday incelenir. Feed’den çıkmış sayfalar yeniden taranmaz.
- Örnek veri sentetiktir. Gerçek Türkçe haberlerde eş anlamlı anlatımlar kaçabilir. Benzer metin şablonları ve farklı tarihlerdeki benzer olaylar yanlış eşleşebilir.
- Kurulum yerel ve tek araştırmacı içindir. Hesap ve yetkilendirme yoktur. Compose yalnızca localhost’a port açar. SQLite önizlemesi eşzamanlı worker testi için uygun değildir.

## Testler ve değerlendirme

```sh
cd backend
python -m pytest -q
python -m app.evaluate
python -m alembic check
```

Varsayılan testler internet kullanmaz ve RSS/Atom/HTML fixture’larıyla çalışır. `TEST_DATABASE_URL` verildiğinde veritabanı testleri PostgreSQL’de geçici şemalarda çalışır ve eşzamanlı iş alma testi de etkinleşir. PostgreSQL rolü geçici şema oluşturup silebilmelidir.

Haber evrimi akışını ayrı çalıştırmak için `python -m pytest -q tests/test_evolution.py` kullanın. Testler değişen fixture sürümünden rapora kadar akışı, manuel kararların korunmasını ve HTML kaçışını denetler.

```sh
cd frontend
npm ci
npm run typecheck
npm run build
```

`backend/evaluation.json` elle olay etiketleri verilen 14 kurgusal Türkçe haber içerir. Değerlendirme tüm 91 çifti aynı vektör uzayında puanlar, birden fazla eşiği karşılaştırır ve seçili eşikte yanlış eşleşmeleri ve kaçırılan çiftleri kimlikleriyle yazar. Çift puanları grup tutarlılığı kuralı uygulanmadan ölçülür.

| Eşik | Doğru eşleşme | Doğru ayrım | Yanlış eşleşme | Kaçırılan eşleşme |
| --- | ---: | ---: | ---: | ---: |
| 0,20 | 4 | 79 | 4 | 4 |
| 0,30 | 4 | 81 | 2 | 4 |
| 0,40 | 4 | 81 | 2 | 4 |
| **0,48** | **4** | **81** | **2** | **4** |
| 0,55 | 2 | 82 | 1 | 6 |
| 0,65 | 2 | 82 | 1 | 6 |

0,48 bu küçük kümede daha düşük eşiklerle aynı sayıda doğru eşleşmeyi korur. 0,55’e çıkmak bir yanlış eşleşmeyi elerken iki doğru çifti kaybettirir. 0,48’de yanlış eşleşen çiftler S1–S4 (0,826) ve S2–S4 (0,531). Kaçırılan çiftler S1–S3 (0,072), S2–S3 (0,145), T1–T3 (0,052) ve T2–T3 (0,072). S4 farklı bir sel olayı için benzer bir haber kalıbı kullanır. S3 ve T3 aynı olayı farklı sözcüklerle anlatır. Bu ölçüm küçük bir sentetik karşılaştırmadır.

