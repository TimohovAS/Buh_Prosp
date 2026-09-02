"""Разбор и сборка контактных данных клиента.

До миграции 20260902_0018 телефон, почта и сайт хранились одной свободной
строкой в поле ``contact``. Здесь лежит разбор такой строки и обратная сборка
одной строкой — она нужна выгрузкам, где под контакт отведена одна ячейка.
"""

import re

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*[a-z]{2,}", re.IGNORECASE)
WEBSITE_RE = re.compile(r"(?:https?://|www\.)[^\s,;]+", re.IGNORECASE)
PHONE_MARKER_RE = re.compile(r"\b(?:tel|тел|phone|mob|моб)\b\.?\s*:?", re.IGNORECASE)
PHONE_RE = re.compile(r"\+?\d[\d\s\-/().]{4,}\d")
MIN_PHONE_DIGITS = 6


def _extract(pattern: re.Pattern[str], text: str, predicate=None) -> tuple[list[str], str]:
    """Вырезать из строки все совпадения, вернув их и остаток текста."""
    found: list[str] = []

    def replace(match: re.Match[str]) -> str:
        value = match.group(0).strip()
        if predicate is not None and not predicate(value):
            return match.group(0)
        found.append(value)
        return " "

    return found, pattern.sub(replace, text)


def _is_phone(value: str) -> bool:
    return sum(char.isdigit() for char in value) >= MIN_PHONE_DIGITS


def _clean_person(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" ,;:-–—.")
    return value if any(char.isalpha() for char in value) else ""


def split_contact_line(raw: str | None) -> dict[str, str]:
    """Разложить свободную строку контакта на лицо, телефон, почту и сайт."""
    persons: list[str] = []
    phones: list[str] = []
    emails: list[str] = []
    websites: list[str] = []

    for part in re.split(r"[;\n]+", raw or ""):
        if not part.strip():
            continue
        found_emails, rest = _extract(EMAIL_RE, part)
        emails.extend(found_emails)
        found_websites, rest = _extract(WEBSITE_RE, rest)
        websites.extend(found_websites)
        rest = PHONE_MARKER_RE.sub(" ", rest)
        found_phones, rest = _extract(PHONE_RE, rest, _is_phone)
        phones.extend(phone.strip() for phone in found_phones)
        person = _clean_person(rest)
        if person:
            persons.append(person)

    return {
        "contact": "; ".join(persons),
        "phone": ", ".join(phones),
        "email": ", ".join(emails),
        "website": ", ".join(websites),
    }


def format_contact_line(client) -> str:
    """Собрать контакт клиента одной строкой для выгрузок."""
    phone = (getattr(client, "phone", "") or "").strip()
    parts = [
        (getattr(client, "contact", "") or "").strip(),
        f"tel. {phone}" if phone else "",
        (getattr(client, "email", "") or "").strip(),
        (getattr(client, "website", "") or "").strip(),
    ]
    return "; ".join(part for part in parts if part)
