import re
from typing import Optional, Dict, Any

VALID_RECEIVER_TOKENS = ["BIRUKTAWIT", "FIKRE", "BRUKTAWIT", "BERUKTAWIT"]

def is_valid_biruktawit_receiver(ocr_text: str, bank_api_data: Optional[Dict[str, Any]] = None) -> bool:
    """
    Validates that the recipient is Biruktawit Fikre.
    """
    # 1. API check
    if bank_api_data:
        receiver = str(
            bank_api_data.get("receiver_name")
            or bank_api_data.get("creditedPartyName")
            or ""
        ).upper()
        if any(token in receiver for token in VALID_RECEIVER_TOKENS):
            return True

    # 2. Text analysis
    clean_ocr = (ocr_text or "").upper()
    return any(token in clean_ocr for token in VALID_RECEIVER_TOKENS)

def extract_transaction_reference(ocr_text: str) -> Optional[str]:
    """
    Extracts transaction reference from screenshot text.
    Handles CBE (FT...), Telebirr, and Bank of Abyssinia codes.
    """
    if not ocr_text:
        return None
        
    patterns = [
        r'\bFT[A-Z0-9]{8,12}\b',   # CBE
        r'\bTXN[0-9]{8,12}\b',      # Telebirr
        r'\b[A-Z0-9]{10,14}\b'      # General Bank of Abyssinia / FT
    ]
    for pattern in patterns:
        match = re.search(pattern, ocr_text.upper())
        if match:
            return match.group(0)
    return None

