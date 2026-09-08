# CADi SAML Faz 4 Çıkış Kapısı Doğrulama Raporu
**Faz Adı:** Taşınabilir Rapor ve Veri Hattı  
**Karar (Verdict):** `GATE_PASSED`  
**Sözleşme Sürümü:** `1.0.0`  
**Zaman Damgası (UTC):** `2026-09-07T16:22:23.559753+00:00`  

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
| Geçen Testler (`passed`) | **4** |
| Atlanan Testler (`skipped`) | 0 |
| Başarısız Testler (`failed`) | 0 |
| Engellenen / Hatalı Testler (`blocked`) | 0 |
| Bulunamayan / Eksik Testler | 0 |
| Manifest Doğrulandı | EVET |
| Negatif/Ret Senaryoları | BAŞARILI |
| **Kapı Onayı** | **ONAYLANDI (GATE_PASSED)** |

## 4. Gerçek Çalıştırılan Test Node ID'leri Dökümü
```text
PASSED     : tests/test_fea_verification_and_convergence.py::test_calculix_model_index_base_and_multi_material_contract
PASSED     : tests/test_fea_verification_and_convergence.py::test_element_indexing_strict_validation_and_rejection
PASSED     : tests/test_fea_verification_and_convergence.py::test_portable_fea_report_generation
PASSED     : tests/test_heterogeneous_fea.py::test_fea_result_permanent_dataclass_fields
```

---
*Bu rapor CADi SAML GateValidator tarafından otomatik üretilmiş, taşınabilir ve deterministiktir.*
