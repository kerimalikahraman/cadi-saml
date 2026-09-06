"""
demo_planar_mechanism.py
========================
High-precision demonstration of a Planar Linkage Mechanism:
Industrial Crank-Slider (Krank-Biyel Piston Mekanizmasi)
1. 3D Mechanical Assembly (Monolithic Engine Block Bedplate, Crankshaft with Counterweight, Connecting Rod, Piston)
2. Exact Planar Kinematics (Revolute & Prismatic joints, non-linear coupled trigonometric solver)
3. 2D ISO Engineering Drafting (SVG with HLR hidden lines)
4. Interactive 3D WebGL Motion Simulation with Three.js
"""

import os
import math
from cadi_saml import Assembly, OCCTBackend

def run_planar_demo():
    output_dir = os.path.abspath("demo_outputs")
    os.makedirs(output_dir, exist_ok=True)

    print("\n=======================================================")
    print("  CADi SAML - PLANAR MEKANIZMA GOSTERIMI")
    print("  (Endustriyel Krank-Biyel Piston Mekanizmasi)")
    print("=======================================================\n")

    R_crank = 30.0   # Krank yaricapi (Strok = 60 mm)
    L_conrod = 90.0  # Biyel kolu uzunlugu (L/R orani = 3.0)

    with Assembly("Planar_Crank_Slider_Mechanism", units="mm", material="Steel4140") as asm:
        print("[1/4] 3D Parcalar Modelleniyor...")

        # 1. Taban Govde / Motor Blogu (Sabit Referans Sasi - Monolitik Dokum Govde)
        # Krank yatak mesnedi, silindir kovanı (36mm bore) ve ustu acik gozlem pencereli motor blogu
        frame = asm.add_engine_frame(
            "engine_frame",
            base_length=250.0,
            base_width=90.0,
            base_thickness=12.0,
            bearing_center_z=32.0,
            cylinder_bore_dia=36.0,
            origin=(0.0, 0.0, 0.0),
            color=(0.22, 0.28, 0.36),  # Slate Döküm Gri
            material="CastIron",
        )

        # 2. Krank Mili (Crankshaft - Monolitik Krank Diski, Karsi Agirlik ve Ofset Krank Pimi)
        crank = asm.add_crankshaft(
            "crankshaft",
            crank_radius=R_crank,
            disc_radius=44.0,
            disc_thickness=10.0,
            pin_diameter=14.0,
            pin_length=16.0,
            shaft_diameter=16.0,
            shaft_length=24.0,
            origin=(0.0, 0.0, 17.0),
            color=(0.12, 0.53, 0.85),  # Islem Gormus Celik Mavi
            material="Steel4140",
        )

        # 3. Biyel Kolu (Connecting Rod - Krank Basi, I-profil Govde, Kucuk Bas ve Yatak Delikleri)
        conrod = asm.add_connecting_rod(
            "connecting_rod",
            length=L_conrod,
            big_bore_dia=14.0,
            big_head_dia=28.0,
            small_bore_dia=10.0,
            small_head_dia=20.0,
            thickness=10.0,
            shank_width=12.0,
            origin=(R_crank, 0.0, 27.0),
            color=(0.85, 0.47, 0.02),  # Dovme Bronz / Celik Altin
            material="ForgedSteel",
        )

        # 4. Silindir Piston (Slider Piston - Yatay Piston Govdesi, Segman Kanallari ve Bilek Pimi)
        piston = asm.add_slider_piston(
            "slider_piston",
            diameter=34.0,
            length=42.0,
            pin_diameter=10.0,
            origin=(R_crank + L_conrod, 0.0, 32.0),
            color=(0.80, 0.84, 0.88),  # Eloksalli Alumi̇nyum Gumus
            material="AlloyPiston",
        )

        # ---------------------------------------------------------------------
        # Kinematik Eklemler ve Duzlemsel Krank-Biyel Baglantisi
        # ---------------------------------------------------------------------
        print("\n[2/4] Kinematik Eklemler ve Krank-Biyel Iliskisi Tanimlaniyor...")

        # Krank donel eklemi (Z ekseninde 0,0,17 merkezli)
        asm.add_revolute_joint("crankshaft", origin=(0.0, 0.0, 17.0), axis=(0.0, 0.0, 1.0))

        # Biyel kolu salinim eklemi (Krank piminde baslar: 30, 0, 27)
        asm.add_revolute_joint("connecting_rod", origin=(R_crank, 0.0, 27.0), axis=(0.0, 0.0, 1.0))

        # Piston lineer kayma eklemi (X ekseni boyunca: 120, 0, 32)
        asm.add_prismatic_joint("slider_piston", origin=(R_crank + L_conrod, 0.0, 32.0), axis=(1.0, 0.0, 0.0))

        # Ana Duzlemsel Mekanizma Iliskisi (Planar Slider-Crank Coupler)
        asm.add_slider_crank_relation(
            crank_part="crankshaft",
            conrod_part="connecting_rod",
            piston_part="slider_piston",
            crank_radius=R_crank,
            conrod_length=L_conrod,
            crank_center=(0.0, 0.0, 17.0),
            slide_axis=(1.0, 0.0, 0.0),
            offset=0.0,
        )

        # Test Kinematik Cozumu: 90 derece krank acisi icin
        states = asm.solve_motion("crankshaft", value=90.0)
        piston_disp = states["slider_piston"].translation_mm
        conrod_ang = states["connecting_rod"].angle_deg
        print(f"   * Krank Acisi: 90.0 deg")
        print(f"   * Piston Konumu (X): {piston_disp:.2f} mm (Strok ortasi)")
        print(f"   * Biyel Acisi:       {conrod_ang:.2f} deg (Maksimum egim acisi)")

        # ---------------------------------------------------------------------
        # 3. 2D ISO Muhendislik Cizimi
        # ---------------------------------------------------------------------
        drawing_path = os.path.join(output_dir, "planar_crank_slider_drawing_A4.svg")
        print("\n[3/4] 2D Teknik Resim Uretiliyor (HLR Gizli Cizgi Ayiklama)...")
        asm.export_drawing(
            filepath=drawing_path,
            sheet_size="A4",
            title="PLANAR CRANK-SLIDER PISTON MECHANISM",
            material="Steel4140",
        )
        print(f"   [OK] Teknik Resim Kaydedildi: {drawing_path}")

        # ---------------------------------------------------------------------
        # 4. 3D WebGL Canli Hareket Simulasyonu
        # ---------------------------------------------------------------------
        motion_path = os.path.join(output_dir, "planar_mechanism_simulation.html")
        print("\n[4/4] Interaktif Canli 3D WebGL Hareket Simulasyonu Uretiliyor...")
        asm.export_motion_html(
            filepath=motion_path,
            title="PLANAR CRANK-SLIDER MECHANISM",
            driver_part="crankshaft",
        )
        print(f"   [OK] Hareket Simulasyonu Kaydedildi: {motion_path}")

    print("\n=======================================================")
    print("  DUZLEMSEl MEKANIZMA BASARIYLA URETILDI!")
    print(f"Klasor: {output_dir}")
    print(f"1. {os.path.basename(drawing_path)} (2D ISO Teknik Resim)")
    print(f"2. {os.path.basename(motion_path)} (Canli 3D Krank-Biyel-Piston Simulatoru)")
    print("=======================================================\n")

if __name__ == "__main__":
    run_planar_demo()
