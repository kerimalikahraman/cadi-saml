"""
demo_showcase.py
================
Grand demonstration of CADi SAML's new capabilities:
1. 3D Mechanical Assembly (Gear Reducer & Flanged Mounting Chassis)
2. 2D ISO Engineering Technical Drawing (SVG with HLR hidden lines and Antet)
3. 3D FEA Structural Analysis (Von-Mises Stress, Deflection, Safety Factor, VTK & WebGL HTML viewer)
4. Kinematic Motion Simulation (Revolute joints, Gear mates, live interactive spinning WebGL viewer)
"""

import os
import sys
from cadi_saml import Assembly, OCCTBackend

def run_demo():
    output_dir = os.path.abspath("demo_outputs")
    os.makedirs(output_dir, exist_ok=True)
    print("\n=======================================================")
    print("  CADi SAML v0.3.0 - ENDUSTRIYEL CAD+CAE GOSTERIMI")
    print("=======================================================\n")

    # -------------------------------------------------------------------------
    # 1. 3D CAD Modelleme (İki Aşamalı Dişli Redüktörü & Şasi)
    # -------------------------------------------------------------------------
    print("[1/5] 3D CAD Modeli Olusturuluyor...")
    with Assembly("Precision_Gear_Reducer", units="mm", material="Alu6061-T6") as asm:
        # Şasi / Montaj Tabanı (140x80x10 mm Alüminyum blok, merkez: 60, 40, 5)
        chassis = asm.add_box("chassis", length=140.0, width=80.0, height=10.0, origin=(60.0, 40.0, 5.0))
        
        # Giriş Pinyon Dişlisi (Modül=2.5, Diş Sayısı=16, Bölüm Dairesi = 40 mm)
        pinion = asm.add_spur_gear(
            "pinion",
            module=2.5,
            teeth=16,
            face_width=14.0,
            bore_dia=12.0,
            origin=(30.0, 40.0, 10.0),
        )

        # Çıkış Çark Dişlisi (Modül=2.5, Diş Sayısı=32, Bölüm Dairesi = 80 mm)
        # Eksenler arası mesafe = (40 + 80) / 2 = 60 mm -> X = 30 + 60 = 90 mm
        wheel = asm.add_spur_gear(
            "wheel",
            module=2.5,
            teeth=32,
            face_width=14.0,
            bore_dia=15.0,
            origin=(90.0, 40.0, 10.0),
        )

        # Miller (Pinyon ve Çark göbeklerinin içine tam oturan şaftlar)
        asm.add_cylinder("input_shaft", radius=6.0, height=35.0, origin=(30.0, 40.0, 5.0))
        asm.add_cylinder("output_shaft", radius=7.5, height=35.0, origin=(90.0, 40.0, 5.0))

        # ---------------------------------------------------------------------
        # 2. Kinematik Mekanizma ve Dişli İlişkisi (Kinematics)
        # ---------------------------------------------------------------------
        print("[2/5] Kinematik Eklemler ve Disli Eslesmesi Kuruluyor...")
        asm.add_revolute_joint("pinion", origin=(30.0, 40.0, 10.0), axis=(0.0, 0.0, 1.0))
        asm.add_revolute_joint("wheel", origin=(90.0, 40.0, 10.0), axis=(0.0, 0.0, 1.0), initial_angle=5.625)
        asm.add_revolute_joint("input_shaft", origin=(30.0, 40.0, 5.0), axis=(0.0, 0.0, 1.0))
        asm.add_revolute_joint("output_shaft", origin=(90.0, 40.0, 5.0), axis=(0.0, 0.0, 1.0), initial_angle=5.625)
        
        # Dişli ve Mil ilişkileri
        asm.add_gear_relation("pinion", "wheel")  # 16/32 = 0.5 ters yön
        asm.add_gear_relation("pinion", "input_shaft", ratio=1.0, reverse=False)
        asm.add_gear_relation("wheel", "output_shaft", ratio=1.0, reverse=False)

        # Python tarafında hareket analizi
        kin_states = asm.solve_motion("pinion", value=90.0)
        print(f"   * Pinyon Acisi: {kin_states['pinion'].angle_deg:.1f} deg")
        print(f"   * Cark Acisi:   {kin_states['wheel'].angle_deg:.1f} deg (Ters yonde 1:2 oraninda dondu!)")

        # ---------------------------------------------------------------------
        # 3. 2D İmalat Teknik Resmi Üretimi (Drafting / HLR)
        # ---------------------------------------------------------------------
        drawing_path = os.path.join(output_dir, "reducer_drawing_A4.svg")
        print("\n[3/5] 2D Imalat Teknik Resmi Ciziliyor (HLR Gizli Cizgi Ayiklama)...")
        asm.export_drawing(
            filepath=drawing_path,
            sheet_size="A4",
            title="PRECISION 1:2 SPEED REDUCER",
            material="Alu6061-T6",
        )
        print(f"   [OK] Teknik Resim Kaydedildi: {drawing_path}")

        # ---------------------------------------------------------------------
        # 4. İnteraktif Canlı 3D WebGL Hareket Simülatörü
        # ---------------------------------------------------------------------
        motion_path = os.path.join(output_dir, "reducer_motion_simulation.html")
        print("\n[4/5] Interaktif Canli 3D WebGL Hareket Simulasyonu Uretiliyor...")
        asm.export_motion_html(
            filepath=motion_path,
            title="PRECISION GEAR REDUCER - KINEMATICS",
            driver_part="pinion",
        )
        print(f"   [OK] Hareket Simulasyonu Kaydedildi: {motion_path}")

        # ---------------------------------------------------------------------
        # 5. FEA Yapısal Mukavemet Analizi (CAE)
        # ---------------------------------------------------------------------
        print("\n[5/5] Sasi Uzerinde 3D Sonlu Elemanlar (FEA) Mukavemet Analizi Cozuluyor...")
        fea = asm.add_fea_study("chassis", material="Alu6061-T6", mesh_size=5.0)
        fea.fix_face("z_min")
        fea.apply_force("z_max", force_vector=(0.0, -800.0, -1200.0))
        
        fea_result = fea.solve()
        print(fea_result.summary_report)

        # FEA Sonuçlarını Dışa Aktar
        vtk_path = os.path.join(output_dir, "chassis_fea_results.vtk")
        fea_html_path = os.path.join(output_dir, "chassis_fea_stress_viewer.html")

        fea_result.export_vtk(vtk_path)
        fea_result.export_html(fea_html_path, deformation_scale=25.0)

        print(f"   [OK] ParaView VTK Kaydedildi:     {vtk_path}")
        print(f"   [OK] 3D WebGL Gerilme Raporu:     {fea_html_path}")

    print("\n=======================================================")
    print("  TUM CIKTILAR BASARIYLA URETILDI!")
    print(f"Klasor: {output_dir}")
    print(f"1. {os.path.basename(drawing_path)}      (2D Teknik Resim - Vektorel SVG)")
    print(f"2. {os.path.basename(motion_path)}   (Canli Donen 3D Disli Simulatoru - HTML)")
    print(f"3. {os.path.basename(fea_html_path)} (3D WebGL Gerilme Renk Haritasi - HTML)")
    print(f"4. {os.path.basename(vtk_path)}       (ParaView / Blender 3D Mesh)")
    print("=======================================================\n")

if __name__ == "__main__":
    run_demo()
