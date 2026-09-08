# CADi SAML Faz 1 Çıkış Kapısı Doğrulama Raporu
**Faz Adı:** FEA Temel Güvenilirliği  
**Karar (Verdict):** `GATE_PASSED`  
**Sözleşme Sürümü:** `1.0.0`  
**Zaman Damgası (UTC):** `2026-09-07T16:21:48.177888+00:00`  

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
| Geçen Testler (`passed`) | **10** |
| Atlanan Testler (`skipped`) | 0 |
| Başarısız Testler (`failed`) | 0 |
| Engellenen / Hatalı Testler (`blocked`) | 0 |
| Bulunamayan / Eksik Testler | 0 |
| Manifest Doğrulandı | EVET |
| Negatif/Ret Senaryoları | BAŞARILI |
| **Kapı Onayı** | **ONAYLANDI (GATE_PASSED)** |

## 4. Gerçek Çalıştırılan Test Node ID'leri Dökümü
```text
PASSED     : tests/test_fea_verification_and_convergence.py::test_element_indexing_boundary_first_and_last_elements
PASSED     : tests/test_heterogeneous_fea.py::test_fiber_direction_rejection_not_implemented
PASSED     : tests/test_heterogeneous_fea.py::test_overlapping_material_regions_raise_error
PASSED     : tests/test_phase_1_fea_reliability.py::test_empty_material_region_rejection
PASSED     : tests/test_phase_1_fea_reliability.py::test_first_and_last_boundary_elements_coverage
PASSED     : tests/test_phase_1_fea_reliability.py::test_invalid_and_out_of_bounds_element_id_rejection
PASSED     : tests/test_phase_1_fea_reliability.py::test_linear_isotropic_solver_preservation
PASSED     : tests/test_phase_1_fea_reliability.py::test_missing_material_definition_and_unassigned_elements
PASSED     : tests/test_phase_1_fea_reliability.py::test_mixed_base_rejection
PASSED     : tests/test_phase_1_fea_reliability.py::test_overlapping_material_regions_rejection
```

---
*Bu rapor CADi SAML GateValidator tarafından otomatik üretilmiş, taşınabilir ve deterministiktir.*
