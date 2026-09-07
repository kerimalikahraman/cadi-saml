# CADi SAML — CFD ve Gelecek Geliştirme Planı

Bu belge, CADi SAML kütüphanesini parametrik CAD üretiminden analiz yapabilen bir mühendislik asistanına dönüştürmek için oluşturulmuştur.

## Mevcut hedef

Kütüphane yalnızca geometri üretmemeli; üretilen modelin akış, ısı, dayanım, üretilebilirlik ve montaj açısından uygunluğunu da inceleyebilmelidir.

LLM akışı şu şekilde olmalıdır:

```text
Mühendislik şartnamesi
→ parametrik CAD modeli
→ analiz sınır şartları
→ hesap veya simülasyon
→ sonuçların CAD/FEA modeline aktarılması
→ contract doğrulaması
→ gerekiyorsa parametrik düzeltme
```

## CFD ve akış analizi yol haritası

İlk aşamada tam 3B CFD çözücüsü yazılmayacak. Önce hızlı ve açıklanabilir analitik hesaplar eklenecek.

### 1. Boru akışı

Eklenecek girdiler:

- boru çapı
- boru uzunluğu
- debi veya giriş hızı
- basınç
- sıcaklık
- akışkan türü
- pürüzlülük

Hesaplanacak sonuçlar:

- akış hızı
- Reynolds sayısı
- laminer/türbülanslı rejim
- sürtünme katsayısı
- basınç kaybı
- pompa gücü
- önerilen çap

Örnek API:

```python
result = analyze_pipe_flow(
    diameter=25.0,
    length=1200.0,
    flow_rate=0.002,
    fluid="water",
)
```

### 2. Boru elemanları

Piping makrolarıyla bağlanacak kayıplar:

- dirsek
- T bağlantısı
- vana
- filtre
- ani genişleme
- ani daralma
- toplam sistem basınç kaybı

### 3. Isıl analiz

İlk termal modül şu hesapları desteklemeli:

- iletim
- taşınım
- radyasyon
- sıcaklık dağılımı
- termal genleşme
- soğutma performansı

Örnek API:

```python
thermal = analyze_thermal_model(
    material="Aluminum6061",
    ambient_temperature=25.0,
    heat_load=500.0,
    convection_coefficient=20.0,
)
```

### 4. Hidrolik sistem

- pompa-basınç ilişkisi
- vana ve filtre kayıpları
- silindir hareket hızı
- hidrolik güç
- kavitasyon riski

### 5. Fan ve hava kanalı

- fan debisi
- kanal basınç kaybı
- soğutma performansı
- kutu içi sıcaklık bölgeleri

### 6. CFD/FEA bağlantısı

İleri aşamada akış çözümünden elde edilen basınç yükleri FEA’ya aktarılmalı:

```text
CFD → yüzey basıncı → FEA → deformasyon → geometri güncelleme
```

Örnek kullanım alanları:

- kanat üzerindeki hava yükü
- boru dirseğindeki basınç kuvveti
- fan kanadı gerilmesi
- basınçlı kap deformasyonu

## Önerilen yeni paket yapısı

```text
src/cadi_saml/
├── simulation/
│   ├── flow.py
│   ├── thermal.py
│   ├── hydraulic.py
│   ├── fluid_properties.py
│   ├── boundary_conditions.py
│   ├── mesh.py
│   ├── results.py
│   └── coupling.py
```

## LLM için gerekli davranış

Model şu tip talepleri karşılayabilmeli:

> DN50 boruda 2 litre/saniye su akışı için basınç kaybını hesapla. Çap yetersizse yeni çap öner ve sonucu CAD modeline işle.

Beklenen işlem sırası:

1. Şartnameyi oku.
2. Boru geometrisini bul.
3. Akışkan özelliklerini seç.
4. Akış hesabını yap.
5. Basınç kaybını kontrol et.
6. Yetersizse alternatif çap hesapla.
7. Seçilen değeri provenance ile kaydet.
8. CAD modelini parametrik olarak güncelle.
9. Post-build contract çalıştır.
10. Sonucu açık ve yapılandırılmış biçimde raporla.

## Uygulama sırası

1. Akışkan özellikleri veritabanı
2. Boru basınç kaybı hesapları
3. Reynolds ve akış rejimi analizi
4. Boru elemanı kayıp katsayıları
5. Temel ısı transferi
6. Sınır şartı modeli
7. Mesh üretimi
8. OpenFOAM veya SU2 dışa aktarma/geri alma
9. CFD sonuçlarını FEA ve CAD’e bağlama
10. Akış kaybı, ağırlık ve soğutma için optimizasyon

## Öncelikli teknik iyileştirmeler

- Analitik analiz sonuçlarını `PostBuildContract` içine bağlamak.
- Her analiz girdisi ve sonucu için provenance tutmak.
- Birim dönüşümlerini zorunlu ve açık yapmak.
- Eksik akışkan veya sınır şartında geometri uydurmamak.
- Sonuçları JSON, insan okunabilir rapor ve CAD parametre patch’i olarak sunmak.
- Hesapların varsayımlarını ve geçerlilik aralıklarını raporlamak.

## Mevcut kütüphane için sonraki büyük adımlar

CFD’den önce şu temel yetenekler tamamlanmalı:

- gerçek feature tree geçmişinin korunması
- sketch constraint çözümünün genişletilmesi
- montaj DOF ve mate sisteminin birleştirilmesi
- geometri sorgulama API’sinin genişletilmesi
- DFM/GD&T sonuçlarının contract’a tam bağlanması
- patch ve analiz sonuçlarının aynı parametrik model üzerinde çalışması

Bu belge sonraki geliştirme konuşmalarında ana plan olarak kullanılacaktır.

## Ortak analiz mimarisi

On altı analiz başlığı ayrı ve kopuk fonksiyonlar olarak değil, aynı mühendislik akışına bağlı çalışmalar olarak tasarlanmalıdır:

```text
Geometri
→ malzeme
→ yükler ve sınır şartları
→ analiz
→ sonuç
→ kabul kriteri
→ tasarım değişikliği
→ yeniden analiz
```

### Analiz seviyeleri

#### Seviye 1 — Hızlı analitik hesaplar

Mil çapı, dişli gerilmesi, rulman ömrü, cıvata ön yükü, basınçlı kap cidarı, tolerans ve boru basınç kaybı gibi hesaplar burada çalışır. Bu seviye hızlı, açıklanabilir ve LLM için uygundur.

#### Seviye 2 — Sayısal mühendislik çözümleri

Mevcut FEA ile birlikte modal, burkulma, termal ve yorulma analizleri bu seviyede yer alır. Mesh, sınır şartı ve yakınsama kontrolü zorunludur.

#### Seviye 3 — Harici çözücüler

CFD, ileri temas, nonlineer malzeme, akustik ve karmaşık dinamik problemler OpenFOAM, CalculiX, Code_Aster, SU2 veya benzeri çözücülere aktarılır.

### Ortak `AnalysisStudy` modeli

Tüm analizler aynı temel çalışma nesnesini kullanmalıdır:

```python
study = AnalysisStudy(
    name="powertrain_validation",
    assembly=asm,
    material="42CrMo4",
    units="mm-N-MPa",
)

study.add_static_load(...)
study.add_boundary_condition(...)
study.add_acceptance_criterion(...)
result = study.solve()
```

Aynı çalışma üzerinden birden çok analiz çalıştırılabilmelidir:

```python
study.run("static")
study.run("fatigue")
study.run("critical_speed")
study.run("bearing_life")
```

### Ortak veri yapıları

- `MaterialModel`
- `LoadCase`
- `BoundaryCondition`
- `MeshSettings`
- `AnalysisResult`
- `AcceptanceCriteria`
- `ProvenanceRecord`
- `SensitivityReport`

Her analiz sonucu yalnızca geçti/kaldı bilgisi vermemelidir:

```json
{
  "status": "FAIL",
  "critical_value": 1.42,
  "required_value": 2.0,
  "critical_location": "shaft.step_2",
  "assumptions": ["linear elastic material"],
  "sensitivity": {"torque": "high"},
  "suggested_changes": [
    {"parameter": "diameter", "value": 32.0}
  ]
}
```

### Analizler arası veri akışı

```text
Mil hesabı → dişli ve rulman yükleri
Dişli hesabı → mil torku ve yatak kuvvetleri
CFD → FEA yüzey basıncı
Termal analiz → termal FEA sıcaklık alanı
Modal analiz → motor devriyle rezonans karşılaştırması
Statik analiz → yorulma analizinin gerilme girdisi
Tüm sonuçlar → optimizasyon hedefleri
```

Güç aktarım sistemi örneği:

```text
Güç + devir
→ tork
→ dişli kuvvetleri
→ mil gerilmesi
→ rulman yükleri
→ rulman ömrü
→ kritik devir
→ yorulma ömrü
→ güvenlik kararı
```

### İlk ortak altyapı paketi

```text
simulation/
├── base.py
├── results.py
├── load_cases.py
├── acceptance.py
└── coupling.py
```

Bu altyapı kurulduktan sonra mevcut FEA, mil, dişli, rulman ve tolerans analizleri ortak sisteme bağlanmalı; modal, yorulma, termal ve CFD modülleri bunun üzerine eklenmelidir.

### Güvenilirlik kuralları

- Kütüphane tam CFD veya ileri nonlineer FEA’yı ilk aşamada kendi içinde yeniden yazmamalıdır.
- Analitik ve çözücü tabanlı sonuçlar ayrı açıkça belirtilmelidir.
- Her analiz geçerlilik aralığını ve varsayımlarını raporlamalıdır.
- Yakınsamayan sonuçlar başarılı gösterilmemelidir.
- Eksik yük veya sabitleme bilgisi varsayımla doldurulmamalıdır.
- Analizler arası birim ve koordinat dönüşümü doğrulanmalıdır.
- Fiziksel olarak doğrulanmamış optimizasyon sonucu en iyi tasarım olarak sunulmamalıdır.

### Nihai LLM akışı

```text
LLM şartnameyi okur
→ CAD modelini oluşturur
→ yükleri ve sınır şartlarını çıkarır
→ uygun analiz seviyesini seçer
→ sonucu yorumlar
→ başarısızsa parametrik düzeltme önerir
→ modeli günceller
→ analizleri tekrarlar
→ onaylanabilir CAD ve mühendislik raporu üretir
```

## Mevcut FEA altyapısı

FEA kütüphanede zaten bulunmaktadır. Yeni hedef FEA eklemek değil, mevcut yapısal analiz motorunu daha gelişmiş analizlerle genişletmektir.

Mevcut dosyalar:

- `src/cadi_saml/analysis/fea.py`
- `src/cadi_saml/analysis/solver.py`
- `src/cadi_saml/analysis/materials.py`
- `tests/test_fea_analysis.py`
- `tests/test_fea_visualization.py`

Mevcut FEA akışı:

```text
OpenCASCADE katısı
→ Gmsh tetrahedral mesh
→ yüzey sabitleme
→ kuvvet uygulama
→ lineer elastik çözüm
→ Von Mises gerilmesi ve deplasman
→ emniyet katsayısı
→ VTK/HTML raporu
```

Örnek kullanım:

```python
fea = asm.add_fea_study(
    "bracket",
    material="S235JR",
    mesh_size=4.0,
)

fea.fix_face("z_min")
fea.apply_force(
    face="x_max",
    force_vector=(0.0, 0.0, -300.0),
)

result = fea.solve()
```

Mevcut FEA testleri şunları kapsar:

- Euler-Bernoulli kiriş ile analitik karşılaştırma
- sac braket statik analizi
- aşırı yükte akma uyarısı
- mesh iyileştikçe sonuçların yakınsaması
- VTK dışa aktarma
- interaktif HTML sonuç görüntüleme

## Eklenecek FEA analizleri

### Modal analiz

Parçanın doğal titreşim frekanslarını ve rezonans riskini hesaplar.

```python
modal = ModalStudy(asm, part="fan_housing")
modal_result = modal.solve(mode_count=6)
```

Kontrol edilecek sonuçlar:

- doğal frekanslar
- mod şekilleri
- rezonans riski
- motor veya fan çalışma frekansıyla çakışma

### Burkulma analizi

İnce kolon, levha ve şasilerin basınç altında kararlılığını kontrol eder.

```python
buckling = BucklingStudy(asm, part="column")
buckling.fix_face("z_min")
buckling.apply_compressive_force("z_max", 12000.0)
result = buckling.solve(mode_count=3)
```

### Yorulma analizi

Tekrarlı yüklerde parçanın ömrünü hesaplar.

Girdiler:

- minimum ve maksimum yük
- çevrim sayısı
- malzeme yorulma eğrisi
- yüzey etkisi
- çentik etkisi

Sonuçlar:

- tahmini çevrim ömrü
- yorulma emniyet katsayısı
- kritik bölgeler
- hasar birikimi

### Termal gerilme

Sıcaklık dağılımının oluşturduğu genleşme ve gerilmeyi hesaplar.

```text
Termal çözüm
→ sıcaklık alanı
→ malzeme genleşmesi
→ mekanik FEA
→ termal gerilme ve deformasyon
```

### Temas ve bağlantı analizi

Şu temas türleri desteklenmeli:

- bonded
- frictionless
- frictional
- bolt preload
- press fit
- bearing contact

Özellikle rulman, cıvata, kaplin ve pres geçme bağlantıları için gereklidir.

### Dinamik ve titreşim analizi

- zamanla değişen kuvvet
- motor titreşimi
- balanssızlık
- darbe yükü
- harmonik cevap
- transient response

### Nonlineer analiz

İleri aşamada:

- plastik deformasyon
- büyük deformasyon
- temas nonlineerliği
- malzeme akması
- kauçuk ve elastomer modelleri

## CFD ile FEA bağlantısı

CFD ve FEA birbirinden bağımsız çalışmamalıdır. Akış analizinden çıkan basınçlar FEA yüzey yüklerine dönüştürülmelidir.

```text
CAD geometrisi
→ akış hacmi oluşturma
→ CFD mesh
→ hız, basınç ve sıcaklık çözümü
→ basınç dağılımını CAD yüzlerine eşleme
→ FEA mesh’ine yük aktarımı
→ gerilme/deformasyon hesabı
→ emniyet kontrolü
→ gerekiyorsa parametrik CAD güncellemesi
```

Örnek kullanım alanları:

- fan kanadı üzerindeki hava yükü
- kanat veya gövde basınç dağılımı
- boru dirseği basınç kuvveti
- pompa gövdesi yükleri
- radyatör ve soğutucu deformasyonu
- basınçlı kap sıcaklık ve gerilme analizi

## FEA ve CFD için ortak veri modeli

Her analiz aynı geometri ve sınır şartı modeliyle çalışmalıdır:

```json
{
  "geometry": "assembly_name",
  "material": "42CrMo4",
  "units": "mm-N-MPa",
  "boundary_conditions": [],
  "loads": [],
  "thermal_conditions": [],
  "fluid_conditions": [],
  "mesh_settings": {},
  "acceptance_criteria": {}
}
```

Her analiz sonucu provenance taşımalıdır:

- kullanılan geometri sürümü
- mesh ayarı
- malzeme kaynağı
- sınır şartı kaynağı
- çözücü versiyonu
- yakınsama durumu
- geçerlilik aralığı

## FEA sonuçlarının contract’a bağlanması

Post-build contract içine aşağıdaki aşamalar eklenmelidir:

```text
FEA mesh validity
→ boundary condition validity
→ load completeness
→ solver convergence
→ stress limit
→ displacement limit
→ safety factor
→ result provenance
```

Örneğin:

```python
report = asm.verify_contract(
    test_fea=True,
    fea_require_safety_factor=2.0,
    fea_max_displacement_mm=0.5,
)
```

Eksik yük, sabitleme veya malzeme varsa sistem geometri uydurmamalı; yapılandırılmış hata döndürmelidir.

## FEA geliştirme sırası

1. Modal analiz
2. Burkulma analizi
3. Yorulma analizi
4. Termal gerilme
5. Temas ve cıvata ön yükü
6. Dinamik/titreşim analizi
7. CFD basınç yükü aktarımı
8. Nonlineer malzeme ve temas
9. FEA sonucuna göre otomatik optimizasyon

## Önerilen analiz paketleri

```text
src/cadi_saml/
├── simulation/
│   ├── flow.py
│   ├── thermal.py
│   ├── structural.py
│   ├── modal.py
│   ├── buckling.py
│   ├── fatigue.py
│   ├── vibration.py
│   ├── contact.py
│   ├── hydraulic.py
│   ├── mesh.py
│   ├── boundary_conditions.py
│   ├── results.py
│   └── coupling.py
```

## LLM örnek akışı

Kullanıcı:

> Bu 7,5 kW güç aktarım milini kontrol et; burulma, yorulma, rulman ömrü ve kritik devri hesapla. Daha sonra boru üzerindeki basınç yükünü FEA’ya aktar.

Sistem:

1. CAD modelini okur.
2. Mil geometrisini ve malzemeyi bulur.
3. Burulma hesabı yapar.
4. Mevcut FEA ile gerilme ve deformasyonu çözer.
5. Yorulma ve kritik devir analizini yapar.
6. CFD veya boru akışı analizinden gelen basıncı alır.
7. Basıncı FEA yüzeylerine aktarır.
8. Emniyet katsayısını kontrol eder.
9. Uygun değilse parametrik çap veya kalınlık değişikliği önerir.
10. Yeni modeli tekrar contract doğrulamasından geçirir.

## Diğer analiz ve mühendislik geliştirmeleri

### Birim ve fiziksel boyut sistemi

Her sayısal değer birim ve fiziksel tür bilgisi taşımalıdır. Uzunluk, kuvvet, tork, basınç, sıcaklık, debi, güç ve gerilme birbirine karıştırılmamalıdır.

```json
{
  "value": 25.0,
  "unit": "mm",
  "quantity": "length"
}
```

Birim belirtilmemiş veya fiziksel olarak uyumsuz değerler strict modda reddedilmelidir.

### Tasarım niyeti

LLM’den yalnızca ölçüler değil, tasarım amacı da alınmalıdır:

```json
{
  "function": "torque_transmission",
  "priority": "low_weight",
  "safety_factor": 2.0,
  "manufacturing_process": "CNC"
}
```

Bu bilgiler analiz ve optimizasyon kararlarında kullanılmalıdır.

### Tasarım alternatifleri ve optimizasyon

Tek model yerine farklı hedeflere göre alternatifler üretilebilmelidir:

- düşük ağırlık
- yüksek emniyet
- düşük maliyet
- düşük basınç kaybı
- kolay üretim
- uzun ömür

Her alternatif ağırlık, maliyet, malzeme, emniyet katsayısı, üretim süresi ve analiz sonuçlarıyla karşılaştırılmalıdır.

### Üretilebilirlik ve maliyet analizi

Geometriye göre uygun üretim süreci önerilmelidir:

- CNC freze
- torna
- lazer kesim
- sac büküm
- döküm
- kaynak
- 3D baskı
- enjeksiyon

BOM sistemi malzeme miktarı, standart parça sayısı, işlem süresi ve yaklaşık maliyet bilgileriyle genişletilmelidir.

### Dependency ve etki analizi

Bir parametre değiştiğinde etkilenen tüm parçalar ve analizler raporlanmalıdır:

```text
Mil çapı değişti
→ kama değişti
→ rulman değişti
→ kaplin deliği değişti
→ tork gerilmesi değişti
→ maliyet değişti
```

LLM için `impact_report` şu bilgileri vermelidir:

- etkilenen parçalar
- etkilenen feature’lar
- bozulan kısıtlar
- hacim ve ağırlık farkı
- analiz sonuçlarındaki değişim
- yeniden çalıştırılması gereken analizler

### Belirsizlik ve hassasiyet analizi

Analiz sonucu yalnızca tek sayı olarak verilmemelidir. Giriş toleransı, yük değişimi, malzeme belirsizliği ve mesh hassasiyeti raporlanmalıdır.

```json
{
  "safety_factor": 2.15,
  "confidence": 0.91,
  "sensitivity": {
    "load": "high",
    "material": "medium",
    "mesh": "low"
  }
}
```

### Gelişmiş hareket ve bağlantı analizi

Kinematik sisteme şu elemanlar eklenmelidir:

- yay
- amortisör
- zincir
- kayış
- kam takipçisi
- kablo ve hortum hareketi
- mekanik durdurucu
- limit switch

Bağlantı modelleri ön yük, sürtünme, pres geçme, gevşeme, kaynak ve yapıştırıcı bağlantılarını kapsamalıdır.

### Malzeme davranışı

Malzeme veritabanına sıcaklık bağımlılığı, plastik deformasyon, yorulma eğrileri, sürünme, elastomer ve kompozit yön bağımlılığı eklenmelidir.

### Revision ve geri alma sistemi

LLM’in çok adımlı tasarım süreci revision olarak saklanmalıdır:

```text
Revision 1: taban oluşturuldu
Revision 2: delik eklendi
Revision 3: mil çapı değişti
Revision 4: analiz sonucuna göre kalınlık artırıldı
```

Her revision için parametrik diff, contract sonucu ve analiz raporu tutulmalıdır. Kullanıcı herhangi bir revision’a geri dönebilmelidir.

### İnsan onay noktaları

Şu kararlar otomatik uygulanmadan önce seçenek olarak sunulmalıdır:

- standart parça seçimi
- malzeme değişikliği
- emniyet katsayısı düşükken geometri değişikliği
- üretim süreci değişikliği
- yüksek maliyet etkili optimizasyon

### Gelişmiş geometri hata teşhisi

Sistem şu hataları yüz veya feature seviyesinde raporlamalıdır:

- kendi kendine kesişen yüzey
- açık shell
- sıfır kalınlık
- başarısız boolean
- ters normal
- bozuk sketch profili
- kopuk montaj

Her hata için parça, feature, parametre, hata kodu ve düzeltme önerisi verilmelidir.

### Plugin ve çözücü mimarisi

Harici analiz çözücüleri plugin olarak bağlanmalıdır:

```text
simulation_plugins/
├── openfoam/
├── su2/
├── calculix/
├── gmsh/
└── custom_solver/
```

CAD çekirdeği çözücüye bağımlı olmamalı; mesh, sınır şartı, sonuç ve provenance arayüzleri ortak kalmalıdır.

### LLM sandbox güvenliği

LLM tarafından üretilen CAD ve analiz kodu için:

- izin verilen import listesi
- dosya erişim kısıtlaması
- çalışma süresi ve bellek sınırı
- subprocess izolasyonu
- ağ erişimi kontrolü

uygulanmalıdır.

## Genel hedef akışı

```text
Şartnameyi anla
→ tasarım niyetini çıkar
→ birimleri doğrula
→ parametrik modeli oluştur
→ geometriyi incele
→ CFD/FEA ve mühendislik hesaplarını çalıştır
→ üretilebilirlik ve maliyeti kontrol et
→ alternatif tasarımlar üret
→ kullanıcı onayı al
→ revision kaydet
→ nihai CAD ve mühendislik raporunu üret
```

Bu başlıklar, gelecekte yeni analiz veya kütüphane geliştirmesi konuşulduğunda aynı plan dosyasına eklenmeye devam edecektir.

## STEP dosyasını CADi SAML modeline dönüştürme

STEP dosyasını doğrudan düzenlenebilir CAD koduna çevirmek için yalnızca yüzeyleri okumak yeterli değildir. Amaç, ham B-Rep geometrisini CADi SAML’in parametrik IR ve feature tree yapısına dönüştürmektir.

### Önerilen dönüşüm akışı

```text
STEP dosyası
→ OpenCASCADE STEP import
→ parça ve solid ayrıştırma
→ yüzey/kenar/vertex analizi
→ geometrik feature tanıma
→ parametre çıkarma
→ feature tree oluşturma
→ semantic port ve mate çıkarma
→ CADi SAML IR üretme
→ yeniden derleme
→ STEP karşılaştırması
→ düzenlenebilir Python/SAML kodu
```

### 1. STEP import ve güvenli ayrıştırma

`STEPFeatureRecognizer` şu bilgileri çıkarmalıdır:

- parça adı
- solid sayısı
- yüzey tipleri
- silindirik ve düz yüzeyler
- delik ve boss adayları
- eksenler
- simetri düzlemleri
- bounding box
- kütle merkezi
- bağlantı yüzeyleri
- renk ve malzeme metadata’sı

Her STEP dosyası import sonrasında manifold ve birim kontrolünden geçirilmelidir.

### 2. Geometrik feature tanıma

Tanıma sırası basitten karmaşığa ilerlemelidir:

1. Box ve prizmatik taban
2. Silindir, koni, küre ve torus
3. Delik, counterbore ve countersink
4. Cep ve çıkıntı
5. Fillet ve chamfer
6. Pattern ve mirror
7. Sac metal bükümleri
8. Dişli, mil, kama ve standart parçalar
9. Loft ve sweep
10. Tanınamayan serbest biçimli yüzeyler

Tanıma sonucu doğrudan kesin kabul edilmemeli; her feature için güven skoru tutulmalıdır:

```json
{
  "feature": "HoleFeature",
  "parameters": {"diameter": 10.0, "depth": 25.0},
  "confidence": 0.97,
  "evidence": ["cylindrical_inner_face", "coaxial_end_faces"]
}
```

### 3. Parametrik feature tree yeniden oluşturma

STEP dosyası genellikle tasarım geçmişini içermez. Bu nedenle çıkarılan feature’lar olasılıksal bir geçmiş olarak kurulmalıdır:

```text
BasePad
→ Pocket
→ Hole
→ CircularPattern
→ Fillet
→ Chamfer
```

Her feature için:

- parent feature
- giriş yüzleri
- parametreler
- bağımlılıklar
- güven skoru
- `source="step_recognition"` provenance kaydı

tutulmalıdır.

Güven skoru düşük feature’lar kullanıcı onayı olmadan düzenlenebilir kabul edilmemelidir.

### 4. CADi SAML IR üretimi

Çıktı, doğrudan Python string’i değil önce makine tarafından doğrulanabilir IR olmalıdır:

```json
{
  "parts": [
    {
      "name": "housing",
      "features": [
        {"type": "pad", "length": 100.0, "width": 60.0, "height": 20.0},
        {"type": "hole", "diameter": 10.0, "depth": 15.0}
      ],
      "ports": [
        {"name": "top_face", "type": "planar", "normal": [0, 0, 1]}
      ]
    }
  ],
  "recognition_metadata": {
    "source_file": "input.step",
    "confidence": 0.91,
    "unrecognized_regions": []
  }
}
```

Bu IR daha sonra:

- CADi SAML Assembly’ye
- feature tree’ye
- Python koduna
- yeni dataset kaydına

dönüştürülebilmelidir.

### 5. Yeniden derleme ve geometrik eşleştirme

Tanıma sonucunda oluşturulan parametrik model tekrar OpenCASCADE ile derlenmeli ve orijinal STEP ile karşılaştırılmalıdır:

- solid sayısı
- hacim
- bounding box
- kütle merkezi
- yüzey alanı
- delik eksenleri
- kritik çap ve uzunluklar
- parça konumları

Karşılaştırma tolerans içinde değilse feature tree güvenilmez olarak işaretlenmelidir.

### 6. STEP üzerinde değişiklik yapma

Kullanıcı STEP dosyası üzerinde doğrudan yüzey düzenlemek yerine tanınan parametrik model üzerinde patch uygulamalıdır:

```python
model = STEPReverseEngineer("input.step").to_assembly()

proposal = model.preview_patch({
    "housing.features[1].diameter": 12.0,
    "housing.features[1].depth": 18.0,
})

model.apply_patch(proposal)
model.verify_contract(strict=True)
model.export_step("modified.step")
```

Tanınamayan serbest biçimli bölgeler korunmalı; yalnızca güvenilir parametrik feature’lar değiştirilmelidir.

### 7. STEP’ten dataset üretimi

STEP dosyası dataset için şu üç biçimde kullanılabilir:

#### Gold reconstruction sample

```text
STEP → tanıma → CADi SAML kodu → yeniden oluşturma → geometrik karşılaştırma
```

#### Edit/patch sample

```text
STEP + değişiklik talebi → parametrik patch → yeni STEP → doğrulama
```

#### Negative recognition sample

```text
STEP → düşük güvenli veya çelişkili feature → kullanıcı onayı/hata çıktısı
```

Dataset kaydında şunlar bulunmalıdır:

- STEP dosya checksum’ı
- kaynak birim sistemi
- tanınan feature listesi
- güven skorları
- unrecognized region listesi
- üretilen IR
- üretilen kod
- yeniden derleme toleransları
- karşılaştırma raporu

### 8. Belirsizlik yönetimi

STEP dosyasından orijinal tasarım niyeti her zaman çıkarılamaz. Sistem şu durumları açıkça ayırmalıdır:

- kesin tanınan feature
- yüksek güvenli tahmin
- düşük güvenli tahmin
- serbest biçimli ve parametrikleştirilemeyen bölge
- kullanıcı onayı gereken alan

LLM’e şu tür çıktı verilmelidir:

```json
{
  "status": "needs_review",
  "recognized": 18,
  "uncertain": 3,
  "unrecognized": 1,
  "questions": [
    "Bu 12 mm silindirik yüzey bir delik mi yoksa yatak yuvası mı?"
  ]
}
```

### 9. Önerilen yeni modüller

```text
src/cadi_saml/reverse/
├── step_importer.py
├── step_recognizer.py
├── feature_classifier.py
├── parameter_extractor.py
├── assembly_reconstructor.py
├── geometry_matcher.py
└── recognition_report.py
```

### 10. Uygulama sırası

1. STEP import ve solid envanteri
2. Silindir/düzlem/delik tanıma
3. Parametre çıkarma
4. CADi SAML IR üretimi
5. Feature tree reconstruction
6. Yeniden derleme ve geometri karşılaştırması
7. Patch ile düzenleme
8. Güven skoru ve kullanıcı onayı
9. STEP tabanlı gold/negative dataset üretimi
10. Serbest biçimli yüzey ve karmaşık feature desteği

## STEP dönüşümü: mimari kararların derinleştirilmesi — 6 Eylül 2026

Bu bölüm bir uygulama önerisidir; burada tarif edilen yeteneklerin kodda tamamlandığı anlamına gelmez. Önceki bölümdeki API, dosya yapısı ve güven skoru örnekleri taslak olarak değerlendirilmelidir. Özellikle örnek güven skorları ölçülmüş doğruluk olasılıkları değildir.

### 1. Ürünün amacı ve sınırı

Hedef, STEP dosyasını sadece açmak veya Python içinden tekrar yüklemek değil; geometrisi doğrulanabilen, belirli parametreleri değiştirilebilen ve eğitim verisi olarak izlenebilen bir modele dönüştürmektir.

STEP üzerinden gelen son geometriden orijinal işlem geçmişini tekil biçimde çıkarmak genellikle mümkün değildir. Aynı parça farklı eskiz, ekstrüzyon, döndürme ve Boolean işlemleriyle üretilebilir. Bu nedenle ürünün vaadi "orijinal kodu kurtarmak" değil, "kaynak şekle eşdeğer ve desteklenen değişiklikleri yapabilen bir temsil üretmek" olmalıdır.

Üç bilgi türü ayrı tutulmalıdır:

- Ölçülen: yüzey türü, çap, konum, eksen, hacim, komşuluk; ölçüm toleransı ve kaynak referansı ile.
- Yorumlanan: bu yüzeylerin bir delik, cep, flanş veya tekrar eden düzen oluşturduğu hipotezi; alternatifleri ve doğrulama durumu ile.
- Bildirilen: malzeme, yük, tolerans, rulman görevi veya üretim amacı; dosyada açık metadata ya da kullanıcı şartnamesi varsa kaynağıyla.

Silindirik bir boşluk geometriden bulunabilir; bunun rulman yuvası olduğu, hangi geçmenin gerektiği veya hangi torku taşıdığı yalnızca şekilden kesinleştirilemez. Montaj konumları da hareketli mafsal veya montaj kısıtlarını tek başına kanıtlamaz.

### 2. Varsayılan çözüm: orijinali koruyan hibrit model

Tam parametrik yeniden kurma, düzenleme yapabilmenin ön koşulu olmamalıdır. Önceki uygulama sırası bu ilkeye göre güncellenmelidir.

1. Kaynak STEP ve içe aktarılmış B-Rep değişmez bir başlangıç modeli olarak saklanır.
2. Parça tanımları, montaj örnekleri, birimler ve dönüşümler envantere alınır.
3. Tanınan bölgelerin üzerine anlamlı kimlikler ve düzenleme yetenekleri eklenir.
4. Desteklenen değişiklikler kaynak model üzerine izlenebilir işlemler olarak uygulanır.
5. Tam parametrik temsil, yalnızca yeniden üretim doğrulamasını geçen parça veya bölgeler için sunulur.

Örneğin karmaşık döküm gövdede altı basit delik tanınabiliyorsa, gövdenin bütün üretim geçmişini çözmeden desteklenen delik değişiklikleri yapılabilir. Ancak deliği daraltmak, büyütmek kadar basit olmayabilir: mevcut boşluğu doldurma ve tekrar kesme işlemlerinin komşu boşlukları etkilemediği ayrıca kanıtlanmalıdır. Sistem her tanınan feature için desteklenen işlemleri ayrı açıklamalıdır.

Tanınmayan serbest biçimli yüzeyler yaklaşık kutu/silindir ile değiştirilmez. Kaynak gövde korunur; desteklenmeyen değişiklik açık gerekçeyle reddedilir.

Çıktı türleri ayrı isimlendirilmelidir:

- Kaynak varlığına bağımlı kod paketi: Python + STEP/BREP + manifest + dosya özetleri. Yeniden çalıştırılabilir fakat bağımsız parametrik üretim değildir.
- Hibrit düzenleme paketi: kaynak varlık + tanınmış özellikler + düzenleme geçmişi + doğrulama raporu.
- Bağımsız parametrik kod: kaynak STEP yüklemeden modeli kurar; yalnızca yeterli yeniden kurma ve doğrulama varsa bu etiketi alır.

### 3. Kimlik, montaj ve koordinat sözleşmesi

Yüz veya kenarlar liste sırası ile kalıcı olarak adreslenmemelidir. Bir Boolean işlemi yüzleri bölebilir, birleştirebilir veya sıralamayı değiştirebilir.

- Kalıcı feature kimliği, kaynak gövde kimliği ve montaj örneği yolu tutulur.
- Geometri çekirdeğinin generated/modified/deleted ilişkileri mümkün olduğunda kaydedilir.
- Yeniden eşleştirmede yüzey türü, eksen, yarıçap, konum ve komşuluk birlikte kullanılır.
- Birden fazla aday varsa keyfi biçimde en yakın yüz seçilmez; referans çözümlenemedi olarak döner.
- OCAF/TNaming altyapısı değerlendirilir; tüm topoloji değişikliklerini otomatik çözen bir garanti gibi sunulmaz.

Tekrarlanan cıvatalar gibi parçaların ortak tanımı ile montajdaki ayrı örnekleri ayrılmalıdır. Kullanıcı bir örneği değiştiriyorsa gerekirse bağımsız kopya oluşturulur; bütün örneklerin değişmesi ayrıca belirtilmelidir. Yerel koordinatlar ile dünya koordinatları ayrı saklanır. Birim dönüşümü tek kontrollü sınırda yapılır ve kaynağı kaydedilir.

İçe aktarımda XDE/STEPCAFControl yaklaşımı değerlendirilmelidir. Montaj hiyerarşisini, adları ve mevcut metadatayı düzleştirmeden almak hedeflenir. Dosyada bulunmayan bilgiler üretilmez.

### 4. Tanıma motoru ve LLM'nin sınırı

Geometri ölçümü ve çekirdek işlemleri deterministik katmanda yapılmalıdır. LLM ölçüm aracı değil; doğrulanmış özellikler üzerinde kullanıcı isteğini düzenleme planına çeviren katman olmalıdır.

Yüzey komşuluk grafiği; yüzlerin analitik türünü, yönelimini, iç/dış malzeme tarafını ve kenar ilişkilerini bir araya getirmelidir. Sadece silindirik yüzey bulmak delik tanımak için yeterli değildir. Kör/geçişli delik, kademeli delik, dış mil yüzeyi ve birbirini kesen boşluklar ayrılmalıdır.

Birden fazla yapım hipotezi üretilebilir. Seçimde kaynak şekle uyum, modelin basitliği ve desteklenen değişikliklerde kararlı davranış değerlendirilir. Güven skoru, ayrılmış doğrulama kümesinde kalibre edilmeden doğruluk olasılığı diye gösterilmez.

Kullanıcıya "model yüzde 95 çözüldü" yerine şu bilgi verilmelidir: kaç özellik tanındı, hangi ölçüler değiştirilebilir, hangi bölgeler kaynak olarak korunuyor ve hangi kontroller geçti. Yüz sayısına dayalı kapsam, yüz bölünmelerinden etkilenebileceği için tek başarı metriği olamaz.

### 5. İki ayrı doğrulama sözleşmesi

#### A. Değişiklik öncesi eşdeğerlik

Kaynak model ile üretilen model aynı birim ve koordinat sisteminde karşılaştırılır:

- Geçerli B-Rep, beklenen solid ve montaj örneği sayıları.
- Montaj dönüşümleri, sınır kutusu, hacim, alan, ağırlık merkezi ve atalet özellikleri.
- Her iki yönde yüzey mesafesi; örnekleme çözünürlüğü ve sınırlamaları raporlanarak.
- Uygun modellerde Boolean simetrik fark hacmi; işlem başarısızsa sonuç başarılı sayılmaz.
- Küçük deliklerin kaybolmasını yakalayacak yerel özellik ve boyut kontrolleri.

Hacim ve sınır kutusunun eşitliği tek başına yeterli değildir: bir deliğin yeri değişirken bu değerler aynı kalabilir. Örneklenmiş yüzey mesafesi de kesin küresel hata sınırı diye sunulmaz. Mutlak ve bağıl toleranslar kaynak hassasiyeti ve görev gereksinimine göre açıkça belirlenir. Onarım gerekiyorsa onarım öncesi/sonrası fark ayrıca raporlanır; onarım sessiz başarıya dönüşmez.

#### B. Düzenleme sonrası davranış

Düzenlenen bütün modelin eski modele eşit olması beklenmez. Önceden tanımlanmış değişiklik sözleşmesi doğrulanır:

- Hedef çap, derinlik, eksen veya konum istenen değere geldi mi?
- İzin verilen değişiklik bölgesi dışındaki yüzeyler korundu mu?
- İstenmeyen solid kaybı, yeni boşluk, komşu kanala açılma veya montaj çarpışması oluştu mu?
- Varsa kullanıcı tarafından verilen minimum et kalınlığı ve diğer kısıtlar sağlandı mı?
- Bağımlı özellikler izin verilen kapsamda güncellendi mi?

Değişmesine izin verilen bölge çıktıdan sonradan seçilmemeli; işlem planında tanımlanmalıdır. Çekirdek veya eşleştirme hataları belirsiz/başarısız olarak raporlanmalıdır. Son Python paketi temiz bir süreçte tekrar çalıştırılarak aynı sonucu verdiği doğrulanmalıdır.

### 6. Dataset stratejisi

En güçlü başlangıç verisi kendi bildiğimiz programlarımızdır: CADi SAML kodu → STEP → dönüşüm motoru → üretilen kod → geometri ve değişiklik doğrulaması. Dönüşüm motoruna referans kodun işlem geçmişi verilmez; aksi halde gerçek tersine dönüşüm ölçülmez.

- Tam metin kod eşitliği aranmaz; farklı geçerli programlar aynı geometriyi üretebilir.
- Kaynak programın bilinen parametreleriyle yapılan kontrollü düzenleme ile dönüştürülen modeldeki karşılığı karşılaştırılır.
- STEP içe aktarma örnekleri, hibrit düzenleme örnekleri ve bağımsız kod üretimi örnekleri ayrı etiketlenir.
- Gerçek STEP dosyalarından çıkarılan programlar doğrulanmış yeniden kurma olarak etiketlenir; orijinal tasarım geçmişi olarak sunulmaz.
- Eğitim ve test ayrımı parça ailesi/kaynak model bazında yapılır. Aynı parçanın döndürülmüş veya ölçeklenmiş kopyaları iki tarafa dağıtılmaz.
- Kaynak, lisans/kullanım hakkı, birim, çekirdek ve kütüphane sürümü, dosya özeti, tolerans, tanıma sürümü ve doğrulama raporu saklanır.
- Belirsiz hedef, desteklenmeyen özellik, bozuk dosya ve başarısız düzenleme örnekleri de beklenen yapılandırılmış sonuçlarıyla tutulur.

Sentetik ailelerde iyi sonuç almak gerçek endüstriyel STEP genellemesini kanıtlamaz. Ayrı gerçek dosya kümesi ve başarısızlık dağılımı raporlanmalıdır. Sayısal geometri doğruluğu, üretilebilirlik veya mühendislik emniyeti onayıyla karıştırılmamalıdır.

### 7. İlk teslimat ve kabul senaryoları

İlk teslimatın kullanıcı akışı: STEP yükle → tanınan delikleri ve ölçülerini göster → desteklenen bir deliğin çapını değiştir → farkı ve doğrulama raporunu göster → Python ve gerekli varlıkları paketle.

İlk kapsam basit prizmatik/dönel gövdeler ve izole dairesel delikler olmalıdır. Serbest biçimli gövdeyi tam parametrik kurma, otomatik mafsal çıkarma ve bütün delik türlerini düzenleme ilk sürüm taahhüdü olmamalıdır.

Kabul senaryoları:

1. Değişikliksiz dışa aktarma/yeniden kurma kaynak şekli belirlenen toleransta korur.
2. Aynı hacim ve sınır kutusuna sahip fakat deliği kaymış model eşdeğerlikten geçmez.
3. Dış silindir yanlışlıkla delik olarak düzenlenmez; kör ve geçişli delikler ayrılır.
4. Döndürülmüş ve farklı birimdeki aynı parça doğru ölçülür ve aynı fiziksel değişikliği alır.
5. Tek montaj örneğini değiştirmek diğer örnekleri etkilemez.
6. Tanınmayan yüzeyler korunur; belirsiz seçim sessizce başka yüze uygulanmaz.
7. Başarısız düzenleme başlangıç modelini bozmaz; geri alma mümkündür.
8. Üretilen paket temiz süreçte çalışır; kaynak varlık gereksinimleri manifestte bulunur.
9. Boolean/mesafe kontrolü çalışmadığında rapor tam doğrulanmış başarı göstermez.
10. Düzenleme hedefi sağlanırken izin verilmeyen komşu bölge değişikliği yakalanır.

Her sürümde destek kapsamı, kabul edilen dönüşümlerin geometrik doğruluğu, yanlış kabul oranı, düzenleme başarısı, belirsiz sonuç oranı ve çalışma süresi birlikte izlenmelidir. Eşikler benchmark üzerinde belirlenmelidir; tahmini başarı yüzdeleri vaat edilmemelidir.

### 8. Bağımlılıklara göre uygulama sırası

1. XDE tabanlı import, değişmez kaynak, birim/koordinat ve montaj envanteri.
2. Kaynak kimlikleri, referans eşleştirme ve değişikliksiz geometri karşılaştırması.
3. Sınırlı feature tanıma ve özellik başına düzenleme yetenekleri.
4. Tek izole delik düzenlemesi, işlem kaydı ve geri alma.
5. Yerel düzenleme sözleşmesi ve bağımsız yeniden çalıştırma doğrulaması.
6. Python/varlık paketi üretimi ve dataset manifesti.
7. Bilinen kaynak programlarla benchmark; ardından ayrı gerçek STEP değerlendirmesi.
8. Doğrulanmış ailelerde bağımsız parametrik yeniden kurma.
9. Cep, kanal, desen, pah/radyüs ve daha karmaşık bölgelerin kademeli desteği.

### 9. Teknik dayanaklar

- OCCT XDE: montaj yapısı ve metadata altyapısı: https://github.com/Open-Cascade-SAS/OCCT/wiki/xde
- OCCT STEP işlemcisi ve STEPCAFControl: https://old.opencascade.com/doc/occt-7.4.0/overview/html/occt_user_guides__step.html
- OCCT OCAF ve topolojik adlandırma: https://dev.opencascade.org/doc/occt-7.2.0/overview/html/occt_user_guides__ocaf.html

Sürümlü doküman bağlantıları kavramsal dayanak içindir. Uygulama sırasında projedeki OpenCASCADE/Python binding sürümünün sunduğu gerçek API ve metadata desteği ayrıca doğrulanmalıdır.

## STEP düzenleme katmanı için ek kritik özellikler

### İşlem (transaction) ve geri alma

Her düzenleme, kaynak modelin kopyası üzerinde bir işlem olarak çalışmalıdır. İşlem; hedef kimlikleri, önceki ve yeni parametreleri, kullanılan koordinat sistemini, etkilenen bölgeyi ve doğrulama sonucunu kaydeder. Çekirdek işlemi başarısız olursa kaynak gövde değişmeden kalır. Kullanıcı tek bir değişikliği geri alabilmeli, işlemleri birleştirebilmeli ve aynı düzenlemeyi başka bir örneğe uygulayabilmelidir.

### Görsel fark ve açıklanabilir hata

Düzenleme öncesi/sonrası şekil, yalnızca sayısal raporla değil, renkli fark görünümüyle de sunulmalıdır: eklenen, çıkarılan, taşınan ve belirsiz bölgeler ayrı gösterilir. Bir işlem reddedildiğinde sistem "başarısız" demekle kalmamalı; örneğin minimum et kalınlığının ihlal edildiğini, Boolean işleminin geçersiz katı ürettiğini veya hedef yüzün birden fazla aday taşıdığını açıklamalıdır.

### Etki alanı ve bağımlılık grafiği

Bir delik çapı değiştiğinde bağlı pah, pattern, bağlantı elemanı ve montaj kısıtları etkilenebilir. Her feature için giriş/çıkış bağımlılıkları tutulmalı; sistem değişiklikten önce etkilenecek nesneleri listelemeli ve kullanıcıya onaylanabilir bir etki özeti vermelidir. Bağımlı özellik desteklenmiyorsa işlem kısmi ve sessiz biçimde uygulanmamalıdır.

### Güvenlik ve kaynak yönetimi

STEP dosyası ve üretilen Python kodu güvenilmeyen girdi kabul edilmelidir. Kod üretimi izin verilen CADi SAML çağrılarıyla sınırlanmalı, dış komut çalıştırma ve keyfi dosya erişimi engellenmeli, büyük veya bozuk dosyalar için kaynak sınırı konulmalıdır. Manifest; kaynak dosya özeti, kütüphane/çekirdek sürümü ve yeniden üretim komutunu içermelidir.

### İnsan onayını doğru yerde kullanma

Kullanıcı her ölçümde durdurulmamalıdır. Ölçümü kesin ve işlem sözleşmesi doğrulanmış değişiklikler otomatik çalışabilir. Birden fazla geometrik yorum, komşu bölge riski, yetersiz tolerans veya desteklenmeyen feature varsa sistem düzenlemeyi beklemeye alıp seçenekleri göstermelidir. Onay kararı dataset'e de kaydedilerek hangi belirsizliklerin insan tarafından çözüldüğü izlenmelidir.

### Performans ve önbellek

Aynı STEP tekrar işlendiğinde dosya özeti, çekirdek sürümü ve tanıma ayarları eşleşiyorsa import ve ölçüm sonuçları önbellekten alınabilir. Ancak geometri onarımı, birim ayarı veya tolerans değiştiğinde önbellek geçersiz kılınmalıdır. Büyük montajlarda parça tanıma, montaj yerleşimi ve görselleştirme ayrı aşamalara bölünmelidir.

Bu ekler, tam parametrik tersine mühendislikten önce teslim edilmesi gereken operasyonel güven katmanını tanımlar. Önerilen nesne adları ve işlem akışları taslaktır; mevcut CADi SAML API'si olarak kabul edilmemelidir.

## Bağımsız CADi SAML kodu hedefi

Kullanıcı STEP yüklediğinde nihai hedef, STEP dosyasını çalışma zamanında tekrar okumayan, yalnızca CADi SAML çağrılarıyla aynı modeli oluşturan Python kodudur. Üretilen dosya; `import_step(...)`, harici B-Rep dosyası, kaynak yol veya gizli dosya bağımlılığı içermemelidir. STEP yalnızca dönüştürme aşamasının girdisidir; teslim edilen kodun girdisi değildir.

Bu hedef için çıktı açıkça şu şekilde sınıflandırılmalıdır:

1. **Bağımsız parametrik kod:** Tüm geometri CADi SAML işlemleriyle yeniden kurulur ve temiz bir ortamda STEP olmadan çalışır.
2. **Bağımsız hibrit kod:** Tanınan bölgeler parametrik CADi SAML işlemleriyle kurulur; tanınmayan bölgeler için kabul edilmiş, paketlenmiş bir CADi SAML yerleşik geometri temsili kullanılır. Kaynak STEP'e çalışma zamanında ihtiyaç duymaz.
3. **STEP bağımlı paket:** Sadece geçici uyumluluk çıktısıdır; bağımsız kod diye etiketlenemez.

Bağımsız hibritte bile “bilinmeyen yüzeyi kutuya dönüştürme” yapılmamalıdır. Gerekirse dönüştürme aşamasında kaynak yüzey verisi CADi SAML'nin kendi veri yapısına çevrilir ve kodun içine güvenli, sürümlü bir sabit veri olarak gömülür. Bu veri STEP dosyasına referans değil, üretilmiş bir CADi SAML girdisidir; formatı ve lisansı manifestte belirtilmelidir.

### Bağımsız kod üretim hattı

1. STEPCAF/XDE ile dosyayı yükle; birimleri, montaj örneklerini, dönüşümleri ve solidleri çıkar.
2. Her solid için ölçülebilir bir ara temsil (IR) oluştur; kaynak yüz/kenar indekslerini kalıcı kimlik olarak kullanma.
3. Prizma, silindir, dönel yüzey, delik, cep, kanal, pattern, pah ve radyüs gibi desteklenen özellikleri komşuluk ve ölçümlerle tanı.
4. Her feature'ı CADi SAML kurucu çağrılarına ve parametrelerine çevir; işlem sırasını bağımlılık grafiğinden üret.
5. Tanınmayan bölgeleri ya güvenli yerleşik yüzey/mesh/ B-Rep sabiti olarak kodla ya da bağımsız üretimi reddet. Eksik bölgeyi tahmin ederek doldurma.
6. Üretilen Python'u yeni bir süreçte, STEP dosyası ve kaynak klasörü olmadan çalıştır.
7. Son şekli kaynak STEP ile karşılaştır; yerel ve küresel toleranslar geçmeden bağımsız kod etiketi verme.

### Bağımsızlık kabul testleri

- Üretilen klasörden STEP dosyasını ve kaynak yolunu kaldırınca kod hâlâ çalışır.
- Kod farklı bir çalışma dizininden ve temiz Python sürecinden çalıştırılabilir.
- Üretilen modelin solid/instance sayısı, dönüşümleri ve kritik feature ölçüleri korunur.
- Hacim veya dış sınır aynı olsa bile yeri değişmiş delik ve kanallar yüzey farkı/yerel kontrollerle yakalanır.
- Bozuk veya çözülemeyen feature olduğunda sistem `independent_generation_failed` gibi yapılandırılmış sonuç verir; yaklaşık geometriyi başarılı diye sunmaz.
- Kod deterministik manifest, CADi SAML sürümü, OpenCASCADE sürümü ve birim bilgisiyle yeniden üretilebilir.

İlk bağımsız kod MVP'si eksen hizalı prizmatik/dönel parçalar, delikler, basit cepler ve tekrar desenleriyle sınırlandırılmalıdır. Serbest biçimli yüzeylerde bağımsızlık ancak yerleşik B-Rep temsilinin doğrulanmasından sonra açılmalıdır. Böylece kullanıcı STEP'i bir kez verir, karşılığında dosyadan tamamen bağımsız CADi SAML kodu alır; sistem de hangi kısımların gerçek parametrik, hangi kısımların gömülü geometri olduğunu dürüstçe bildirir.

## Elektronik ve elektrik tasarım katmanı

CADi SAML'nin mekanik modelin yanına bir elektronik/elektrik modülü eklemesi, özellikle motor, sensör, aktüatör ve kontrol kutusu içeren sistemlerde büyük değer sağlar. Bu modül mekanik geometriyi kopyalamamalı; elektriksel bağlantılar, bileşen özellikleri ve mekanik yerleşim arasında ortak bir sistem modeli kurmalıdır.

### Kapsam

- Şematik devre: bileşen, pin, net, besleme, toprak, sinyal ve konektör ilişkileri.
- Kablo ve harness: kablo kesiti, damar sayısı, renk/etiket, bükülme yarıçapı, uzunluk ve güzergâh.
- PCB mekanik yerleşimi: kart sınırı, montaj delikleri, komponentlerin yaklaşık hacimleri, keep-out bölgeleri ve konektör konumları. Elektrik izleri çizilmez.
- Elektrik kabini: DIN rayı, sigorta, kontaktör, röle, güç kaynağı, klemens ve havalandırma yerleşimi.
- Elektromekanik eşleştirme: motor mili, sensör ekseni, konektör erişimi, montaj deliği ve bakım boşluğu.
- Elektriksel arayüz kontrolü: sensör beslemesi, konektör pin eşleşmesi, kablo/harness güzergâhı ve temel güç/gerilim düşümü kontrolü. Devre şeması veya PCB izi tasarlanmaz.
- Termal ön değerlendirme: PCB veya kabin içi kayıplar, yaklaşık sıcaklık artışı ve soğutma ihtiyacı.
- Kural kontrolleri: kısa devre, yanlış voltaj sınıfı, eksik toprak, yetersiz izolasyon mesafesi, kablo bükülme ihlali ve mekanik çakışma.

### Ortak ara temsil

Elektronik nesneler `Component`, `Pin`, `Net`, `Connector`, `Cable`, `Board`, `Enclosure` ve `MountingInterface` gibi kavramlarla temsil edilmelidir. Her bileşenin elektriksel özellikleri (nominal gerilim, akım, güç, izolasyon sınıfı), mekanik zarfı ve montaj referansları ayrı alanlardır. Aynı bileşen tanımı farklı montaj örneklerinde tekrar kullanılabilir.

Mekanik montajdaki koordinat sistemi ile PCB/kabin koordinat sistemi dönüşüm matrisiyle bağlanır. Bir konektörün CAD yüzündeki konumu, şemadaki pin numaralarıyla ilişkilendirilebilir. Bu ilişki kurulmadan LLM'nin yalnızca isim benzerliğine göre kablo bağlamasına izin verilmemelidir.

### Proje sınırı

Bu modül PCB tasarlayan, bakır izlerini yönlendiren veya tam E-CAD/autorouter sistemi değildir. PCB'nin elektriksel devresi başka bir araçta hazırlanabilir; CADi SAML bu kartın mekanik zarfını, montaj deliklerini, konektör erişimini, soğutmasını ve çevresindeki muhafazayı tasarlar. Aynı şekilde sensörün elektronik iç devresi değil, ölçüm noktasına göre konumu, yönü, görüş alanı, kablo çıkışı ve bakım erişimi modellenir.

### LLM kullanım sınırı

LLM; “24 V sensörü PLC'nin X3 girişine bağla”, “kabloyu hareketli kol boyunca döşe” veya “fan için muhafazada açıklık oluştur” gibi niyetleri yapılandırılmış tasarım işlemlerine çevirebilir. Gerilim, akım, pin tipi, yön ve güvenlik sınıfı ölçüm/kurallar motoru tarafından doğrulanmalıdır. Eksik elektriksel değerler varsayılmamalı; kullanıcıdan veya bileşen kataloğundan istenmelidir.

### Bağımsız kod üretimi

Elektronik modül için de STEP dönüşümündeki aynı kural geçerlidir: üretilen CADi SAML kodu harici kaynak dosyasını zorunlu kılmamalıdır. PCB ve kabin geometrisi parametrik olarak üretilebilir; parça sembolleri, pin/net listeleri ve kablo güzergâhları manifest içinde kodlanabilir. Üçüncü taraf E-CAD çıktıları (örneğin Gerber, netlist veya üretim dosyaları) kaynak olarak ekleniyorsa paket bağımlılığı açıkça belirtilmelidir.

### İlk uygulanabilir sürüm

İlk sürümde PCB autorouter, bakır iz tasarımı veya sertifikalı elektrik güvenliği hedeflenmemelidir. Daha sınırlı ve ölçülebilir bir akış önerilir: elektronik bileşen/kart kataloğu → kart zarfı ve montaj arayüzü → muhafaza ve sensör yerleşimi → konektör erişimi → kablo uzunluğu/bükülme kontrolü → ısı yayılımı ve mekanik/arayüz kural raporu.

Kabul testleri; sensörün ölçüm noktasına doğru yönelmesi, algılama hattının kapanmaması, kart ve komponent zarfının muhafaza duvarına çarpmaması, konektör ve bakım kapağına erişimin açık kalması, kablo minimum bükülme yarıçapının korunması, kartın soğutma ihtiyacının karşılanması ve üretilen modelin kaynak elektrik dosyası olmadan tekrar oluşturulabilmesi olmalıdır. Sertifikasyon ve saha güvenliği için sonuçlar yetkili elektrik mühendisi onayı gerektiren tasarım çıktısı olarak etiketlenmelidir.

### Enerji ve elektromanyetik tasarım kapsamı

Batarya, motor ve güç elektroniği için ayrı bir elektromekanik alt modül eklenebilir. Buradaki amaç elektrik devresini veya PCB izlerini çizmek değil; enerji bileşenlerini makine gövdesiyle güvenli ve analiz edilebilir biçimde birleştirmektir.

- Batarya hücresi/modülü: hücre zarfı, seri/paralel paket düzeni, tutucu, sıkıştırma, izolasyon boşluğu, servis kapağı ve değiştirilebilirlik.
- Batarya muhafazası: sızdırmazlık, basınç tahliye yönü, darbe koruması, havalandırma/soğutma kanalı, drenaj ve yangın bölümlendirmesi için geometrik kontroller.
- Güç yolu: bara ve kablo kanalı, yüksek akım konektörü, sigorta/servis ayırıcısı, kablo bükülmesi ve hareketli parçalarla açıklık.
- Motor/inverter yerleşimi: kütle merkezi, reaksiyon torku, montaj rijitliği, titreşim izolasyonu, konektör yönü ve soğutma yüzeyi.
- Elektromanyetik uyumluluk için ön tasarım: yüksek akım kabloları ile hassas sensör kablolarını ayırma, ekranlama/şase bağlantısı için mekanik temas noktaları, muhafaza sürekliliği ve kablo girişlerinin konumu.
- Batarya termal davranışı: hücre kaybı, soğutucu temas yüzeyi, yaklaşık ısı yolu ve sıcaklık sensörü konumları. Bu sonuçlar ayrıntılı elektro-kimyasal veya CFD çözümü olarak etiketlenmez.

Her enerji bileşeni için elektriksel değerler (gerilim, sürekli/pik akım, kapasite, izin verilen sıcaklık) mekanik zarf ve montaj referanslarından ayrı tutulmalıdır. CADi SAML bu değerlerle hacim, kütle merkezi, kablo kesiti için ön kontrol, ısı yükü ve servis aralığı hesaplayabilir; hücre kimyası, kısa devre dayanımı, izolasyon koordinasyonu ve sertifikasyon sonuçlarını varsayamaz.

İlk batarya MVP'si; hücre kutusu ve modül dizisi oluşturma, muhafaza ve kapak tasarımı, kablo/servis ayırıcı yerleşimi, soğutma kanalının geometrik kontrolü, sensör yerleşimi ve çarpışma/erişim raporundan oluşmalıdır. Sonraki aşamada titreşim, düşme/yükleme senaryosu, termal ağ modeli ve basitleştirilmiş elektromanyetik açıklık kuralları eklenebilir.

## Şasi tasarım katmanı

Şasi modülü; batarya, motor, süspansiyon, direksiyon, fren ve gövde bağlantılarını ortak bir referans iskeletinde yönetmelidir. Ana kiriş, travers, kolon, plaka, braket, gusset ve boru profilleri; kesit, et kalınlığı, bağlantı tipi ve malzeme ile parametrik oluşturulmalıdır. Süspansiyon hareket zarfı, tekerlek dönüşü, bakım erişimi, kablo/hortum geçişi ve alet hacmi de geometri kadar önemli boşluk nesneleri olmalıdır.

Kullanıcı statik ağırlık, fren/ivmelenme, viraj, tek tekerlek çukuru, burulma, çekme/itme, batarya darbe yükü ve motor reaksiyon torku gibi senaryolar tanımlayabilmelidir. Kuvvet, moment, mesnet ve emniyet katsayısı verilmemişse sistem sayı uydurmamalıdır. Bu senaryolar mevcut FEA altyapısına aktarılmalı; gerilme, deformasyon, burulma rijitliği, bağlantı kuvveti, burkulma eğilimi ve kaynak/bolt bölgeleri raporlanmalıdır.

Şasi için ayrıca profil ve plaka üretilebilirliği, kaynak torcu ve cıvata anahtarı erişimi, drenaj delikleri, sac büküm yarıçapı, delik kenar mesafesi, malzeme yoğunluğu ve galvanik temas kontrolleri eklenmelidir. Batarya muhafazasıyla arasında elektriksel izolasyon, darbe yolu ve servis ayırma bölgesi korunmalıdır.

İlk şasi MVP'si parametrik profiller ve braketler, montaj arayüzü kütüphanesi, kütle merkezi/aks yükü hesabı, temel statik-burulma yük setleri, boşluk-çakışma kontrolü, FEA sınır şartı üretimi ve basit DFM raporundan oluşmalıdır. Çarpışma güvenliği veya homologasyon sonucu olarak etiketlenmemeli; doğrulanmış yük durumları ve mühendis incelemesi sonraki aşamada eklenmelidir.

## Süspansiyon tasarım katmanı

Süspansiyon modülünün temel nesnesi bağlantı noktalarıdır (hardpoint). Üst/alt salıncak, dikey taşıyıcı, rot kolu, amortisör, yay, viraj demiri, tekerlek göbeği ve şasi bağlantıları bu noktalar üzerinden tanımlanmalıdır. Parçanın katı geometrisi, bu kinematik iskelet doğrulanmadan üretilmemelidir.

### Kinematik ve paketleme

- Tekerlek merkezi, lastik zarfı, jant ve göbek referansları.
- Üst/alt salıncak, toe link, track rod ve amortisör üst-alt bağlantıları.
- Jounce/rebound hareketi boyunca kamber, toe, caster ve kingpin ekseni değişimleri.
- Roll merkezi, instant center, bump steer, scrub radius ve direksiyon dönüş zarfı.
- Lastik ile şasi, çamurluk, fren, akü muhafazası ve kollar arasındaki açıklık.
- Amortisör strok sınırı, yay oturma yüzeyi, bump stop ve mekanik hareket limitleri.
- Sağ-sol simetri, ön/arka aks farkı ve farklı sürüş yükseklikleri için varyant yönetimi.

### Yay, amortisör ve yükler

Yay katsayısı, ön yük, amortisör sıkışma/geri açılma katsayısı, hareket oranı, tekerlek yükü ve hedef sürüş yüksekliği ayrı parametreler olmalıdır. Statik aks yükü, fren, viraj, tek tekerlek çukuru ve kaldırım/engel yükleri kullanıcı tarafından senaryo olarak verilmelidir. Sistem bu bilgilerle bağlantı kuvvetlerini ve şasiye aktarılan reaksiyonları hesaplayabilir; gerçek yol dayanımı veya sertifikasyon sonucu varsaymamalıdır.

### Geometri üretimi ve analiz bağlantısı

Hardpoint çözümü geçerli olduktan sonra salıncak boruları, dövme/levha taşıyıcılar, mafsal yuvaları, burçlar, bağlantı kulakları ve fren/sensör braketleri parametrik oluşturulmalıdır. FEA için salıncak, porya ve şasi bağlantılarında kuvvet/moment setleri; yorulma için çevrim geçmişi; modal analiz için kütle ve rijitlik bilgisi üretilebilmelidir. Burç esnekliği ve lastik temas modeli ilk sürümde basitleştirilmiş varsayım olarak açıkça etiketlenmelidir.

### İlk süspansiyon MVP'si ve kabul kontrolleri

İlk sürüm çift salıncaklı veya MacPherson gibi tek bir seçilmiş mimariyle başlamalıdır. Hardpoint girişi, tekerlek hareket simülasyonu, kamber/toe grafikleri, lastik ve şasi çakışma kontrolü, amortisör strok kontrolü, temel aks yükü hesabı ve montaj geometrisi üretimi yeterli ilk kapsamdır.

Kabul testleri; tam jounce/rebound boyunca lastiğin gövdeye çarpmaması, direksiyon dönüşünde bağlantıların kilitlenmemesi, amortisörün strok dışına çıkmaması, sağ-sol montajın tutarlı olması, beklenen hareket yönünün korunması ve üretilen parçaların hardpoint değişince yeniden oluşturulabilmesidir. Sonuçlar “kinematik ön tasarım” olarak sunulmalı; yol tutuşu, dayanıklılık ve mevzuat onayı olarak etiketlenmemelidir.
## Yüksek enerjili motor sistemleri için araç matrisi

Roket motoru benzeri yüksek sıcaklık, yüksek basınç ve hızlı akış içeren sistemlerde CADi SAML'nin rolü güvenli bir dijital mühendislik katmanı olmaktır. Yakıt/oksitleyici reçetesi, ateşleme prosedürü veya çalışır motor üretim talimatı bu kütüphanenin kapsamı değildir; sonuçlar yetkili ekip, tesis ve mevzuat denetimi gerektirir.

Gerekli araçlar: parametrik CAD ve montaj; termal analiz; CFD/akış çözümü ve mesh yönetimi; basınç ve termal gerilme için FEA; yüksek sıcaklık malzeme ve üretim kataloğu; basınç/sıcaklık/titreşim sensörü yerleşimi; test fikstürü ve güvenlik yerleşimi; gereksinimden analiz ve test raporuna izlenebilirlik.

İlk güvenli MVP; motor performansını optimize etmek yerine muhafaza, flanş, nozul arayüzü, sensör portları, soğutma kanalı hacmi, montaj/bakım erişimi, analiz sınır şartı ihracı ve doğrulama manifesti üretmelidir. Çalışabilirlik, basınç dayanımı veya itki yalnızca yetkili analiz ve kontrollü testlerle doğrulanır.
## Birleştirilmiş iş planı ve açık kaynak stratejisi

CADi SAML üst katman olmalı; ağır çözücüleri yeniden yazmak yerine sabit adaptörler kullanmalıdır. LLM yalnızca şartnameyi IR'ye, IR'yi CADi SAML koduna ve küçük yamalara çevirir. OpenCASCADE (B-Rep/STEP/XDE), Gmsh (mesh), meshio (format dönüşümü), OpenFOAM (CFD), SU2 (alternatif CFD), Code_Aster/Salome-Meca (FEA), CalculiX (hafif FEA), PyVista/VTK (görselleştirme) ve NumPy/SciPy (hesap/optimizasyon) aday açık kaynak bileşenlerdir. Lisans ve sürüm koşulları dağıtımdan önce kaydedilmelidir.

Uygulama sırası: çekirdek IR/birim/provenance sözleşmesi; STEP'ten bağımsız parametrik kod; montaj, şasi, hardpoint tabanlı süspansiyon ve batarya muhafazası; yerel geometri farkı/rollback; tek FEA ve tek OpenFOAM runner adaptörü; modal, burkulma, yorulma, termal ve DFM analizleri; gold/negative/unresolved dataset; görsel rapor, önbellek ve sandbox.

Token kullanımını azaltmak için katalog kimlikleri, JSON IR, sabit solver şablonları, artımlı patch, sonuç özeti ve analiz önbelleği kullanılmalıdır. Büyük mesh/sonuçlar konuşmaya taşınmamalı; deterministik ölçüm, mesh, solver ve diff araçlarda kalmalıdır. Her aşama temiz süreçte yeniden üretim, ölçülebilir kabul testi ve belirsiz durumda kontrollü ret şartını karşılamalıdır.

## LLM'nin kesin kullanım noktaları

LLM beş yerde kullanılır:

1. **Şartnameyi anlama:** “bataryayı şasinin altına yerleştir, sensör erişilebilir kalsın” gibi doğal dili ölçülebilir gereksinimlere çevirir. Eksik gerilim, yük, ölçü veya toleransı tespit edip ister; sayı uydurmaz.
2. **CADi SAML kodu üretimi:** doğrulanmış IR'den feature, montaj, şasi, süspansiyon veya muhafaza kurucu çağrılarını üretir. Hangi fonksiyonun mevcut olduğu katalog/API şemasından kontrol edilir.
3. **Değişiklik planlama:** “deliği 2 mm büyüt” veya “sensörü 30 mm dışarı al” isteğini hedef kimlik, yeni parametre, etki alanı ve rollback içeren küçük bir patch'e dönüştürür.
4. **Araç orkestrasyonu:** geometri ölçümü, çakışma, FEA, CFD, mesh ve doğrulama araçlarını bağımlılık sırasıyla çağırır; sonuç dosyalarını yorumlar ve bir sonraki adımı seçer.
5. **Raporlama ve dataset etiketleme:** geçen kontrolleri, belirsiz bölgeleri, hata nedenlerini ve gold/negative/unresolved durumunu anlaşılır biçimde açıklar; manifest üretir.

LLM'nin yapmaması gereken işler; yüzeyden ölçü tahmin etmek, fizik denklemini yaklaşık cevapla değiştirmek, mesh veya solver sonucunu uydurmak, doğrulanmamış geometriyi başarılı ilan etmek, güvenlik katsayısı/imalat toleransı icat etmek ve bilinmeyen STEP bölgelerini keyfi katıyla doldurmaktır. Bu işler deterministik CADi SAML/OpenCASCADE kodu, kataloglar, mesh araçları, harici çözücüler ve doğrulama sözleşmesi tarafından yapılır.

Örnek akış: Kullanıcı “motoru şasiye bağla ve bakım kapağı açık kalsın” der → LLM bunu montaj arayüzü, motor zarfı, bağlantı noktaları ve bakım boşluğu gereksinimlerine çevirir → CADi SAML geometrik modeli kurar → çakışma ve erişim aracı ölçer → gerekirse FEA/termal analiz runner'ı çalışır → LLM yalnız sonuçları açıklar veya küçük bir düzeltme patch'i önerir → doğrulama geçmeden çıktı onaylanmaz.
