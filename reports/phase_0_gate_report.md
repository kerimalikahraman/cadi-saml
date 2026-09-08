# CADi SAML Faz 0 Çıkış Kapısı Doğrulama Raporu
**Faz Adı:** Kaynak ve Sözleşme Dondurma  
**Karar (Verdict):** `GATE_PASSED`  
**Sözleşme Sürümü:** `1.0.0`  
**Zaman Damgası (UTC):** `2026-09-07T16:21:37.357510+00:00`  

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
PASSED     : tests/test_phase_0_contracts_and_gates.py::test_contracts_immutability_and_schemas
PASSED     : tests/test_phase_0_contracts_and_gates.py::test_manifest_schema_and_canonical_mapping
PASSED     : tests/test_phase_0_contracts_and_gates.py::test_negative_invalid_index_base_rejection
PASSED     : tests/test_phase_0_contracts_and_gates.py::test_negative_mixed_base_rejection
```

---
*Bu rapor CADi SAML GateValidator tarafından otomatik üretilmiş, taşınabilir ve deterministiktir.*
