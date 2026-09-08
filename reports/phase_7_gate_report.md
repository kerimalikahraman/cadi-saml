# CADi SAML Faz 7 Çıkış Kapısı Doğrulama Raporu
**Faz Adı:** Bağlantı ve İleri Analiz  
**Karar (Verdict):** `GATE_PASSED`  
**Sözleşme Sürümü:** `1.0.0`  
**Zaman Damgası (UTC):** `2026-09-07T16:22:55.364315+00:00`  

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
| Geçen Testler (`passed`) | **3** |
| Atlanan Testler (`skipped`) | 0 |
| Başarısız Testler (`failed`) | 0 |
| Engellenen / Hatalı Testler (`blocked`) | 0 |
| Bulunamayan / Eksik Testler | 0 |
| Manifest Doğrulandı | EVET |
| Negatif/Ret Senaryoları | BAŞARILI |
| **Kapı Onayı** | **ONAYLANDI (GATE_PASSED)** |

## 4. Gerçek Çalıştırılan Test Node ID'leri Dökümü
```text
PASSED     : tests/test_fea_verification_and_convergence.py::test_bimetal_interface_stress_extraction
PASSED     : tests/test_heterogeneous_fea.py::test_boundary_condition_explicit_dofs_and_values
PASSED     : tests/test_heterogeneous_fea.py::test_fiber_direction_rejection_not_implemented
```

---
*Bu rapor CADi SAML GateValidator tarafından otomatik üretilmiş, taşınabilir ve deterministiktir.*
