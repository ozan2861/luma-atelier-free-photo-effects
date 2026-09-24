# Güvenlik Politikası

Luma Atelier çevrimdışı çalışır; uygulama kodu fotoğrafları, dosya yollarını
veya kullanım verilerini bir ağ hizmetine göndermez.

## Açık bildirme

Bir güvenlik açığı bulursanız ayrıntıları herkese açık bir issue içinde
paylaşmayın. GitHub deposundaki **Security → Report a vulnerability** yolunu
kullanarak özel bildirim gönderin. Etkiyi, yeniden üretme adımlarını ve varsa
örnek dosyayı ekleyin; gerçek parola, anahtar veya kişisel fotoğraf eklemeyin.

## Otomatik kontroller

Her değişiklikte aşağıdaki kontroller çalışır:

- yerel secret, kişisel yol ve uygulama-ağı politikası taraması;
- Bandit orta/yüksek önem statik analizi;
- pip-audit çalışma zamanı bağımlılığı taraması;
- kötü niyetli proje arşivi ve tür doğrulama regresyon testleri.

Güvenlik araçları yalnızca geliştirme/CI ortamındadır ve paketlenmiş uygulamanın
çalışma zamanı bağımlılıklarına dahil edilmez.
