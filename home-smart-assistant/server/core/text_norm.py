"""Chuan hoa van ban tieng Viet de khop tu khoa/thiet bi du go co dau hay khong.

Ke thua y tuong tu app/tools._norm (du an cu): bo dau, ve chu thuong, doi gach noi thanh
khoang trang, gop khoang trang. Them lop dong nghia (may lanh -> dieu hoa) cho thiet bi.
"""
import re
import unicodedata

# Ten goi khac -> ten chuan (da chuan hoa, khong dau). Dat cum dai/cu the truoc.
_SYNONYMS = (
    ("dieu hoa nhiet do", "dieu hoa"),
    ("dieu hoa khong khi", "dieu hoa"),
    ("may dieu hoa", "dieu hoa"),
    ("may lanh", "dieu hoa"),
    ("bong den", "den"),
    ("den dien", "den"),
    ("den chieu sang", "den"),
    ("quat dien", "quat"),
    ("quat may", "quat"),
    ("quat gio", "quat"),
    ("ti vi", "tivi"),
    ("vo tuyen", "tivi"),
)


def norm(s):
    """Bo dau, chu thuong, gach noi -> khoang trang, gop khoang trang."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d")
    s = re.sub(r"[_\-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_device(s):
    """Chuan hoa + doi ten goi khac ve ten chuan."""
    t = norm(s)
    for a, b in _SYNONYMS:
        t = t.replace(a, b)
    return t


def tokens(s):
    """Tap cac tu (da chuan hoa thiet bi) trong chuoi."""
    return set(re.findall(r"[a-z0-9]+", norm_device(s)))
