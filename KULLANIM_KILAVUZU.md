# CADi SAML (v0.6.0) — Kapsamlı Kullanım Kılavuzu

**Açık Kaynak Kodlu, Parametrik ve LLM-Uyumlu Python CAD & Kinematik Motoru**

---

## 📑 İçindekiler
1. [Giriş ve Kurulum](#1-giriş-ve-kurulum)
2. [Hızlı Başlangıç & Temel Mimari](#2-hızlı-başlangıç--temel-mimari)
3. [Düzlemsel Mekanizmalar ve Krank-Biyel Sistemleri](#3-düzlemsel-mekanizmalar-ve-krank-biyel-sistemleri)
4. [Dişli Transmisyonları & Kremayer-Pinyon](#4-dişli-transmisyonları--kremayer-pinyon)
5. [Sac Metal Modelleme (DIN 6935 K-Faktörü)](#5-sac-metal-modelleme-din-6935-k-faktörü)
6. [Motorsport Donanımları & Süspansiyon](#6-motorsport-donanımları--süspansiyon)
7. [Standart Parçalar & Alüminyum Profiller](#7-standart-parçalar--alüminyum-profiller)
8. [Organik Yüzeyler & NACA Kanat Profilleri](#8-organik-yüzeyler--naca-kanat-profilleri)
9. [2D ISO Teknik Resim Üretimi (HLR)](#9-2d-iso-teknik-resim-üretimi-hlr)
10. [İnteraktif 3D WebGL Hareket Simülasyonu](#10-i̇nteraktif-3d-webgl-hareket-simülasyonu)
11. [Geometri Doğrulama, Çakışma Testi ve Kütle Özellikleri](#11-geometri-doğrulama-çakışma-testi-ve-kütle-özellikleri)

---

## 1. Giriş ve Kurulum

CADi SAML, hem mühendislerin hem de Yapay Zekâ modellerinin (LLM) sıfır koordinat karmaşasıyla, anlamsal (semantik) ve hatasız 3D CAD modelleri üretmesi için OpenCASCADE (OCCT) çekirdeği üzerinde geliştirilmiştir.

```bash
pip install cadi_saml
```

Gerekli B-Rep katı modelleme kütüphanesi için:
```bash
pip install cadquery-ocp
```

---

## 2. Hızlı Başlangıç & Temel Mimari

Her tasarım bir `with Assembly(...)` bağlamında başlar. Koordinat dönüşümleriyle uğraşmak yerine montaj ilişkileri ve fonksiyonel parçalar tanımlanır:

```python
from cadi_saml import Assembly, OCCTBackend

with Assembly("Temel_Montaj", units="mm", material="Steel4140") as asm:
    # Kutu ekleme
    govde = asm.add_box("govde", length=120.0, width=80.0, height=30.0)
    
    # Delik delme
    govde.add_hole("mil_deligi", diameter=25.0, depth=0, position=(60.0, 40.0))
    
    # Pah kırma veya Yuvarlatma (Fillet / Chamfer)
    asm.fillet("govde", radius=3.0, edges="all_top")

# Katı B-Rep modelleri derle
backend = OCCTBackend()
solids = backend.compile(asm.to_ir())

# STEP formatında dışa aktar
backend.export_step(solids, "govde.step")
```

---

## 3. Düzlemsel Mekanizmalar ve Krank-Biyel Sistemleri

CADi SAML 0.4.0 ile gelen monolitik krank mili, biyel kolu, segmanlı piston ve motor bloğu şablonları:

```python
with Assembly("Krank_Biyel_Motoru", units="mm") as asm:
    R = 30.0   # Krank yarıçapı (Strok = 60 mm)
    L = 90.0   # Biyel kolu uzunluğu

    # 1. Motor Bloğu / Yataklı Taban Gövde (36mm silindir kovanı ve üst pencere)
    frame = asm.add_engine_frame("engine_frame", cylinder_bore_dia=36.0)

    # 2. Monolitik Krank Mili (Karşı ağırlıklı disk ve ofsetli krank pimi)
    crank = asm.add_crankshaft("crankshaft", crank_radius=R, origin=(0.0, 0.0, 17.0))

    # 3. Dövme Biyel Kolu (I-Profil gövde, krank ve bilek pimi delikleri)
    conrod = asm.add_connecting_rod("connecting_rod", length=L, origin=(R, 0.0, 27.0))

    # 4. Yatay Kovan Pistonu (Segman kanallı ve dahili bilek pimi)
    piston = asm.add_slider_piston("slider_piston", diameter=34.0, length=42.0, origin=(R + L, 0.0, 32.0))

    # Kinematik Eklemler
    asm.add_revolute_joint("crankshaft", origin=(0.0, 0.0, 17.0), axis=(0.0, 0.0, 1.0))
    asm.add_revolute_joint("connecting_rod", origin=(R, 0.0, 27.0), axis=(0.0, 0.0, 1.0))
    asm.add_prismatic_joint("slider_piston", origin=(R + L, 0.0, 32.0), axis=(1.0, 0.0, 0.0))

    # Düzlemsel Krank-Biyel-Piston Kinematik Çözücüsü
    asm.add_slider_crank_relation(
        crank_part="crankshaft",
        conrod_part="connecting_rod",
        piston_part="slider_piston",
        crank_radius=R,
        conrod_length=L,
        crank_center=(0.0, 0.0, 17.0),
        slide_axis=(1.0, 0.0, 0.0)
    )

    # Anlık Kinematik Konum Hesabı (90 derece için)
    states = asm.solve_motion("crankshaft", value=90.0)
    print(f"Piston Konumu: {states['slider_piston'].translation_mm:.2f} mm")
    print(f"Biyel Açısı: {states['connecting_rod'].angle_deg:.2f}°")
```

---

## 4. Dişli Transmisyonları & Kremayer-Pinyon

Evolvent profilli düz dişliler, sessiz helisel dişliler ve doğrusal kremayer mekanizmaları:

```python
with Assembly("Reduktor_Kademesi", units="mm") as asm:
    # Pinyon Dişli (m=2.5, z=20)
    pinion = asm.add_spur_gear("pinion", module=2.5, teeth=20, face_width=20.0, bore_dia=16.0, origin=(0, 0, 0))

    # Çark Dişli (m=2.5, z=40) - Merkez Mesafesi a = 75 mm
    wheel = asm.add_spur_gear("wheel", module=2.5, teeth=40, face_width=20.0, bore_dia=25.0, origin=(75.0, 0, 0))

    # Kinematik Dönüş Oranı Bağlantısı
    asm.add_revolute_joint("pinion", origin=(0, 0, 0), axis=(0, 0, 1))
    asm.add_revolute_joint("wheel", origin=(75.0, 0, 0), axis=(0, 0, 1))
    asm.add_gear_relation("pinion", "wheel", ratio=0.5, reverse=True)
```

---

## 5. Sac Metal Modelleme (DIN 6935 K-Faktörü)

Büküm payı ve sac açınım hesabı yapan endüstriyel sac şekillendirme:

```python
with Assembly("Sac_Braket", units="mm") as asm:
    bracket = asm.add_sheet_metal_bracket(
        name="sasi_braketi",
        bracket_type="U",       # "L", "U", "Z" veya "HAT"
        width=50.0,
        length1=60.0,
        length2=40.0,
        thickness=2.0,
        k_factor=0.44,          # Standart çelik büküm K-faktörü
        hole_diameter=8.5
    )
```

---

## 6. Motorsport Donanımları & Süspansiyon

Yarış araçları ve yüksek performanslı şasiler için hazır kütüphane:

```python
with Assembly("Yaris_Tekerlegi", units="mm") as asm:
    rotor = asm.add_brake_rotor("fren_diski", outer_diameter=240.0)
    kaliper = asm.add_brake_caliper("kaliper", length=140.0)
    bijon = asm.add_centerlock_nut("centerlock_bijon", size="M30")
    amortisör = asm.add_coilover("yaris_amortisoru", extended_length=320.0, stroke=80.0, wire_dia=10.0)
    mafsal = asm.add_heim_joint("unibal_rotbasi", thread_size="M10")
```

---

## 7. Standart Parçalar & Alüminyum Profiller

Tek satırda DIN/ISO standart bileşenler:

```python
# Sigma Alüminyum Profil
ray = asm.add_profile("vslot_2040", profile_type="2040", length=400.0)

# Step Motor
motor = asm.add_motor("step_motor", frame="NEMA17", body_length=40.0)

# Standart Rulman & Cıvata
rulman = asm.add_bearing("bilyali_rulman", standard="SKF", code="608ZZ")
civata = asm.add_bolt("baglanti_civatasi", size="M6", length=25.0)
somun = asm.add_nut("somun", standard="DIN934", size="M6")
```

---

## 8. Organik Yüzeyler & NACA Kanat Profilleri

Akışkanlar mekaniği ve havacılık için C2 süreklilikte pürüzsüz NURBS kanat profilleri:

```python
with Assembly("Kanat_Profili", units="mm") as asm:
    kok = asm.section_naca(code="2412", chord=180.0, center=(0, 0, 0))
    uc = asm.section_naca(code="0012", chord=110.0, center=(0, 300.0, 40.0))
    kanat = asm.add_loft("aerodinamik_kanat", sections=[kok, uc])
```

---

## 9. 2D ISO Teknik Resim Üretimi (HLR)

OpenCASCADE Hidden Line Removal (HLR) algoritmasıyla görünmeyen kenarları kesik çizgi, görünen kenarları net çizgi olarak A4/A3 mühendislik teknik resmine dönüştürme:

```python
asm.export_drawing(
    filepath="teknik_resim_A4.svg",
    sheet_size="A4",
    title="KRANK-BIYEL MEKANIZMASI",
    material="Steel4140"
)
```

---

## 10. İnteraktif 3D WebGL Hareket Simülasyonu

Three.js tabanlı, tarayıcıda doğrudan çalışan, motoru çalıştırıp durdurabileceğiniz, hız ve patlatılmış görünüm (exploded view) ayarlı bağımsız simülasyon:

```python
asm.export_motion_html(
    filepath="simulasyon.html",
    title="KRANK-BIYEL SIMULATORU",
    driver_part="crankshaft"
)
```

---

## 11. Geometri Doğrulama, Çakışma Testi ve Kütle Özellikleri

```python
from cadi_saml import ValidationEngineer

validator = ValidationEngineer()

# Su geçirmez katı kontrolü
is_manifold = validator.check_manifold(solid)

# Parçalar birbiri içine giriyor mu (Clash Detection)?
clashes = validator.check_clashes(solids)
if clashes:
    print(f"Uyarı: {len(clashes)} adet parça çakışması tespit edildi!")

# Kütle, ağırlık merkezi ve eylemsizlik momenti hesabı
props = asm.get_mass_properties()
print(f"Toplam Ağırlık: {props['total_mass_kg']:.3f} kg")
print(f"Ağırlık Merkezi (X, Y, Z): {props['center_of_gravity']}")
```

---

## 12. Yeni Nesil Montaj Makroları (v0.5.0)

Münferit parça modellemenin ötesine geçerek birbiriyle eşleşen parçaları, bağlantı elemanlarını ve mühendislik hesaplarını tek komutta oluşturan akıllı montaj makroları:

### A) Otomatik Cıvata-Somun Bağlantısı (`add_bolted_joint`)
Delik portları arasındaki sıkma kalınlığını (`grip_length`) hesaplar, ISO 4014 / DIN 912 standardına göre nominal cıvata boyunu otomatik seçer, pulları ve somunu ekleyip diş tutunma emniyetini raporlar:

```python
joint_report = asm.add_bolted_joint(
    name="flans_baglantisi",
    thread="M10",
    bolt_type="hex_head",
    with_washer_head=True,
    with_washer_nut=True,
    with_nut=True,
    grip_length=24.0  # mm
)
print("Seçilen Cıvata:", joint_report["standard_designation"])
print("Diş Emniyet Kontrolü:", joint_report["engagement_check_passed"])
```

### B) Takviyeli Montaj Braketi (`add_mounting_bracket`)
L veya U tipi form verilmiş sac veya işlenmiş braket, feder takviyesi (`gusset`) ve montaj deliklerini birlikte üretir:

```python
bracket = asm.add_mounting_bracket(
    name="chassis_mount",
    bracket_type="L",
    width=60.0,
    length1=80.0,
    length2=70.0,
    thickness=4.0,
    with_gusset=True
)
```

### C) Profil Şase ve Testere Kesim Listesi (`add_profile_frame`)
Sigma (t-slot) veya kutu profillerden 3D şase iskeleti kurar ve testere kesim listesini (`cut_list`) hesaplar:

```python
frame = asm.add_profile_frame(
    name="cihaz_sasesi",
    profile_type="4040",
    length_x=800.0,
    width_y=500.0,
    height_z=600.0
)
print("Toplam Profil İhtiyacı:", frame["total_profile_length_meters"], "metre")
```

### D) Kinematik Eşleşmiş Dişli Çifti (`add_gear_pair`)
İki dişlinin modül uyumunu denetler, teorik merkez mesafesini $a = m \cdot (z_1 + z_2) / 2$ hesaplar, teğet yerleştirir ve aralarındaki dişli hareket ilişkisini otomatik kurar:

```python
reducer = asm.add_gear_pair(
    name="tahrik_grubu",
    pinion_teeth=18,
    gear_teeth=54,
    module=2.5,
    face_width=30.0
)
print("Çevrim Oranı (i):", reducer["reduction_ratio"])  # 3.0
print("Merkez Mesafesi:", reducer["center_distance_mm"], "mm")  # 90.0 mm
```

### E) Yataklama ve Rulman Ünitesi (`add_bearing_support`)
Standart SKF rulman, yatak gövdesi (pillow block veya 4 civatalı flanşlı) ve kapak grubunu birleştirir:

```python
asm.add_bearing_support(
    name="mil_yatagi",
    shaft_dia=25.0,
    housing_type="pillow_block",
    bearing_series="6205"
)
```

### F) Kademeli Mil Dizilimi (`add_shaft_stack`)
Kademeli mil üzerine sırasıyla rulman, dişli, burç ve segmanları eksenel sırayla yerleştirir:

```python
asm.add_shaft_stack(
    name="ana_mil_grubu",
    shaft_name="ana_mil",
    steps=[(20.0, 30.0), (25.0, 45.0), (30.0, 60.0), (25.0, 40.0)],
    stack_elements=[
        {"step_index": 1, "type": "bearing", "name": "on_rulman"},
        {"step_index": 2, "type": "gear", "teeth": 24, "name": "pinyon_disli"}
    ]
)
```

---

## 13. Makine Elemanları ve İşleme Detayları

Parça referansı üzerinden doğrudan zincirleme çağrılabilen hassas talaşlı imalat detayları:

```python
# Kademeli mil üzerinde kama yuvası (DIN 6885) ve segman kanalı (DIN 471)
mil = asm.add_cylinder("mil", radius=15.0, height=120.0)
mil.add_keyway(width=8.0, depth=4.0, length=45.0, shaft_dia=30.0)
mil.add_retaining_ring_groove(shaft_dia=30.0, groove_dia=28.0, width=1.3, position_z=100.0)

# Gövde üzerinde alyan cıvata havşa yuvası (Counterbore) ve freze cebi
govde = asm.add_box("govde", 100, 100, 40)
govde.add_counterbore(cbore_dia=15.0, cbore_depth=8.0, hole_dia=9.0, origin=(30.0, 30.0, 40.0))
govde.add_pocket(length=50.0, width=50.0, depth=15.0, origin=(50.0, 50.0, 25.0))
```

---

## 14. LLM ve Agent Keşif Motoru (Self-Describing API)

Yapay Zekâ ve otonom mühendislik agent'larının kütüphaneyi runtime'da keşfetmesi ve hatasız parametre üretmesi için:

```python
# Kütüphanenin tüm kabiliyetlerini JSON şeması olarak al
schema = asm.list_capabilities()

# Belirli bir makronun parametrelerini, beklenen portlarını ve örnek kodunu sorgula
macro_info = asm.describe_macro("add_bolted_joint")
print(macro_info["parameters"])
print(macro_info["example"])

# Montajdaki tüm açık portları listele
available_ports = asm.list_ports()
```

---

## 15. İmalat Çıktıları ve Raporlama (BOM & Cut-List)

```python
# Malzeme Listesi (BOM - Bill of Materials)
bom = asm.export_bom("montaj_bom.json")

# Profil ve Boru Kesim Listesi (Testere boyları ve açıları)
cut_list = asm.export_cut_list("kesim_listesi.json")

# Kapsamlı Mühendislik Doğrulama Raporu
report = asm.generate_validation_report()
print("Montaj Doğrulama Durumu:", report["status"])
```

---

## 16. Strict LLM Modu, Post-Build Doğrulama Sözleşmesi ve Willis Planet Kinematiği (v0.6.0)

### Strict LLM Modu ve `CADISpecificationError`
LLM eksik, hatalı veya standart dışı bir parametre gönderdiğinde kütüphane asla sessiz varsayım yapmaz veya uydurma geometri üretmez:
- Tanımsız vida ölçüsü (örn. `thread="M99"`) sessizce M8'e dönüştürülmez.
- Geçersiz boru rotaları veya çakışık portlar sessizce düz boru eklemez.
- Çözülemeyen planet dişli oranları keyfi 18/18/54 diş dönmez.
- Tanımsız kam kanunları sessizce lineer profile düşmez.

Bunun yerine yapılandırılmış `CADISpecificationError` fırlatılır:
```python
from cadi_saml import CADISpecificationError

try:
    asm.add_threaded_hole(target_part="govde", thread="UNKNOWN_SPEC")
except CADISpecificationError as err:
    print("Hatalı Parametre:", err.parameter_name)
    print("Girilen Değer:", err.provided_value)
    print("Geçerli Seçenekler:", err.valid_options)
    print("Düzeltme Önerisi:", err.suggested_fix)
```

### Parametre Kaynağı (Specification Provenance) İzleme
Üretilen her ölçünün hangi JSON alanından veya standart tablosundan geldiğini kaydeder:
```python
govde = asm.add_box("govde", 100, 80, 20)
govde.track_provenance("length", source="llm_json", source_ref="payload.specs.length_mm", confidence=1.0)
govde.track_provenance("material", source="catalog_din", source_ref="DIN 17100")
```

### Post-Build Doğrulama Sözleşmesi (`verify_contract`)
6 aşamalı otomatik doğrulama zinciri:
1. `compilation`: Katı gövde derleme
2. `manifold`: Su sızdırmazlık ve topoloji kontrolü
3. `dimensions`: Pozitif hacim ve boyut doğrulaması
4. `interference`: Çakışma / tolerans denetimi
5. `kinematics`: Serbestlik ve kinematik ilişki tutarlılığı
6. `step_roundtrip`: STEP AP214 dışa aktarma, OCCT ile geri okuma ve hacim korunumu ($< 0.5\%$)

```python
contract_report = asm.verify_contract(test_step_roundtrip=True, check_clash=True)
if not contract_report.passed:
    print("Sözleşme Başarısız:", contract_report.summary)
```

### Willis Bağıntılı Planet Kinematiği ve Evolvent İç Dişli
Planet dişli mekanizmaları Willis bağıntısına ($\frac{\omega_s - \omega_c}{\omega_r - \omega_c} = -\frac{z_r}{z_s}$) göre çözülür ve iç çember dişlisi analitik evolvent diş geometrisiyle oluşturulur:
```python
# Analitik iç evolvent dişli çemberi
ring = asm.add_internal_gear(
    name="ring_gear",
    module=2.0,
    teeth=48,
    face_width=20.0,
    rim_thickness=12.0,
    bolt_count=6,
    bolt_diameter=6.0,
    bolt_pcd=120.0,
)

# Willis kinematik ilişkisi
asm.add_planetary_relation(
    sun_part="sun",
    carrier_part="carrier",
    ring_part="ring_gear",
    planet_parts=["planet_1", "planet_2", "planet_3"],
    fixed_component="ring",
)
```

---

## 📄 Lisans
MIT Lisansı. CADi Geliştirici Ekibi tarafından hazırlanmıştır.
