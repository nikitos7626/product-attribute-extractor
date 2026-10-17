from app.extractors.normalization.loaders import load_pairs, load_colors

BRANDS: dict[str, str] = load_pairs("brands.csv")
COLORS: dict[str, tuple[str, int]] = load_colors("colors.csv")


# Атрибуты, где допустимо несколько значений —
# они склеиваются через запятую в одно поле.
MULTI_VALUE_ATTRS: set[str] = {"connectivity", "features", "audio_codec"}


# Категориальные словари: имя атрибута → {alias: canonical}
CATEGORICAL: dict[str, dict[str, str]] = {
    "material":         load_pairs("materials.csv"),
    "country_of_origin": load_pairs("countries.csv"),
    "storage_type":     load_pairs("storage_types.csv"),
    "screen_tech":      load_pairs("screen_tech.csv"),
    "resolution_class": load_pairs("resolution_classes.csv"),
    "connectivity":     load_pairs("connectivity.csv"),
    "features":         load_pairs("features.csv"),
    "audio_codec":      load_pairs("audio_codecs.csv"),
    "gender":           load_pairs("genders.csv"),
    "form_factor":      load_pairs("form_factors.csv"),
}


UNITS: dict[str, list[str]] = {
    "memory":  ["гб", "gb", "тб", "tb", "гигабайт", "терабайт"],
    "screen":  ["дюйм", "дюйма", "дюймов", '"', "inch", "in", "”", "″"],
    "battery": ["мач", "mah", "а·ч", "ач"],
    "refresh": ["гц", "hz"],
}