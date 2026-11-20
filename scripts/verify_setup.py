import os
import sys

# Ensure root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from config import settings

EXPECTED_PDFS = [
    ("Free Primer", "Biruktawit_Fitness_Foundation_Guide.pdf"),
    ("BF-F-BC-3X", "BF_8W_F_Booty_3x.pdf"),
    ("BF-F-BC-4X", "BF_8W_F_Booty_4x.pdf"),
    ("BF-F-FL-3X", "BF_8W_F_FatLoss_3x.pdf"),
    ("BF-F-FL-4X", "BF_8W_F_FatLoss_4x.pdf"),
    ("BF-F-MS-3X", "BF_8W_F_Muscle_3x.pdf"),
    ("BF-F-MS-4X", "BF_8W_F_Muscle_4x.pdf"),
    ("BF-M-MG-3X", "BF_8W_M_Hypertrophy_3x.pdf"),
    ("BF-M-MG-4X", "BF_8W_M_Hypertrophy_4x.pdf"),
    ("BF-M-FL-3X", "BF_8W_M_FatLoss_3x.pdf"),
    ("BF-M-FL-4X", "BF_8W_M_FatLoss_4x.pdf"),
    ("BF-M-ST-3X", "BF_8W_M_Strength_3x.pdf"),
    ("BF-M-ST-4X", "BF_8W_M_Strength_4x.pdf")
]

def main():
    print("=" * 60)
    print("  BIRUKTAWIT BOT // PRE-FLIGHT VERIFICATION REPORT")
    print("=" * 60)

    # 1. Check Config & Env
    print("\n1. CONFIGURATION & CREDENTIALS")
    has_token = bool(settings.BOT_TOKEN and not settings.BOT_TOKEN.startswith("1234567890"))
    print(f"  [{'OK' if has_token else 'WARN'}] Telegram Bot Token: {'Configured' if has_token else 'Default Placeholder'}")
    print(f"  [OK] Creator Brand: {settings.CREATOR_NAME} ({settings.CREATOR_HANDLE})")
    print(f"  [OK] Default Program Price: {settings.DEFAULT_PRICE_ETB} ETB")
    print(f"  [OK] Bank CBE: {settings.CBE_ACCOUNT} ({settings.CBE_ACCOUNT_HOLDER})")
    print(f"  [OK] Bank BOA: {settings.BOA_ACCOUNT} ({settings.BOA_ACCOUNT_HOLDER})")
    print(f"  [OK] Telebirr: {settings.TELEBIRR_ACCOUNT} ({settings.TELEBIRR_ACCOUNT_HOLDER})")

    # 2. Check Welcome Image Banner
    print("\n2. WELCOME MEDIA ASSET")
    welcome_img = os.path.join(settings.resolved_image_dir, "welcome_biruktawit.jpg")
    img_exists = os.path.exists(welcome_img)
    print(f"  [{'OK' if img_exists else 'MISSING'}] Welcome Image: {welcome_img}")

    # 3. Check PDF Deliverables in static/pdfs/
    print("\n3. OFFICIAL PDF DELIVERABLES (static/pdfs/)")
    pdf_dir = settings.resolved_pdf_dir
    os.makedirs(pdf_dir, exist_ok=True)

    present_count = 0
    for label, filename in EXPECTED_PDFS:
        target_path = os.path.join(pdf_dir, filename)
        exists = os.path.exists(target_path)
        if exists:
            present_count += 1
            print(f"  [OK] {label}: {filename} (Ready)")
        else:
            print(f"  [WAITING] {label}: {filename} (Drop your PDF here)")

    print(f"\nPDF Summary: {present_count}/{len(EXPECTED_PDFS)} files present in static/pdfs/")
    print("=" * 60)

if __name__ == "__main__":
    main()

