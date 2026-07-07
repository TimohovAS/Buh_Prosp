from decimal import Decimal

import pytest

from backend.payment_qr_service import (
    account_to_18_digits,
    build_ips_payload,
    format_ips_amount,
    render_qr_png_data_url,
)


def test_account_to_18_digits_pads_middle_part():
    assert account_to_18_digits("840-711122843-32") == "840000071112284332"
    assert account_to_18_digits("840-721419843-40") == "840000072141984340"


def test_account_to_18_digits_rejects_malformed():
    for bad in ["840-711122843", "84-711122843-32", "840-711122843-3", "840-71112a843-32", "", None]:
        with pytest.raises(ValueError):
            account_to_18_digits(bad)


def test_account_to_18_digits_rejects_bad_control_digits():
    # реальная опечатка: пропущена цифра в середине, контрольное число не сходится
    with pytest.raises(ValueError, match="контрольного числа"):
        account_to_18_digits("840-71122843-32")
    with pytest.raises(ValueError, match="контрольного числа"):
        account_to_18_digits("840-711122843-33")


def test_format_ips_amount_uses_decimal_comma():
    assert format_ips_amount(Decimal("5122.16")) == "RSD5122,16"
    assert format_ips_amount(Decimal("12311.28")) == "RSD12311,28"
    assert format_ips_amount(100) == "RSD100,00"


def test_format_ips_amount_rejects_non_positive():
    with pytest.raises(ValueError):
        format_ips_amount(0)
    with pytest.raises(ValueError):
        format_ips_amount(Decimal("-1"))


def test_build_ips_payload_matches_nbs_format():
    payload = build_ips_payload(
        recipient_account="840-711122843-32",
        recipient_name="Пореска управа Републике Србије",
        amount=Decimal("5122.16"),
        payer_name="Andrei Timokhov pr ProspEl",
        sifra_placanja="253",
        payment_purpose="Porez na paušalni prihod za 2026. godinu",
        model="97",
        poziv_na_broj="2624190000007887475",
    )
    assert payload == (
        "K:PR|V:01|C:1|R:840000071112284332"
        "|N:Пореска управа Републике Србије"
        "|I:RSD5122,16"
        "|P:Andrei Timokhov pr ProspEl"
        "|SF:253"
        "|S:Porez na paušalni prihod za 2026. g"
        "|RO:972624190000007887475"
    )


def test_build_ips_payload_truncates_purpose_to_35_chars():
    payload = build_ips_payload(
        recipient_account="840-711122843-32",
        recipient_name="Test",
        amount=1,
        payment_purpose="X" * 60,
    )
    s_tag = next(part for part in payload.split("|") if part.startswith("S:"))
    assert len(s_tag) == 2 + 35


def test_build_ips_payload_strips_pipe_from_values():
    payload = build_ips_payload(
        recipient_account="840-711122843-32",
        recipient_name="Bad|Name",
        amount=1,
    )
    assert "Bad Name" in payload
    assert payload.count("K:") == 1


def test_build_ips_payload_reference_digits_only():
    payload = build_ips_payload(
        recipient_account="840-711122843-32",
        recipient_name="Test",
        amount=1,
        model="97",
        poziv_na_broj="26-2419000 0007887475",
    )
    assert payload.endswith("RO:972624190000007887475")


def test_render_qr_png_returns_data_url():
    url = render_qr_png_data_url("K:PR|V:01|C:1|R:840000071112284332|N:Test|I:RSD1,00")
    assert url.startswith("data:image/png;base64,")
    assert len(url) > 200
