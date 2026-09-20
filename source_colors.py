#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""source_colors.py — индивидуальные цвета для каждого источника."""

# ANSI 256-цвета. Формат: "38;5;N" (fg), "48;5;N" (bg)
# См. https://www.ditig.com/256-colors-cheat-sheet

SOURCE_COLORS = {
    # ===== РОССИЙСКИЕ =====
    "ria":              ("38;5;196", None),   # яркий красный
    "kp":               ("38;5;160", None),   # алый
    "pravda":           ("38;5;88", None),    # бордовый

    "tass":             ("38;5;214", None),   # янтарный
    "tass_en":          ("38;5;214", None),
    "interfax":         ("38;5;220", None),   # жёлтый
    "interfax_subscribe": ("38;5;220", None),
    "regnum":           ("38;5;208", None),   # оранжевый
    "gazeta":           ("38;5;172", None),   # тёмно-оранжевый

    "kommersant":       ("38;5;93", None),    # фиолетовый
    "rbc":              ("38;5;46", None),    # ярко-зелёный
    "vedomosti":        ("38;5;24", None),    # тёмно-синий
    "expert":           ("38;5;64", None),    # оливковый

    "lenta":            ("38;5;51", None),    # бирюзовый
    "mk":               ("38;5;205", None),   # розовый
    "aif":              ("38;5;118", None),   # лаймовый
    "meduza":           ("38;5;165", None),   # маджента
    "rg":               ("38;5;130", None),   # медный
    "ng":               ("38;5;33", None),    # синий
    "newsru":           ("38;5;136", None),   # золотой
    "habr":             ("38;5;64", None),    # оливковый
    "un_ru":            ("38;5;21", None),    # голубой

    "5tv":              ("38;5;45", None),    # небесно-голубой
    "m24":              ("38;5;87", None),    # циан
    "mosreg":           ("38;5;27", None),    # индиго
    "fontanka":         ("38;5;44", None),
    "fontanka_main":    ("38;5;44", None),
    "dp":               ("38;5;26", None),
    "amic":             ("38;5;39", None),
    "chita":            ("38;5;51", None),
    "e1":               ("38;5;33", None),
    "ngs":              ("38;5;33", None),
    "newsnn":           ("38;5;33", None),
    "amur":             ("38;5;45", None),
    "pravda_severa":    ("38;5;136", None),

    "izvestia":         ("38;5;172", None),
    "rg_military":      ("38;5;130", None),
    "vesti":            ("38;5;160", None),
    "utro":             ("38;5;172", None),
    "hi_news":          ("38;5;118", None),
    "infox":            ("38;5;136", None),
    "russian_rt":       ("38;5;202", None),
    "sputnik_ru":       ("38;5;202", None),
    "vz":               ("38;5;93", None),
    "rosbalt":          ("38;5;136", None),
    "moscowtimes_ru":   ("38;5;136", None),

    "cbr":              ("38;5;46", None),    # зелёный
    "cbr_press":        ("38;5;34", None),    # тёмно-зелёный
    "kremlin":          ("38;5;214", None),   # янтарный
    "kremlin_en":       ("38;5;214", None),
    "russia_insider":   ("38;5;136", None),   # золотой
    "pravdareport":     ("38;5;130", None),   # медный

    # ===== КИТАЙСКИЕ =====
    "china_xinhua":     ("38;5;196", None),   # яркий красный
    "china_daily":      ("38;5;208", None),   # оранжевый
    "cgtn":             ("38;5;160", None),   # алый
    "global_times":     ("38;5;202", None),   # оранжево-красный
    "people_daily":     ("38;5;196", None),   # красный
    "chinanews":        ("38;5;172", None),   # тёмно-оранжевый

    # ===== МИРОВЫЕ =====
    "bbc_world":        ("38;5;9", None),
    "bbc_top":          ("38;5;9", None),
    "bbc_tech":         ("38;5;9", None),
    "reuters":          ("38;5;202", None),
    "reuters_world":    ("38;5;202", None),
    "cnn_top":          ("38;5;196", None),
    "cnn_world":        ("38;5;196", None),
    "dw_all":           ("38;5;33", None),
    "dw_world":         ("38;5;33", None),
    "aljazeera":        ("38;5;130", None),
    "guardian_world":   ("38;5;21", None),
    "guardian_uk":      ("38;5;21", None),
    "nyt_world":        ("38;5;99", None),
    "nyt_home":         ("38;5;99", None),
    "france24":         ("38;5;44", None),
    "euronews":         ("38;5;27", None),
    "spiegel":          ("38;5;45", None),
    "zeit":             ("38;5;63", None),
    "faz":              ("38;5;62", None),
    "lemonde":          ("38;5;130", None),
    "elpais":           ("38;5;172", None),
    "scmp":             ("38;5;160", None),
    "japan_times":      ("38;5;196", None),
    "times_india":      ("38;5;172", None),
    "cbc_top":          ("38;5;34", None),
    "cbc_world":        ("38;5;34", None),
    "npr":              ("38;5;26", None),
    "nbc":              ("38;5;99", None),
    "cbs":              ("38;5;27", None),
    "cbs_world":        ("38;5;27", None),
    "sky_world":        ("38;5;160", None),
    "sky_home":         ("38;5;160", None),
    "independent":      ("38;5;45", None),
    "time":             ("38;5;196", None),
    "economist":        ("38;5;130", None),
    "politico_eu":      ("38;5;33", None),
    "euobserver":       ("38;5;27", None),
    "un_news":          ("38;5;33", None),
    "who":              ("38;5;39", None),
    "nasa":             ("38;5;196", None),
    "theverge":         ("38;5;99", None),
    "techcrunch":       ("38;5;34", None),
    "wired":            ("38;5;202", None),
    "arstechnica":      ("38;5;44", None),
    "cointelegraph":    ("38;5;220", None),
    "cnbc":             ("38;5;33", None),
    "marketwatch":      ("38;5;130", None),
    "investing":        ("38;5;34", None),
    "fortune":          ("38;5;172", None),
    "entrepreneur":     ("38;5;118", None),
    "engadget":         ("38;5;34", None),
    "rt":               ("38;5;160", None),
    "abc_top":          ("38;5;33", None),
    "abc_world":        ("38;5;33", None),
    "abc_au":           ("38;5;45", None),
    "abc_nz":           ("38;5;45", None),
    "age":              ("38;5;27", None),
    "smh":              ("38;5;27", None),
    "channelnewsasia":  ("38;5;44", None),
    "straits_times":    ("38;5;44", None),
    "the_hindu":        ("38;5;172", None),
    "ndtv":             ("38;5;172", None),
    "korea_herald":     ("38;5;44", None),
    "rfi":              ("38;5;45", None),
    "arte":             ("38;5;63", None),
    "ansa":             ("38;5;34", None),
    "nos":              ("38;5;202", None),
    "dn":               ("38;5;45", None),
    "nato":             ("38;5;27", None),
    "voa":              ("38;5;33", None),
    "nhk_world":        ("38;5;160", None),
    "publico":          ("38;5;130", None),
    "rtve":             ("38;5;196", None),
    "pbs":              ("38;5;33", None),
    "spaceflight":      ("38;5;45", None),
    "spacedotcom":      ("38;5;45", None),
}

DEFAULT_RU_COLOR = "38;5;33"
DEFAULT_WORLD_COLOR = "38;5;45"


def get_source_color(source_id, region):
    """Возвращает ANSI-код цвета для источника."""
    entry = SOURCE_COLORS.get(source_id)
    if entry:
        fg, bg = entry
        if bg:
            return "\033[{};{}m".format(fg, bg)
        return "\033[{}m".format(fg)
    if region == "RU":
        return "\033[{}m".format(DEFAULT_RU_COLOR)
    return "\033[{}m".format(DEFAULT_WORLD_COLOR)