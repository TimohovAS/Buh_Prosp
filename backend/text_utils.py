"""Текстовые утилиты: транслитерация сербской кириллицы в латиницу.

Используется там, где вывод должен быть латиницей: PDF-отчёты (KPO) и
поле имени получателя в NBS IPS QR (эталонные QR Пореской управы —
латиница; кириллица в payload ломает разбор в банковских приложениях).
Тот же словарь даёт поиску нечувствительность к алфавиту.
"""

import unicodedata

CYRILLIC_TO_LATIN = {
    "А": "A",
    "а": "a",
    "Б": "B",
    "б": "b",
    "В": "V",
    "в": "v",
    "Г": "G",
    "г": "g",
    "Д": "D",
    "д": "d",
    "Ђ": "Dj",
    "ђ": "dj",
    "Е": "E",
    "е": "e",
    "Ж": "Z",
    "ж": "z",
    "З": "Z",
    "з": "z",
    "И": "I",
    "и": "i",
    "Ј": "J",
    "ј": "j",
    "К": "K",
    "к": "k",
    "Л": "L",
    "л": "l",
    "Љ": "Lj",
    "љ": "lj",
    "М": "M",
    "м": "m",
    "Н": "N",
    "н": "n",
    "Њ": "Nj",
    "њ": "nj",
    "О": "O",
    "о": "o",
    "П": "P",
    "п": "p",
    "Р": "R",
    "р": "r",
    "С": "S",
    "с": "s",
    "Т": "T",
    "т": "t",
    "Ћ": "C",
    "ћ": "c",
    "У": "U",
    "у": "u",
    "Ф": "F",
    "ф": "f",
    "Х": "H",
    "х": "h",
    "Ц": "C",
    "ц": "c",
    "Ч": "C",
    "ч": "c",
    "Џ": "Dz",
    "џ": "dz",
    "Ш": "S",
    "ш": "s",
}


def to_serbian_latin(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(CYRILLIC_TO_LATIN.get(char, char) for char in str(value))


def fold_search_text(value: str | None) -> str:
    """Свести текст к виду, в котором поиск не зависит от алфавита, диакритики и регистра.

    «АИМА» и «aima», «Vršac» и «vrsac» совпадают. đ пишут и как dj, и как d,
    поэтому обе записи сводятся к d. Копия на фронтенде — foldSearchText
    в utils/searchUtils.js: правила должны совпадать.
    """
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    without_marks = "".join(char for char in decomposed if not unicodedata.category(char).startswith("M"))
    return to_serbian_latin(without_marks.lower()).replace("đ", "d").replace("dj", "d")


def matches_search(query: str | None, *values: str | None) -> bool:
    """Каждое слово запроса должно найтись хотя бы в одном из полей."""
    haystack = " ".join(fold_search_text(value) for value in values if value)
    return all(token in haystack for token in fold_search_text(query).split())
