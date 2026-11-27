import os
import sys

# Ensure root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from config import settings
from services.deliverer import resolve_sku_pdf_path

CORE_SKUS = [
    ("BF-F-BC-3X", "BF_8W_F_Booty_3x.pdf"),
    ("BF-F-BC-4X", "BF_8W_F_Booty_4x.pdf"),
    ("BF-F-FL-3X", "BF_8W_F_FatLoss_3x.pdf"),
    ("BF-F-FL-4X", "BF_8W_F_FatLoss_4x.pdf"),
    ("BF-M-MG-3X", "BF_8W_M_Hypertrophy_3x.pdf"),
    ("BF-M-MG-4X", "BF_8W_M_Hypertrophy_4x.pdf"),
    ("BF-M-FL-3X", "BF_8W_M_FatLoss_3x.pdf"),
    ("BF-M-FL-4X", "BF_8W_M_FatLoss_4x.pdf"),
]


def main():
    print("=" * 60)
    print("  BIRUKTAWIT BOT // PRE-FLIGHT VERIFICATION REPORT")
    print("=" * 60)

    print("\n1. CONFIGURATION & CREDENTIALS")
    has_token = bool(settings.BOT_TOKEN and not settings.BOT_TOKEN.startswith("1234567890"))
    print(f"  [{'OK' if has_token else 'WARN'}] Telegram Bot Token: {'Configured' if has_token else 'Default Placeholder'}")
    print(f"  [OK] Creator Brand: {settings.CREATOR_NAME} ({settings.CREATOR_HANDLE})")
    print(f"  [OK] Support Bot: @{settings.SUPPORT_BOT_USERNAME}")
    print(f"  [OK] Default Program Price: {settings.DEFAULT_PRICE_ETB} ETB")
    print(f"  [OK] Bank CBE: {settings.CBE_ACCOUNT} ({settings.CBE_ACCOUNT_HOLDER})")
    print(f"  [OK] Bank BOA: {settings.BOA_ACCOUNT} ({settings.BOA_ACCOUNT_HOLDER})")

    print("\n2. WELCOME MEDIA ASSETS")
    welcome_imgs = [
        "IMG_1591 (1)_opt.jpg",
        "Side-by-Side Fitness Progress Photo_opt.jpg",
        "Before and After_ Street to Gym_opt.jpg",
    ]
    for img_name in welcome_imgs:
        p = os.path.join(settings.resolved_image_dir, img_name)
        print(f"  [{'OK' if os.path.exists(p) else 'MISSING'}] {img_name}")

    print("\n3. OFFICIAL PDF DELIVERABLES (8 Core Plans + 1 Free Guide)")
    pdf_dir = settings.resolved_pdf_dir
    os.makedirs(pdf_dir, exist_ok=True)

    present_count = 0
    free_path = os.path.join(pdf_dir, "Biruktawit_Fitness_Foundation_Guide.pdf")
    if os.path.exists(free_path):
        present_count += 1
        print("  [OK] Free Primer: Biruktawit_Fitness_Foundation_Guide.pdf (Ready)")
    else:
        print("  [WAITING] Free Primer: Biruktawit_Fitness_Foundation_Guide.pdf")

    for sku, canonical in CORE_SKUS:
        found = resolve_sku_pdf_path(sku)
        if found:
            present_count += 1
            print(f"  [OK] {sku}: {os.path.basename(found)} (Ready)")
        else:
            print(f"  [WAITING] {sku}: {canonical} (Not uploaded yet)")

    print(f"\nPDF Summary: {present_count}/{len(CORE_SKUS) + 1} files present in static/pdfs/")
    print("=" * 60)


if __name__ == "__main__":
    main()
