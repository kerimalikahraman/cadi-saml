# CADi SAML Faz 8 Çıkış Kapısı Doğrulama Raporu
**Faz Adı:** LLM Entegrasyon Sınırı  
**Karar (Verdict):** `GATE_PASSED`  
**Sözleşme Sürümü:** `1.0.0`  
**Zaman Damgası (UTC):** `2026-09-07T16:23:04.400921+00:00`  

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
PASSED     : tests/test_llm_interface.py::test_compact_inspect_and_semantic_diff
PASSED     : tests/test_llm_interface.py::test_preview_patch_isolated_validation_commit_and_conflict
PASSED     : tests/test_llm_interface.py::test_preview_patch_rejects_unknown_or_invalid_paths_without_mutation
PASSED     : tests/test_llm_interface.py::test_runtime_schema_is_json_safe_and_matches_signature
PASSED     : tests/test_token_reduction.py::test_token_reduction_benchmark
```

---
*Bu rapor CADi SAML GateValidator tarafından otomatik üretilmiş, taşınabilir ve deterministiktir.*
