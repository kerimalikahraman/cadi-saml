# CADi SAML Faz 2 Çıkış Kapısı Doğrulama Raporu
**Faz Adı:** Gerçek Solver ve Mesh Doğrulaması  
**Karar (Verdict):** `GATE_PASSED`  
**Sözleşme Sürümü:** `1.0.0`  
**Zaman Damgası (UTC):** `2026-09-07T16:21:59.800104+00:00`  

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
PASSED     : tests/test_fea_verification_and_convergence.py::test_analytical_cantilever_benchmark
PASSED     : tests/test_fea_verification_and_convergence.py::test_analytical_uniaxial_tension_benchmark
PASSED     : tests/test_fea_verification_and_convergence.py::test_mesh_convergence_study_converged_progression
PASSED     : tests/test_fea_verification_and_convergence.py::test_mesh_convergence_study_unconverged_behavior
PASSED     : tests/test_heterogeneous_fea.py::test_calculix_runner_mocked_external_ccx
```

---
*Bu rapor CADi SAML GateValidator tarafından otomatik üretilmiş, taşınabilir ve deterministiktir.*
