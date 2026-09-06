"""
scripts.generate_negative_dataset
=================================
Generates a structured negative / error-handling dataset (JSONL)
for fine-tuning LLMs on CADi SAML error prevention and constraint diagnostics.

Key Principle:
When given physically impossible, underspecified, contradictory, or invalid CAD requests,
the LLM must NOT fabricate geometry or invent dimensions.
Instead, it must output a structured CADISpecificationError with a clean suggested_fix.

Conforms to schema/saml_dataset_schema.json.
Total cases: 30 (15 pairs of English & Turkish failure scenarios with executable offending scripts).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import cadi_saml


def compute_sample_checksum(prompt: str, code: str) -> str:
    data = f"{prompt.strip()}||{code.strip()}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def generate_negative_samples(seed: int = 42) -> list[dict]:
    samples = []
    sample_id = 1
    lib_version = getattr(cadi_saml, "__version__", "0.6.0")

    negative_cases = [
        # 1. Missing diameter on pipe without standard
        {
            "instruction": "Route an L-shaped hydraulic line between ports without specifying outer diameter or standard.",
            "error_type": "CADISpecificationError",
            "parameter": "outer_dia",
            "message": "Boru dış çapı (outer_dia) belirtilmedi ve standart boru normu (standard) verilmedi.",
            "suggested_fix": "Geçerli bir boru normu (örn: standard='DN25') veya doğrudan dış çap (örn: outer_dia=25.0) belirtin.",
            "category": "specification_error_handling",
            "standards": ["ISO 4200"],
            "reasoning": "Piping macro requires either explicit positive outer_dia or standard schedule (e.g. DN25). Geometry cannot be swept without wall profile.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('BadPipe')\nasm.add_pipe_route('line', from_port=(0,0,0), to_port=(100,0,0))\n",
        },
        {
            "instruction": "Çapı veya normu belirtilmeden (0,0,0)'dan (100,0,0)'a giden boru hattı çiz.",
            "error_type": "CADISpecificationError",
            "parameter": "outer_dia",
            "message": "Boru dış çapı (outer_dia) pozitif bir sayı olmalıdır veya geçerli bir 'standard' belirtilmelidir.",
            "suggested_fix": "Örn: outer_dia=25.0 veya standard='DN25' parametresini ekleyin.",
            "category": "specification_error_handling",
            "standards": ["ISO 4200"],
            "reasoning": "Boru profilinin süpürülmesi için dış çap veya EN 10220/ISO 4200 normu zorunludur.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('BoruHat')\nasm.add_pipe('hat', points=[(0,0,0), (100,0,0)], outer_dia=0.0)\n",
        },

        # 2. Unknown / invalid thread standard
        {
            "instruction": "Tap an M999x12.5 extra giant thread on the machine mounting block.",
            "error_type": "CADISpecificationError",
            "parameter": "thread",
            "message": "Unknown metric thread standard: 'M999'. Not registered in ISO 965 catalog.",
            "suggested_fix": "Choose a standard ISO metric coarse thread: M3, M4, M5, M6, M8, M10, M12, M14, M16, M20, M24.",
            "category": "specification_error_handling",
            "standards": ["ISO 965-1"],
            "reasoning": "M999 does not exist in ISO 965 metric coarse thread tables. Tapped hole operation must be rejected.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('BadThread')\nb = asm.add_box('block', 100, 100, 50)\nasm.add_threaded_hole('block', thread='M999', depth=20.0)\n",
        },
        {
            "instruction": "Taban bloğuna M73x4.5 dişli kılavuz çekilmiş delik ekle.",
            "error_type": "CADISpecificationError",
            "parameter": "thread",
            "message": "Bilinmeyen metrik vida normu: 'M73'. ISO 965 standardında bulunamadı.",
            "suggested_fix": "Standart metrik vida serisinden birini seçin (M6, M8, M10, M12, M16, M20).",
            "category": "specification_error_handling",
            "standards": ["ISO 965-1"],
            "reasoning": "M73 standart dışıdır; takım kütüphanesinde kılavuz geometrisi bulunamaz.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('Taban')\nb = asm.add_box('govde', 80, 80, 40)\nasm.add_threaded_hole('govde', thread='M73', depth=15.0)\n",
        },

        # 3. Physically impossible planetary gearbox teeth relation
        {
            "instruction": "Build an epicyclic planetary gearbox with sun 20T, ring 55T, and 3 planets.",
            "error_type": "CADISpecificationError",
            "parameter": "ring_teeth",
            "message": "Kinematically impossible epicyclic gear train: z_ring (55) - z_sun (20) = 35 is not divisible by 2. Planet tooth count (17.5) must be an integer.",
            "suggested_fix": "Set z_ring = z_sun + 2 * z_planet. For z_sun=20, choose z_ring=56 (z_planet=18) or z_ring=60 (z_planet=20).",
            "category": "specification_error_handling",
            "standards": ["Willis Epicyclic Relation", "DIN 3960"],
            "reasoning": "Willis epicyclic kinematics strictly dictates z_ring = z_sun + 2 * z_planet. Odd difference produces fractional planet teeth.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('BadPlanet')\nasm.add_cylinder('sun', 10, 20)\nasm.add_cylinder('carrier', 20, 20)\nasm.add_cylinder('ring', 30, 20)\nasm.add_cylinder('p1', 5, 20)\nasm.add_planetary_relation('sun', 'carrier', 'ring', ['p1'], z_sun=20, z_ring=55)\n",
        },
        {
            "instruction": "Güneş dişlisi 21, çember dişlisi 50 ve 3 planetli redüktör kademesi modelle.",
            "error_type": "CADISpecificationError",
            "parameter": "ring_teeth",
            "message": "Geçersiz planet dişli ilişkisi: z_ring (50) - z_sun (21) = 29 tek sayı olduğu için planet diş sayısı (14.5) tamsayı olamaz.",
            "suggested_fix": "z_ring = z_sun + 2 * z_planet formülüne uygun diş sayısı seçin (örn: z_sun=21 için z_ring=63, z_planet=21).",
            "category": "specification_error_handling",
            "standards": ["Willis Epicyclic Relation"],
            "reasoning": "Planet redüktörlerde eş eksenli montaj için diş sayısı farkı çift sayı olmak zorundadır.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('PlanetReduktor')\nasm.add_cylinder('sun', 10, 20)\nasm.add_cylinder('carrier', 20, 20)\nasm.add_cylinder('ring', 30, 20)\nasm.add_cylinder('p1', 5, 20)\nasm.add_planetary_relation('sun', 'carrier', 'ring', ['p1'], z_sun=21, z_ring=50)\n",
        },

        # 4. Ghost part in contract specification
        {
            "instruction": "Verify assembly contract expecting specifications for a nonexistent 'bearing_carrier' part.",
            "error_type": "CADISpecificationError",
            "parameter": "expected_specs.parts",
            "message": "Contract specification references nonexistent part 'bearing_carrier' (not found in assembly parts list).",
            "suggested_fix": "Remove 'bearing_carrier' from expected_specs or add the part to the assembly before contract verification.",
            "category": "specification_error_handling",
            "standards": ["CADI-SAML Strict Contract Specification"],
            "reasoning": "A post-build contract cannot validate or pass an assembly that has unfulfilled ghost part constraints.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('GhostAsm')\nasm.add_box('base', 50, 50, 20)\nrep = asm.verify_contract(expected_specs={'parts': {'bearing_carrier': {'volume_mm3': 1000.0}}})\nassert rep.passed\n",
        },
        {
            "instruction": "Montajda bulunmayan 'motor_braketi' parçası için hacim doğrulaması yapan kontrat çalıştır.",
            "error_type": "CADISpecificationError",
            "parameter": "expected_specs.parts",
            "message": "Şartnamede belirtilen 'motor_braketi' isimli parça montajda mevcut değil.",
            "suggested_fix": "Montaja parçayı ekleyin veya şartnameden 'motor_braketi' gereksinimini kaldırın.",
            "category": "specification_error_handling",
            "standards": ["CADI-SAML Strict Contract Specification"],
            "reasoning": "Montajda yer almayan hayalet parça gereksinimleri kontrat tarafından anında reddedilmelidir.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('HayaletMontaj')\nasm.add_box('sasi', 60, 60, 20)\nrep = asm.verify_contract(expected_specs={'parts': {'motor_braketi': {'volume_mm3': 5000.0}}})\nassert rep.passed\n",
        },

        # 5. Non-numeric or NaN tolerance in contract
        {
            "instruction": "Verify assembly contract with max_clash_volume_mm3 set to NaN to ignore collision detection.",
            "error_type": "CADISpecificationError",
            "parameter": "max_clash_volume_mm3",
            "message": "Invalid collision threshold: max_clash_volume_mm3=NaN. Must be a finite, non-negative float.",
            "suggested_fix": "Pass a valid non-negative float threshold (e.g. max_clash_volume_mm3=0.0 or 5.0).",
            "category": "specification_error_handling",
            "standards": ["IEEE 754 Floating Point Compliance"],
            "reasoning": "Passing NaN to collision or volume tolerances breaks comparison predicates and is rejected in strict mode.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('NanTol')\nasm.add_box('p1', 20, 20, 20)\nrep = asm.verify_contract(max_clash_volume_mm3=float('nan'))\nassert rep.passed\n",
        },
        {
            "instruction": "Hacim toleransı olarak 'none' veya NaN vererek montajı doğrula.",
            "error_type": "CADISpecificationError",
            "parameter": "volume_tolerance_ratio",
            "message": "Geçersiz hacim tolerans oranı: Değer sonlu ve pozitif bir sayı olmalıdır.",
            "suggested_fix": "Örn: volume_tolerance_ratio=0.05 gibi geçerli bir oran belirtin.",
            "category": "specification_error_handling",
            "standards": ["IEEE 754"],
            "reasoning": "Sayısal olmayan toleranslar kontrat değerlendirmesinde hata döndürmelidir.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('NanHacim')\nasm.add_box('p1', 30, 30, 30)\nrep = asm.verify_contract(volume_tolerance_ratio=float('nan'))\nassert rep.passed\n",
        },

        # 6. Conflicting duplicate specifications
        {
            "instruction": "Specify contradictory volume constraints: parts.box.volume=100.0 and top-level box.volume=50000.0.",
            "error_type": "CADISpecificationError",
            "parameter": "expected_specs",
            "message": "Conflicting/duplicate specification for part 'box': defined in both 'parts.box' and top-level 'box'.",
            "suggested_fix": "Consolidate requirements into either 'parts.box' or top-level 'box', not both.",
            "category": "specification_error_handling",
            "standards": ["CADI-SAML Contract Disambiguation"],
            "reasoning": "Dual contradictory specifications must be explicitly rejected rather than silently overwriting.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('DupSpec')\nasm.add_box('box', 10, 10, 10)\nrep = asm.verify_contract(expected_specs={'parts': {'box': {'volume_mm3': 100.0}}, 'box': {'volume_mm3': 50000.0}})\nassert rep.passed\n",
        },
        {
            "instruction": "Aynı parça için hem parts['flange'] hem de en üst düzeyde çelişkili ölçü şartı tanımla.",
            "error_type": "CADISpecificationError",
            "parameter": "expected_specs",
            "message": "'flange' parçası için çelişkili çift şartname: hem 'parts.flange' hem de 'flange' altında tanımlanmış.",
            "suggested_fix": "Şartnameyi tek bir sözlük altında toplayın.",
            "category": "specification_error_handling",
            "standards": ["CADI-SAML Contract Disambiguation"],
            "reasoning": "Çelişkili şartnameler sessizce kabul edilmemeli, kullanıcıya hata bildirilmelidir.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('CeliskiFlans')\nasm.add_box('flange', 40, 40, 10)\nrep = asm.verify_contract(expected_specs={'parts': {'flange': {'volume_mm3': 16000.0}}, 'flange': {'volume_mm3': 200.0}})\nassert rep.passed\n",
        },

        # 7. Provenance value mismatch (hallucinated provenance)
        {
            "instruction": "Track provenance claiming cylinder diameter is 50.0mm while the actual model was built with radius 10.0mm (OD 20.0mm).",
            "error_type": "CADISpecificationError",
            "parameter": "provenance.effective_value",
            "message": "Part 'pin' parameter 'outer_diameter' provenance effective_value (50.0) does not match actual part parameter (20.0).",
            "suggested_fix": "Ensure provenance effective_value exactly matches the actual runtime dimension of the created part.",
            "category": "specification_error_handling",
            "standards": ["CADI-SAML Provenance Coverage Protocol"],
            "reasoning": "Provenance tracking must maintain complete data fidelity; fraudulent effective_values cause contract failure.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('FakeProv')\np = asm.add_cylinder('pin', radius=10.0, height=50.0)\np.track_provenance('outer_diameter', 'user', 'prompt.dia', 50.0, 50.0)\nrep = asm.verify_contract(require_provenance=True)\nassert rep.passed\n",
        },
        {
            "instruction": "Gerçek boyutu 100mm olan kiriş için provenance kaydına 9999mm yazarak doğrulamadan geçmeye çalış.",
            "error_type": "CADISpecificationError",
            "parameter": "provenance.effective_value",
            "message": "Parça 'girder' 'length' parametresi provenance effective_value (9999.0) gerçek parça parametresiyle (100.0) uyuşmuyor.",
            "suggested_fix": "Provenance effective_value alanına parçanın derlenmiş gerçek değerini yazın.",
            "category": "specification_error_handling",
            "standards": ["CADI-SAML Provenance Coverage Protocol"],
            "reasoning": "Provenance sahteciliği kontrat tarafından engellenmelidir.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('SahteKiris')\ng = asm.add_box('girder', 100.0, 50.0, 20.0)\ng.track_provenance('length', 'user', 'prompt.length', 100.0, 9999.0)\nrep = asm.verify_contract(require_provenance=True)\nassert rep.passed\n",
        },

        # 8. Provenance for nonexistent parameter
        {
            "instruction": "Track provenance on a simple box for a non-existent parameter 'turbo_boost_pressure'.",
            "error_type": "CADISpecificationError",
            "parameter": "provenance.parameter",
            "message": "Part 'box' contains provenance record for nonexistent parameter 'turbo_boost_pressure' (available: ['length', 'width', 'height']).",
            "suggested_fix": "Only track provenance for valid dimensional parameters of the part.",
            "category": "specification_error_handling",
            "standards": ["CADI-SAML Provenance Coverage Protocol"],
            "reasoning": "Tracking provenance for parameters not present on the B-Rep topology indicates LLM hallucination and is rejected.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('NonexistentParam')\nb = asm.add_box('box', 20, 20, 20)\nb.track_provenance('turbo_boost_pressure', 'user', 'prompt.boost', 2.5, 2.5)\nrep = asm.verify_contract(require_provenance=True)\nassert rep.passed\n",
        },
        {
            "instruction": "Silindir parçasına 'wing_sweep_angle' adında hayali bir parametre için provenance ekle.",
            "error_type": "CADISpecificationError",
            "parameter": "provenance.parameter",
            "message": "Silindir üzerinde 'wing_sweep_angle' adında bir parametre mevcut değil (mevcut parametreler: ['radius', 'height', 'outer_diameter']).",
            "suggested_fix": "Yalnızca parçanın geometrisine ait gerçek parametreleri provenance ile takip edin.",
            "category": "specification_error_handling",
            "standards": ["CADI-SAML Provenance Coverage Protocol"],
            "reasoning": "Parçada bulunmayan hayali ölçülere provenance uydurulması engellenmelidir.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('HayaliParametre')\nc = asm.add_cylinder('silindir', 15.0, 40.0)\nc.track_provenance('wing_sweep_angle', 'user', 'prompt.angle', 35.0, 35.0)\nrep = asm.verify_contract(require_provenance=True)\nassert rep.passed\n",
        },

        # 9. Physically impossible clash / overlap
        {
            "instruction": "Place two 100x100x100mm solid steel blocks at the exact same coordinate (0,0,0) in strict mode.",
            "error_type": "CADISpecificationError",
            "parameter": "interference",
            "message": "Catastrophic interference detected: 'block1' completely clashes with 'block2' (1000000.0 mm3 overlap).",
            "suggested_fix": "Adjust part coordinates or use boolean cut / union operations to eliminate overlapping solids.",
            "category": "specification_error_handling",
            "standards": ["B-Rep Non-Penetration Principle"],
            "reasoning": "Solid physical components cannot occupy the same 3D spatial volume.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('ClashTest')\nasm.add_box('block1', 100, 100, 100, origin=(0,0,0))\nasm.add_box('block2', 100, 100, 100, origin=(0,0,0))\nrep = asm.verify_contract(strict=True)\nassert rep.passed\n",
        },
        {
            "instruction": "Tam üst üste konulmuş iki flanşı çakışma kontrolünden geçirmeye çalış.",
            "error_type": "CADISpecificationError",
            "parameter": "interference",
            "message": "Kritik katı gövde çakışması: 'flange1' ile 'flange2' aynı hacmi paylaşıyor.",
            "suggested_fix": "Parçaları montaj ilişkileri (joint/port) ile eksenel olarak konumlandırın.",
            "category": "specification_error_handling",
            "standards": ["B-Rep Non-Penetration Principle"],
            "reasoning": "İki katı parçanın üst üste çakışması üretimde imkansızdır.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('CakisikFlans')\nasm.add_box('f1', 60, 60, 15, origin=(0,0,0))\nasm.add_box('f2', 60, 60, 15, origin=(0,0,0))\nrep = asm.verify_contract(strict=True)\nassert rep.passed\n",
        },

        # 10. Wall thickness exceeds radius in pipe
        {
            "instruction": "Create a hydraulic pipe with outer diameter 20mm and wall thickness 15mm.",
            "error_type": "CADISpecificationError",
            "parameter": "wall_thickness",
            "message": "Geçersiz et kalınlığı: 15.0 mm (Dış çap: 20.0 mm). Et kalınlığı yarıçaptan (10.0 mm) küçük olmalıdır.",
            "suggested_fix": "0.5 ile 9.5 mm arasında bir et kalınlığı belirtin.",
            "category": "specification_error_handling",
            "standards": ["ISO 4200"],
            "reasoning": "Wall thickness equal to or exceeding radius results in negative inner diameter and self-intersecting geometry.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('ThickPipe')\nasm.add_pipe('pipe', points=[(0,0,0), (50,0,0)], outer_dia=20.0, wall_thickness=15.0)\n",
        },
        {
            "instruction": "Dış çapı 10 mm olan boruya 6 mm et kalınlığı ver.",
            "error_type": "CADISpecificationError",
            "parameter": "wall_thickness",
            "message": "Geçersiz et kalınlığı: 6.0 mm. Yarıçaptan (5.0 mm) büyük et kalınlığı içi dolu veya negatif boru üretir.",
            "suggested_fix": "Et kalınlığını 0.5 ile 4.5 mm arasında seçin.",
            "category": "specification_error_handling",
            "standards": ["ISO 4200"],
            "reasoning": "İç çap negatif olamayacağından katı süpürme işlemi başarısız olur.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('KalinBoru')\nasm.add_pipe('boru', points=[(0,0,0), (60,0,0)], outer_dia=10.0, wall_thickness=6.0)\n",
        },

        # 11. Negative thickness / inverted flange dimensions
        {
            "instruction": "Create a mounting flange with negative thickness (-10 mm).",
            "error_type": "CADISpecificationError",
            "parameter": "thickness",
            "message": "Flange thickness must be positive. Received -10.0.",
            "suggested_fix": "Specify a positive thickness (e.g. thickness=10.0).",
            "category": "specification_error_handling",
            "standards": ["ISO 7005-1"],
            "reasoning": "Negative solid extrusions invert face normals and produce degenerate non-manifold solids.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('NegativeFlange')\nasm.add_flange('flange', outer_diameter=120.0, thickness=-10.0, inner_bore=30.0, bolt_pcd=80.0, bolt_count=4, bolt_diameter=9.0)\n",
        },
        {
            "instruction": "İç deliği (100 mm) dış çapından (80 mm) daha büyük olan ters flanş üret.",
            "error_type": "CADISpecificationError",
            "parameter": "inner_bore",
            "message": "İç delik çapı (100.0 mm) flanş dış çapından (80.0 mm) büyük veya eşit olamaz.",
            "suggested_fix": "İç delik çapını dış çaptan küçük belirleyin (örn: inner_bore=30.0, outer_diameter=80.0).",
            "category": "specification_error_handling",
            "standards": ["ISO 7005-1"],
            "reasoning": "İç deliğin dış çaptan büyük olması katı gövdenin tamamen yok olmasına yol açar.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('TersFlans')\nasm.add_flange('f', outer_diameter=80.0, thickness=15.0, inner_bore=100.0, bolt_pcd=90.0, bolt_count=4, bolt_diameter=8.0)\n",
        },

        # 12. Invalid keyway shaft diameter out of DIN 6885 range
        {
            "instruction": "Cut a standard DIN 6885 drive keyway on a 3mm tiny micro-shaft.",
            "error_type": "CADISpecificationError",
            "parameter": "shaft_diameter",
            "message": "DIN 6885 parallel keyways are defined for shafts >= 6mm. Received diameter: 3.0mm.",
            "suggested_fix": "For shafts under 6mm, use set screws, D-cut shafts, or pins instead of parallel keyways.",
            "category": "specification_error_handling",
            "standards": ["DIN 6885-1"],
            "reasoning": "DIN 6885 standard does not specify parallel drive keyway profiles below 6mm diameter.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('TinyShaft')\ns = asm.add_cylinder('shaft', radius=1.5, height=30.0)\ns.add_keyway('key', standard='DIN_6885_A', shaft_dia=3.0, length=10.0)\n",
        },
        {
            "instruction": "Çapı 4 mm olan mile DIN 6885 standardında kama yuvası aç.",
            "error_type": "CADISpecificationError",
            "parameter": "shaft_diameter",
            "message": "Mil çapı (4.0 mm) DIN 6885 standart aralığının (minimum 6 mm) altındadır.",
            "suggested_fix": "4 mm mil için kamalı bağlantı yerine pim veya D-kesit bağlantısı tercih edin.",
            "category": "specification_error_handling",
            "standards": ["DIN 6885-1"],
            "reasoning": "Mikro millerde kama açılması mil kesitini zayıflatır ve standartta yer almaz.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('MikroMil')\ns = asm.add_cylinder('mil', radius=2.0, height=25.0)\ns.add_keyway('kama', standard='DIN_6885_A', shaft_dia=4.0, length=10.0)\n",
        },

        # 13. Negative bend radius on sheet metal
        {
            "instruction": "Form a sheet metal L-bracket with a negative bend radius of -3 mm.",
            "error_type": "CADISpecificationError",
            "parameter": "inner_radius",
            "message": "Sheet metal inner bend radius must be strictly positive. Received -3.0 mm.",
            "suggested_fix": "Specify a positive inner radius compliant with DIN 6935 (e.g. inner_radius=2.5 mm).",
            "category": "specification_error_handling",
            "standards": ["DIN 6935"],
            "reasoning": "Negative bend radius causes self-intersecting unrolling and crashes sheet metal B-Rep sweep.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('NegativeBend')\nasm.add_sheet_metal_bracket('bracket', bracket_type='L', width=50.0, length1=60.0, length2=40.0, thickness=2.0, inner_radius=-3.0)\n",
        },
        {
            "instruction": "Büküm iç yarıçapı -5 mm olan sac parça üret.",
            "error_type": "CADISpecificationError",
            "parameter": "inner_radius",
            "message": "Sac bükme iç yarıçapı negatif olamaz (-5.0 mm).",
            "suggested_fix": "DIN 6935 standardına uygun pozitif bir büküm yarıçapı (örn: 3.0 mm) girin.",
            "category": "specification_error_handling",
            "standards": ["DIN 6935"],
            "reasoning": "Negatif radyus büküm bölgesinde ters geometri oluşturur ve fiziksel olarak üretilemez.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('NegatifBukme')\nasm.add_sheet_metal_bracket('sac', bracket_type='L', width=40.0, length1=50.0, length2=30.0, thickness=1.5, inner_radius=-5.0)\n",
        },

        # 14. Spur gear with non-positive module or teeth
        {
            "instruction": "Generate an involute spur gear with module 0 and 24 teeth.",
            "error_type": "CADISpecificationError",
            "parameter": "module",
            "message": "Gear module must be strictly positive. Received module=0.",
            "suggested_fix": "Specify a positive gear module according to DIN 780 (e.g. module=1.5 or 2.0).",
            "category": "specification_error_handling",
            "standards": ["DIN 780", "ISO 53"],
            "reasoning": "Module defines gear tooth pitch (p = pi * m); zero module produces non-existent gear teeth.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('ZeroModule')\nasm.add_spur_gear('gear', module=0.0, teeth=24, face_width=15.0)\n",
        },
        {
            "instruction": "Diş sayısı 0 olan düz dişli oluştur.",
            "error_type": "CADISpecificationError",
            "parameter": "teeth",
            "message": "Diş sayısı (teeth) en az 6 olmalıdır. Verilen: 0.",
            "suggested_fix": "Geçerli bir diş sayısı girin (örn: teeth=20).",
            "category": "specification_error_handling",
            "standards": ["DIN 3960"],
            "reasoning": "Diş sayısı sıfır olan dişli geometrisi anlamsızdır ve involüt profil türetilemez.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('SifirDis')\nasm.add_spur_gear('disli', module=2.0, teeth=0, face_width=20.0)\n",
        },

        # 15. Rigid flange coupling with impossible bolt diameter
        {
            "instruction": "Design a DIN 115 coupling where bolt diameter (30 mm) is larger than flange width.",
            "error_type": "CADISpecificationError",
            "parameter": "bolt_diameter",
            "message": "Bolt diameter (30.0 mm) is excessively large for flange envelope (OD: 80.0 mm, PCD: 60.0 mm).",
            "suggested_fix": "Choose a standard bolt diameter according to DIN 115 (e.g. bolt_diameter=8.0 mm).",
            "category": "specification_error_handling",
            "standards": ["DIN 115"],
            "reasoning": "Oversized bolt holes consume the entire flange wall and cause topological cut failure.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('OversizedBolts')\nasm.add_rigid_coupling('c', shaft_diameter=20.0, outer_diameter=80.0, length=50.0, bolt_diameter=30.0, bolt_pcd=60.0)\n",
        },
        {
            "instruction": "Mil çapı (50 mm) dış çapından (40 mm) büyük olan kaplin oluştur.",
            "error_type": "CADISpecificationError",
            "parameter": "shaft_diameter",
            "message": "Mil çapı (50.0 mm) kaplin dış çapından (40.0 mm) büyük veya eşit olamaz.",
            "suggested_fix": "Dış çapı mil çapının en az iki katı seçin (örn: shaft_diameter=20.0, outer_diameter=80.0).",
            "category": "specification_error_handling",
            "standards": ["DIN 115"],
            "reasoning": "Mil deliği dış çaptan büyük olduğunda kaplin gövdesi oluşamaz.",
            "code": "from cadi_saml import Assembly\nasm = Assembly('TersKaplin')\nasm.add_rigid_coupling('c', shaft_diameter=50.0, outer_diameter=40.0, length=60.0)\n",
        },
    ]

    for case in negative_cases:
        err_json = json.dumps({
            "status": "error",
            "error_type": case["error_type"],
            "parameter": case["parameter"],
            "message": case["message"],
            "suggested_fix": case["suggested_fix"],
        }, indent=2, ensure_ascii=False)

        prompt = case["instruction"]
        code = case.get("code", "")
        checksum = compute_sample_checksum(prompt, err_json)

        samples.append({
            "id": f"saml_neg_{sample_id:06d}",
            "instruction": prompt,
            "input": code,
            "output": err_json,
            "output_type": "error_diagnosis",
            "metadata": {
                "category": case["category"],
                "spec_completeness": 0.0,
                "contract_verified": False,
                "provenance_tracked": False,
                "source_standards": case["standards"],
                "execution_status": "expected_error",
                "reasoning_summary": case["reasoning"],
                "input_parameters": {},
                "catalog_parameters": {},
                "derived_parameters": {},
                "executable_code": code,
                "expected_error": {
                    "error_type": case["error_type"],
                    "parameter": case["parameter"],
                    "message": case["message"],
                    "suggested_fix": case["suggested_fix"],
                },
                "generator_meta": {
                    "generator_version": "0.6.0",
                    "library_version": lib_version,
                    "catalog_version": "2026.1",
                    "seed": seed,
                    "checksum": checksum,
                }
            }
        })
        sample_id += 1

    return samples


def main():
    samples = generate_negative_samples()
    print(f"Generated {len(samples)} high-value negative / error-handling samples.")

    out_file = Path(__file__).parent.parent / "dataset" / "saml_negative_dataset.jsonl"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"Negative dataset successfully written to: {out_file} (Total: {len(samples)} samples)")


if __name__ == "__main__":
    main()
