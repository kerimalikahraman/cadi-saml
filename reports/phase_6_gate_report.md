# CADi SAML Faz 6 Çıkış Kapısı Doğrulama Raporu
**Faz Adı:** Şasi, Süspansiyon ve Batarya  
**Karar (Verdict):** `GATE_PASSED`  
**Sözleşme Sürümü:** `1.0.0`  
**Zaman Damgası (UTC):** `2026-09-07T16:22:47.602894+00:00`  

## 1. Çalışma Ortamı (Environment)
| Değişken | Değer |
| :--- | :--- |
| Python Sürümü | `3.14.6` |
| Pytest Sürümü | `9.1.1` |
| İşletim Sistemi | `Windows-11-10.0.26200-SP0` |
| Mimari | `AMD64` |

## 2. Çıkış Kapısı Özeti
| Metrik | Değer |
| :--- | :--- |
| Geçen Testler (`passed`) | **5** |
| Atlanan Testler (`skipped`) | 0 |
| Başarısız Testler (`failed`) | 0 |
| Engellenen / Hatalı Testler (`blocked`) | 0 |
| Bulunamayan / Eksik Testler | 0 |
| Manifest Doğrulandı | EVET |
| Negatif/Ret Senaryoları | BAŞARILI |
| **Kapı Onayı** | **ONAYLANDI (GATE_PASSED)** |

## 4. Gerçek Çalıştırılan Test Node ID'leri Dökümü
```text
PASSED     : tests/test_heterogeneous_fea.py::test_invalid_material_region_and_unassigned_elements
PASSED     : tests/test_systems_vehicle.py::test_battery_pack_enclosure_and_cooling_flow
PASSED     : tests/test_systems_vehicle.py::test_chassis_frame_synthesis_and_mass_distribution
PASSED     : tests/test_systems_vehicle.py::test_integrated_vehicle_platform_and_cad_compile
PASSED     : tests/test_systems_vehicle.py::test_suspension_hardpoints_and_kinematics
```

---
*Bu rapor CADi SAML GateValidator tarafından otomatik üretilmiş, taşınabilir ve deterministiktir.*
