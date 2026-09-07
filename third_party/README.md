# CADi SAML üçüncü taraf bileşenleri

Bu klasör, CADi SAML kaynak koduna gömülmesi gerekmeyen açık kaynak yardımcı projeler içindir.

## Kaynak Koduna Entegre Edilenler

- `meshio` — mesh dosyalarını farklı formatlar arasında dönüştürmek için kullanılan kütüphane (`v5.3.5`, MIT Lisansı).
  - Kaynak: https://github.com/nschloe/meshio
  - Konum: `src/meshio/`
  - Kullanım: FEA/CFD adaptörleri için mesh içe/dışa aktarma ve format dönüşümleri. Depodaki gereksiz test/git/doc çöpleri temizlenmiş, yalnızca çalışma zamanı için gerekli Python modülleri ve lisans dosyası aktarılmıştır.

## Harici kurulacak, depoya kopyalanmayacak

- OpenFOAM — CFD çözücüsü ve vaka şablonları
- SU2 — alternatif CFD/çoklu fizik çözücüsü
- Code_Aster/Salome-Meca — yapısal ve termal FEA
- Gmsh — mesh üretimi
- OpenCASCADE — CAD çekirdeği (Python binding üzerinden)

Bu projelerin lisans metinleri ve sürümleri dağıtım paketinde ayrıca kaydedilmelidir. Çözücülerin tamamını bu klasöre kopyalamak yerine kurulum denetimi ve sürümlü adaptör kullanılacaktır.
