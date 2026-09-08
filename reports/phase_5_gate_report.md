# CADi SAML Faz 5 Çıkış Kapısı Doğrulama Raporu
**Faz Adı:** STEP'ten Bağımsız Kod Üretimi  
**Karar (Verdict):** `GATE_PASSED`  
**Sözleşme Sürümü:** `1.0.0`  
**Zaman Damgası (UTC):** `2026-09-07T16:22:35.196781+00:00`  

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
| Geçen Testler (`passed`) | **8** |
| Atlanan Testler (`skipped`) | 0 |
| Başarısız Testler (`failed`) | 0 |
| Engellenen / Hatalı Testler (`blocked`) | 0 |
| Bulunamayan / Eksik Testler | 0 |
| Manifest Doğrulandı | EVET |
| Negatif/Ret Senaryoları | BAŞARILI |
| **Kapı Onayı** | **ONAYLANDI (GATE_PASSED)** |

## 4. Gerçek Çalıştırılan Test Node ID'leri Dökümü
```text
PASSED     : tests/test_step_reconstruction_regression.py::test_regression_cylinder_with_holes
PASSED     : tests/test_step_reconstruction_regression.py::test_regression_flange_and_bolt_pattern
PASSED     : tests/test_step_reconstruction_regression.py::test_regression_oblique_axis_cylinder
PASSED     : tests/test_step_reconstruction_regression.py::test_regression_simple_box
PASSED     : tests/test_step_reconstruction_regression.py::test_regression_simple_cylinder
PASSED     : tests/test_step_reconstruction_regression.py::test_regression_stepped_shaft
PASSED     : tests/test_step_reconstruction_regression.py::test_regression_stepped_shaft_with_holes
PASSED     : tests/test_step_reconstruction_regression.py::test_regression_zero_step_dependency_after_file_deletion
```

---
*Bu rapor CADi SAML GateValidator tarafından otomatik üretilmiş, taşınabilir ve deterministiktir.*
