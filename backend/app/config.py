"""Shop-wide constants and design-category defaults.

All weights are integer milligrams (mg), purity is parts-per-thousand (ppt, e.g. 916 = 22K),
wastage is basis points (bp, 150 = 1.5%), money is integer paise. No floats touch the ledger.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("KHATA_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("KHATA_DB", DATA_DIR / "khata.db"))
UPLOAD_DIR = DATA_DIR / "uploads"
SECRET = os.getenv("KHATA_SECRET", "dev-secret-change-me")

SHOP_NAME = os.getenv("SHOP_NAME", "Shree Lakshmi Jewellers")
SHOP_CITY = os.getenv("SHOP_CITY", "Jaipur")
JEWELLER_PIN = os.getenv("JEWELLER_PIN", "1234")

# Digital scale resolution in mg. Disagreements within 2x this are treated as scale noise.
SCALE_RESOLUTION_MG = int(os.getenv("SCALE_RESOLUTION_MG", "10"))

PURITY_BY_KARAT = {"24K": 999, "22K": 916, "20K": 833, "18K": 750, "14K": 585}

# key: (label_en, label_hi, default_wastage_bp, default_making_paise_per_g, typical_days)
CATEGORIES = {
    "plain_bangle": ("Plain bangle", "सादा कंगन", 100, 25000, 5),
    "chain": ("Chain", "चेन", 150, 30000, 7),
    "filigree": ("Filigree work", "फिलिग्री (जाली) काम", 250, 60000, 14),
    "necklace_haar": ("Necklace / Haar", "हार", 180, 45000, 12),
    "ring": ("Ring", "अंगूठी", 120, 35000, 4),
    "jhumka_earring": ("Jhumka / Earring", "झुमका", 200, 50000, 8),
    "mangalsutra": ("Mangalsutra", "मंगलसूत्र", 160, 35000, 7),
    "other": ("Other", "अन्य", 150, 30000, 7),
}

# Words a jeweller might use in a voice/text note, mapped to a category.
CATEGORY_KEYWORDS = {
    "plain_bangle": ["bangle", "kangan", "kada", "chudi", "choodi", "कंगन", "कड़ा", "चूड़ी"],
    "chain": ["chain", "चेन"],
    "filigree": ["filigree", "jaali", "jali", "जाली", "फिलिग्री"],
    "necklace_haar": ["haar", "har ", "necklace", "rani haar", "हार", "नेकलेस"],
    "ring": ["ring", "anguthi", "angoothi", "अंगूठी"],
    "jhumka_earring": ["jhumka", "jhumki", "earring", "tops", "bali", "झुमका", "झुमकी"],
    "mangalsutra": ["mangalsutra", "मंगलसूत्र"],
}


def category_label(key: str, lang: str = "en") -> str:
    c = CATEGORIES.get(key, CATEGORIES["other"])
    return c[1] if lang == "hi" else c[0]


def karat_label(purity_ppt: int) -> str:
    for k, v in PURITY_BY_KARAT.items():
        if v == purity_ppt:
            return k
    return f"{purity_ppt}/1000"
