"""Генерация NBS IPS QR-кода для оплаты налоговых обязательств.

Формат по спецификации Народного банка Сербии (IPS QR kod, "K:PR"):
теги разделяются символом '|', счёт получателя кодируется 18 цифрами
(банк 3 + номер с ведущими нулями до 13 + контрольные 2), сумма — с
десятичной запятой, RO — модель контроля + позив на број без пробелов.

Два требования, без которых банковские приложения пишут «неисправан QR»
(проверено по эталонным QR из решений Пореской управы, tmp/*.pdf):
1. Весь payload — ОДИН сегмент 8-битного byte-режима (UTF-8). Библиотека
   qrcode по умолчанию дробит строку на numeric/alphanumeric/byte сегменты,
   и строгий парсер IPS это не принимает.
2. Текстовые поля — латиница (эталон банка на латинице); кириллицу
   транслитерируем.
"""

import base64
from decimal import Decimal
from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_M
from qrcode.util import MODE_8BIT_BYTE, QRData

from backend.decimal_utils import to_decimal
from backend.text_utils import to_serbian_latin

MAX_NAME_LENGTH = 70
MAX_PURPOSE_LENGTH = 35
MAX_REFERENCE_LENGTH = 25
IPS_TAG_SEPARATOR = "|"


def account_to_18_digits(account: str) -> str:
    """840-711122843-32 -> 840000071112284332 (формат R-тега IPS QR)."""
    parts = [part for part in str(account or "").replace(" ", "").split("-") if part]
    if (
        len(parts) != 3
        or not all(part.isdigit() for part in parts)
        or len(parts[0]) != 3
        or not 1 <= len(parts[1]) <= 13
        or len(parts[2]) != 2
    ):
        raise ValueError(f"Некорректный счёт получателя: '{account}' (ожидается формат NNN-NNNNNNNNN-NN)")
    # Контрольное число по модулю 97 (сербский стандарт платёжных счетов):
    # ловит опечатки в реквизитах до того, как банк отклонит платёж.
    expected_control = 98 - (int(parts[0] + parts[1].zfill(13)) * 100) % 97
    if int(parts[2]) != expected_control:
        raise ValueError(
            f"Счёт получателя '{account}' не проходит проверку контрольного числа — проверьте реквизиты решения"
        )
    return parts[0] + parts[1].zfill(13) + parts[2]


def format_ips_amount(amount) -> str:
    value = to_decimal(amount)
    if value < 0:
        raise ValueError("Payment amount cannot be negative")
    return f"RSD{value.quantize(Decimal('0.01'))}".replace(".", ",")


def _clean(value: str | None, max_length: int) -> str:
    # IPS tag separators are not allowed inside field values; text on Latin.
    latin = to_serbian_latin(value)
    return latin.replace("|", " ").replace("\r", " ").replace("\n", " ").strip()[:max_length].rstrip()


def normalize_ips_payment_purpose(purpose: str | None) -> str:
    value = str(purpose or "").strip()
    if value.startswith("Porez na pau") and value.endswith(". godinu"):
        return value[: -len(" godinu")]
    return value


def build_ips_payload(
    *,
    recipient_account: str,
    recipient_name: str,
    amount,
    payer_name: str | None = None,
    sifra_placanja: str | None = "253",
    payment_purpose: str | None = "",
    model: str | None = "97",
    poziv_na_broj: str | None = "",
) -> str:
    tags = [
        ("K", "PR"),
        ("V", "01"),
        ("C", "1"),
        ("R", account_to_18_digits(recipient_account)),
        ("N", _clean(recipient_name, MAX_NAME_LENGTH)),
        ("I", format_ips_amount(amount)),
    ]
    if payer_name:
        tags.append(("P", _clean(payer_name, MAX_NAME_LENGTH)))
    if sifra_placanja:
        tags.append(("SF", _clean(sifra_placanja, 3)))
    purpose = _clean(normalize_ips_payment_purpose(payment_purpose), MAX_PURPOSE_LENGTH)
    if purpose:
        tags.append(("S", purpose))
    reference = "".join(ch for ch in str(poziv_na_broj or "") if ch.isdigit())
    if reference:
        model_digits = "".join(ch for ch in str(model or "") if ch.isdigit())
        tags.append(("RO", (model_digits + reference)[:MAX_REFERENCE_LENGTH]))
    return IPS_TAG_SEPARATOR.join(f"{key}:{value}" for key, value in tags)


def render_qr_png_data_url(payload: str) -> str:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=8, border=2)
    # Один сегмент 8-битного byte-режима (UTF-8), без авто-дробления на
    # numeric/alphanumeric — иначе банковский парсер IPS QR его отвергает.
    qr.add_data(QRData(payload.encode("utf-8"), mode=MODE_8BIT_BYTE))
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
