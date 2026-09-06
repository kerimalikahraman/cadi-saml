# Mühendislik doğrulama ve tasarım API'leri

## FEA geçerliliği ve kabul kriterleri

FEA artık eksik mesnet, bulunamayan yük yüzeyi, sıfır yük veya bilinmeyen malzemeyi
sessizce tamamlamaz. `ValueError` ile durur. Basınç, dış tetrahedron yüzeylerinin
alan vektörlerinden düğümlere dağıtılır; pozitif basınç yüzeye içeri doğrudur.
String yüzey seçiciler sınır koordinatlarını kullanır. Eğik yüzeylerde bir koordinat
fonksiyonu kullanılabilir; seçilen üçgenin tüm düğümleri koşulu sağlamalıdır.

```python
study = asm.add_fea_study(
    "bracket", material="Aluminum6061", mesh_size=2.0,
    required_safety_factor=2.0, max_displacement_mm=0.25,
)
study.fix_face("z_min").apply_force("z_max", (0, 0, -100))
preview = study.preview_boundary_conditions()
result = study.solve()
print(result.solution_valid, result.criteria_passed)
print(result.raw_solution.reaction_forces.sum(axis=0))
```

`is_safe`, geriye uyumluluk için tutulur; yalnızca tanımlanan lineer elastik
akma/sehim kriterlerinin karşılandığını ifade eder. Yorulma, burkulma, temas ve
plastisite değerlendirmesi değildir. `solution_valid` sonlu çözüm ve sayısal artık
kontrolünü belirtir; ağ yakınsaması ayrı kontrol edilmelidir. Tepki kuvvetleri N,
yer değiştirmeler mm ve gerilmeler MPa cinsindendir.

## STEP geometrisini koruyan inceleme

```python
from cadi_saml import STEPReverseEngineer
report = STEPReverseEngineer.inspect_and_to_saml("part.step")
print(report["holes"], report["external_cylinders"], report["pcd_patterns"])
```

İç/dış silindir ayrımı yönlendirilmiş yüzey normalinden yapılır. Tam silindirik
oyuklarda uç noktalarının katı içinde bulunmasına göre kör/geçişli aday sınıfı
verilir. Eğik PCD desenleri yerel düzlemde daire ve eşit açı kontrolüyle bulunur.
Üretilen Python, STEP'i yeniden içeri alır ve port ekler; tekrar delik açmaz.
Özellik geçmişi, havşa ve birleşik kademeli delik yeniden yapılandırılmaz.
Parçalanmış silindir yüzeyleri ve kısmi oyuklar inceleme gerektirir.

## Hareket ve çevrimler

```python
report = asm.validate_mechanism("pinion")
closure = asm.solve_loop_closure("pinion", value=90)
clearance = asm.check_motion_clearances(
    "pinion", values=range(0, 361, 5), min_clearance_mm=1.0,
    ignore_pairs=[("pinion", "bearing")],
)
envelope = asm.get_motion_envelope("pinion", values=range(0, 361, 5))
```

Çevrim çözümü dişli/kayış/kremayer/vida aktarımının skaler denklemleri içindir;
genel uzaysal mafsal çözümü değildir. Geçersiz oranlar ve çelişkili çevrimler
sıfır sürücü konumunda dahi reddedilir. Hareket denetimi bağlı olmayan hareketli
parçaları reddeder; mafsalı olmayan gövdeler sabit kabul edilir.

Boşluk raporu yalnızca verilen konumlardaki sonuçları içerir; aradaki çarpışmalar
kaçabilir. `CONTACT` sıfır boşluğu, `COLLISION` hacimsel kesişimi gösterir.
Hareket zarfı örneklenmiş tüm montajın eksenlere paralel sınır kutusudur;
sürekli süpürülmüş hacim değildir. Mevcut slider-crank hareketi yalnızca ofsetsiz
XY düzlemi/+X sürgü düzenini destekler; diğer düzenler açık hatayla reddedilir.

## Tolerans zinciri ve pul seçimi

```python
from cadi_saml import ToleranceStack
stack = ToleranceStack()
stack.add_dimension_tolerance("housing", 100, lower=-0.1, upper=0.2)
stack.add_dimension_tolerance("shaft", 98, lower=-0.05, upper=0.05, coefficient=-1)
print(stack.analyze_stackup())
print(stack.recommend_shim(0.3, 0.8, available_thicknesses=[1, 1.5, 2]))
```

Sapmalar işaretlidir, uzunluk birimi mm'dir. Zincir bir boyutlu doğrusal en kötü
durum hesabıdır. Pul kalınlığı boşluktan çıkarılır; seçim tüm tolerans aralığının
hedefe uymasını gerektirir. Uygun pul yoksa `feasible=False` döner.

## Sınırlı parametrik tasarım araması

```python
from cadi_saml import Assembly, DesignStudy

def evaluate(parameters):
    model = Assembly("candidate")  # Her denemede yeni model
    model.add_box("beam", 40, 10, parameters["thickness"])
    study = model.add_fea_study("beam", material="S235JR", mesh_size=3)
    result = study.fix_face("x_min").apply_force("x_max", (0, 0, -100)).solve()
    return {"volume": 40 * 10 * parameters["thickness"],
            "deflection": result.max_displacement_mm,
            "safety_factor": result.safety_factor}

search = DesignStudy(evaluate, objective="volume", max_trials=4)
search.add_design_constraint("deflection", maximum=0.25)
search.add_design_constraint("safety_factor", minimum=2)
result = search.optimize_design({"thickness": [4, 6, 8, 10]})
print(result["best"], result["trials"])
```

Sonuç, verilen sonlu parametre ızgarasındaki en iyi uygun adaydır; küresel optimum
iddiası yoktur. Başarısız geometri/çözüm denemeleri `FAILED`, kriter dışı adaylar
`INFEASIBLE` olarak tutulur. Bütçeyi aşan ızgara çalıştırılmaz. Evaluator geçerli
sonlu sayısal metrik döndürmekten ve her denemede bağımsız model kurmaktan sorumludur.

## Kabul testleri

`tests/test_engineering_acceptance.py`: üçgen yüzey basıncı, kuvvet/moment dengesi,
dönme değişmezliği, eksik koşullar, bozuk ağ, kullanıcı kriterleri, tolerans
işaretleri, pul uygunluğu, deneme bütçesi, çevrim çelişkisi, hareket çarpışması,
eğik PCD, STEP hacim/port korunumu ve FEA ağ inceltme kontrolü.

## LLM keşfi, kısa bağlam ve güvenli düzenleme

API kataloğu çalışma zamanındaki gerçek Python imzalarından üretilir; türler,
zorunlu alanlar, varsayılanlar, birimler ve kayıtlı kısıtlar JSON olarak alınabilir:

```python
catalog = asm.api_schema()
box_schema = asm.describe("add_box")
```

`describe_macro()` geriye uyumluluk için aynı merkezi şemayı kullanır. Yeni bir
metodun imzası değiştiğinde katalog otomatik olarak değişir; özel aralık ve enum
kısıtları `core/llm_interface.py` içindeki tek kayıt tablosunda tutulur.

LLM'ye tüm modeli göndermek yerine ilgili bağlam seçilebilir:

```python
context = asm.inspect("motor", detail="summary",
                      include=["parameters", "ports", "constraints"])
asm.checkpoint("motor_mount_before")
# ... değişiklikler ...
changes = asm.diff_since("motor_mount_before")
```

`inspect()` JSON uyumlu parça, port ve mate verisi döndürür. `issues` istenirse
geometri derlenir ve teşhis çalışır; bu seçenek büyük montajlarda daha pahalıdır.
Checkpoint'ler süreç belleğindedir ve dosyaya kalıcı olarak yazılmaz.

Parametre düzenlemeleri aday model üzerinde doğrulanabilir:

```python
proposal = asm.preview_patch({"bracket.parameters.thickness": 6.0})
report = proposal.validate()
if report["valid"]:
    proposal.commit()
```

Önizleme kaynak montajı değiştirmez. Yalnızca var olan parametre yolları kabul
edilir; isim, port ve özellik koleksiyonları bu API'den değiştirilemez. Doğrulama
IR kontrolü, OCCT derleme ve manifold kontrolü yapar. Önizlemeden sonra kaynak
montaj değişirse commit çakışma hatası verir. Eski `patch()` metodu aynı işlemi
otomatik doğrulayıp commit ederek geriye uyumluluğu korur.

`diagnose()` sorunları `code`, `severity`, ilgili `parts`, ölçülen `actual` değer
ve makine tarafından uygulanabilir `repair_options` alanlarıyla döndürür. Eski
teşhis sonucu geçiş sürecinde `legacy` alanında bulunur.
