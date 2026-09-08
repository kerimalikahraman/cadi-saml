# CADi SAML geliştirme planı

## Uygulama sırası

1. [x] Temel kalite ve gözlemlenebilirlik: kurulum, sürüm ve solver sağlığını raporlamak.
2. [x] FEA güvenilirliği: benchmark ve mesh yakınsaması giriş doğrulamalarını güçlendirmek.
3. [x] Büyük montaj performansı: cache ve spatial index yaşam döngüsü doğrulamalarını eklemek.
4. [x] Kinematik kapsamı: mate girdileri, DOF ve duplicate mate tanılarını güçlendirmek.
5. [ ] Analiz modülleri: termal, modal, yorulma, burkulma ve CFD sözleşmelerini ortaklaştırmak.
6. [x] Ürünleşme: temel public diagnostics API’si ve CI akışı.

## Bu iterasyon

`cadi_saml.diagnostics.environment_report()` eklenecek. API; CADi SAML, Python,
kritik bağımlılıkları ve CalculiX durumunu JSON uyumlu olarak döndürecek.
