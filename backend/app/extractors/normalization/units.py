# app/extractors/normalization/units.py
import re


class UnitNormalizer:
    """Приводит единицы измерения к каноническому виду."""

    # ---------- уже было ----------

    @staticmethod
    def memory(value: str, unit: str) -> str:
        """1024 ГБ → 1 ТБ ; 256gb → 256 ГБ."""
        num = float(value.replace(",", "."))
        u = unit.upper().replace("B", "Б").replace("T", "Т")
        if u in ("ТБ", "TB", "ТБАЙТ"):
            gb = num * 1024
        else:
            gb = num
        if gb >= 1024 and gb % 1024 == 0:
            return f"{int(gb / 1024)} ТБ"
        return f"{int(gb)} ГБ" if gb.is_integer() else f"{gb} ГБ"

    @staticmethod
    def screen_diagonal(value: str) -> str:
        num = float(value.replace(",", "."))
        return f'{str(num).replace(".", ",")}"'

    @staticmethod
    def battery(value: str) -> str:
        num = int(float(value.replace(",", ".").replace(" ", "")))
        return f"{num} мАч"

    @staticmethod
    def refresh_rate(value: str) -> str:
        return f"{int(float(value.replace(',', '.')))} Гц"

    @staticmethod
    def resolution(w: str, h: str) -> str:
        return f"{int(w)}×{int(h)}"

    # ---------- новые ----------

    @staticmethod
    def _fmt(num: float, decimals: int = 2) -> str:
        """2.5 → '2,5' ; 3.0 → '3'."""
        if float(num).is_integer():
            return str(int(num))
        return str(round(num, decimals)).replace(".", ",")

    @staticmethod
    def weight(value: str, unit: str) -> str:
        """250 g → 250 г ; 1.5 kg → 1,5 кг ; 1500 г → 1,5 кг."""
        num = float(value.replace(",", "."))
        u = unit.lower()
        if u.startswith("к") or u in ("kg", "килограмм", "килограмма", "килограммов"):
            grams = num * 1000
        else:
            grams = num
        if grams >= 1000:
            kg = grams / 1000
            return f"{UnitNormalizer._fmt(kg, 3)} кг"
        return f"{UnitNormalizer._fmt(grams, 1)} г"

    @staticmethod
    def power(value: str, unit: str) -> str:
        """1.5 кВт → 1500 Вт ; 500 w → 500 Вт."""
        num = float(value.replace(",", "."))
        u = unit.lower()
        if u in ("квт", "kw"):
            w = num * 1000
        else:
            w = num
        return f"{UnitNormalizer._fmt(w)} Вт"

    @staticmethod
    def volume(value: str, unit: str) -> str:
        """500 мл → 500 мл ; 1.7 л → 1,7 л ; 2000 мл → 2 л."""
        num = float(value.replace(",", "."))
        u = unit.lower()
        if u.startswith("л") or u in ("l", "литр", "литра", "литров"):
            ml = num * 1000
        else:
            ml = num
        if ml >= 1000:
            l = ml / 1000
            return f"{UnitNormalizer._fmt(l, 3)} л"
        return f"{UnitNormalizer._fmt(ml, 1)} мл"

    @staticmethod
    def warranty(value: str, unit: str) -> str:
        """1 год → 12 мес ; 24 months → 24 мес."""
        num = int(value)
        u = unit.lower()
        if u.startswith("год") or u.startswith("лет") or u.startswith("year"):
            months = num * 12
        else:
            months = num
        return f"{months} мес"

    @staticmethod
    def dimensions(w: str, h: str, d: str, unit: str = "см") -> str:
        """Нормализация габаритов: 59.5x199.8x67.2 см."""
        w_c = w.replace(",", ".").strip()
        h_c = h.replace(",", ".").strip()
        d_c = d.replace(",", ".").strip()
        u = unit.strip().lower() or "см"
        return f"{w_c}x{h_c}x{d_c} {u}"