from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from backend import company_registry_service
from backend.company_registry_service import (
    CompanyRegistryUnavailableError,
    _lookup_cached,
    build_company_registry_cache,
    normalize_registry_identifier,
    refresh_company_registry_cache,
)
from backend.models import Client, User
from backend.routers import clients_router
from backend.schemas import ClientCreate, ClientUpdate


APR_PAYLOAD = {
    "DatumPreseka": "2026-08-31",
    "Podaci": {
        "01234567": {
            "PoslovnoIme": "APR OFFICIAL COMPANY DOO VRŠAC",
            "SifraOpstine": "80047",
            "NazivOpstine": "ВРШАЦ",
            "NazivStatus": "Активан",
            "DatumOsnivanja": "2015-06-01",
            "NazivPravneForme": "Друштво са ограниченом одговорношћу",
            "SifraDelatnosti": "4321",
        }
    },
}

SEF_PAYLOAD = [
    {
        "BugetCompanyNumber": None,
        "RegistrationCode": "01234567",
        "VatRegistrationCode": "123456789",
        "Name": "Older SEF spelling",
        "RegistrationDate": "2022-04-11T00:00:00+00:00",
        "DeletionDate": None,
    }
]


def test_registry_cache_combines_sef_identifiers_with_apr_company_data(tmp_path):
    cache_path = tmp_path / "registry.db"
    build_company_registry_cache(
        cache_path,
        sef_payload=SEF_PAYLOAD,
        apr_payload=APR_PAYLOAD,
        refreshed_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
    )

    result = _lookup_cached(cache_path, "pib", "123456789", stale=False)

    assert result["apr_snapshot_date"] == "2026-08-31"
    assert result["stale"] is False
    assert len(result["matches"]) == 1
    match = result["matches"][0]
    assert match["name"] == "APR OFFICIAL COMPANY DOO VRŠAC"
    assert match["pib"] == "123456789"
    assert match["maticni_broj"] == "01234567"
    assert match["municipality"] == "ВРШАЦ"
    assert {source["code"] for source in match["sources"]} == {"apr_open_data", "sef_company_list"}


def test_registry_cache_preserves_leading_zero_in_maticni_broj(tmp_path):
    cache_path = tmp_path / "registry.db"
    build_company_registry_cache(cache_path, sef_payload=SEF_PAYLOAD, apr_payload=APR_PAYLOAD)

    result = _lookup_cached(cache_path, "maticni_broj", "01234567", stale=False)

    assert result["matches"][0]["maticni_broj"] == "01234567"


def test_registry_cache_can_find_a_sef_only_entity_by_pib(tmp_path):
    cache_path = tmp_path / "registry.db"
    build_company_registry_cache(
        cache_path,
        sef_payload=SEF_PAYLOAD,
        apr_payload={"DatumPreseka": "2026-08-31", "Podaci": {}},
    )

    result = _lookup_cached(cache_path, "pib", "123456789", stale=False)

    assert result["matches"][0]["name"] == "Older SEF spelling"
    assert result["matches"][0]["municipality"] is None
    assert [source["code"] for source in result["matches"][0]["sources"]] == ["sef_company_list"]


def test_registry_cache_can_find_an_apr_only_entity_by_maticni_broj(tmp_path):
    cache_path = tmp_path / "registry.db"
    build_company_registry_cache(cache_path, sef_payload=[], apr_payload=APR_PAYLOAD)

    result = _lookup_cached(cache_path, "maticni_broj", "01234567", stale=False)

    assert result["matches"][0]["name"] == "APR OFFICIAL COMPANY DOO VRŠAC"
    assert result["matches"][0]["pib"] is None
    assert [source["code"] for source in result["matches"][0]["sources"]] == ["apr_open_data"]


def test_registry_cache_supports_apr_naziv_statusa_field(tmp_path):
    cache_path = tmp_path / "registry.db"
    apr_payload = {
        "DatumPreseka": "2026-08-31",
        "Podaci": {
            "01234567": {
                "PoslovnoIme": "APR OFFICIAL COMPANY DOO VRŠAC",
                "NazivStatusa": "Активан",
            }
        },
    }
    build_company_registry_cache(cache_path, sef_payload=[], apr_payload=apr_payload)

    result = _lookup_cached(cache_path, "maticni_broj", "01234567", stale=False)

    assert result["matches"][0]["status"] == "Активан"


def test_first_refresh_can_use_sef_when_apr_is_temporarily_unavailable(monkeypatch, tmp_path):
    cache_path = tmp_path / "registry.db"

    def fake_download(url, timeout_seconds):
        assert timeout_seconds == 5
        if url == company_registry_service.SEF_COMPANIES_URL:
            return SEF_PAYLOAD
        raise OSError("APR unavailable")

    monkeypatch.setattr(company_registry_service, "_download_json", fake_download)

    refresh_company_registry_cache(cache_path, 5)
    result = _lookup_cached(cache_path, "pib", "123456789", stale=False)

    assert result["matches"][0]["name"] == "Older SEF spelling"
    assert result["warning"]


def test_partial_refresh_does_not_replace_an_existing_complete_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "registry.db"
    build_company_registry_cache(cache_path, sef_payload=SEF_PAYLOAD, apr_payload=APR_PAYLOAD)

    def fake_download(url, _timeout_seconds):
        if url == company_registry_service.SEF_COMPANIES_URL:
            return [{**SEF_PAYLOAD[0], "Name": "New partial spelling"}]
        raise OSError("APR unavailable")

    monkeypatch.setattr(company_registry_service, "_download_json", fake_download)

    with pytest.raises(CompanyRegistryUnavailableError):
        refresh_company_registry_cache(cache_path, 5)

    result = _lookup_cached(cache_path, "pib", "123456789", stale=True)
    assert result["matches"][0]["name"] == "APR OFFICIAL COMPANY DOO VRŠAC"


def test_failed_cache_rebuild_keeps_previous_atomic_cache(tmp_path):
    cache_path = tmp_path / "registry.db"
    build_company_registry_cache(cache_path, sef_payload=SEF_PAYLOAD, apr_payload=APR_PAYLOAD)

    with pytest.raises(ValueError, match="Unexpected APR"):
        build_company_registry_cache(cache_path, sef_payload=SEF_PAYLOAD, apr_payload={"bad": "payload"})

    result = _lookup_cached(cache_path, "pib", "123456789", stale=True)
    assert result["matches"][0]["name"] == "APR OFFICIAL COMPANY DOO VRŠAC"


@pytest.mark.parametrize(
    ("value", "identifier_type", "expected"),
    [
        ("RS 123-456-789", "pib", "123456789"),
        ("01 234 567", "maticni_broj", "01234567"),
    ],
)
def test_registry_identifiers_are_normalized(value, identifier_type, expected):
    assert normalize_registry_identifier(value, identifier_type) == expected


@pytest.mark.parametrize(
    ("value", "identifier_type"),
    [("123", "pib"), ("123456789", "maticni_broj")],
)
def test_registry_identifier_length_is_validated(value, identifier_type):
    with pytest.raises(ValueError):
        normalize_registry_identifier(value, identifier_type)


@pytest.mark.asyncio
async def test_registry_lookup_marks_an_existing_client(monkeypatch, db_session):
    existing = Client(name="Existing company", pib="RS123456789", maticni_broj="01234567")
    db_session.add(existing)
    await db_session.flush()

    async def fake_lookup(identifier_type, value):
        return {
            "query_type": identifier_type,
            "query_value": value,
            "matches": [
                {
                    "name": "APR OFFICIAL COMPANY DOO VRŠAC",
                    "pib": "123456789",
                    "maticni_broj": "01234567",
                    "sources": [],
                }
            ],
            "refreshed_at": "2026-09-21T00:00:00+00:00",
            "apr_snapshot_date": "2026-08-31",
            "stale": False,
            "warning": None,
        }

    monkeypatch.setattr(clients_router, "lookup_company_registry", fake_lookup)

    response = await clients_router.lookup_client_company_registry(
        identifier_type="pib",
        value="123456789",
        exclude_client_id=None,
        db=db_session,
        current_user=User(username="test"),
    )

    assert response.matches[0].existing_client_id == existing.id
    assert response.matches[0].existing_client_name == "Existing company"


@pytest.mark.asyncio
async def test_registry_lookup_does_not_flag_the_client_being_edited(monkeypatch, db_session):
    existing = Client(name="Existing company", pib="123456789", maticni_broj="01234567")
    db_session.add(existing)
    await db_session.flush()

    async def fake_lookup(identifier_type, value):
        return {
            "query_type": identifier_type,
            "query_value": value,
            "matches": [
                {
                    "name": "APR OFFICIAL COMPANY DOO VRŠAC",
                    "pib": "123456789",
                    "maticni_broj": "01234567",
                    "sources": [],
                }
            ],
            "refreshed_at": None,
            "apr_snapshot_date": None,
            "stale": False,
            "warning": None,
        }

    monkeypatch.setattr(clients_router, "lookup_company_registry", fake_lookup)

    response = await clients_router.lookup_client_company_registry(
        identifier_type="maticni_broj",
        value="01234567",
        exclude_client_id=existing.id,
        db=db_session,
        current_user=User(username="test"),
    )

    assert response.matches[0].existing_client_id is None


@pytest.mark.asyncio
async def test_registry_lookup_uses_pib_before_shared_maticni_broj(monkeypatch, db_session):
    shared_maticni = "01234567"
    peer = Client(name="Budget peer", pib="111111111", maticni_broj=shared_maticni)
    exact = Client(name="Exact PIB client", pib="123456789", maticni_broj=shared_maticni)
    db_session.add_all([peer, exact])
    await db_session.flush()

    async def fake_lookup(identifier_type, value):
        return {
            "query_type": identifier_type,
            "query_value": value,
            "matches": [
                {
                    "name": "Registry company",
                    "pib": "123456789",
                    "maticni_broj": shared_maticni,
                    "sources": [],
                }
            ],
            "refreshed_at": None,
            "apr_snapshot_date": None,
            "stale": False,
            "warning": None,
        }

    monkeypatch.setattr(clients_router, "lookup_company_registry", fake_lookup)

    response = await clients_router.lookup_client_company_registry(
        identifier_type="pib",
        value="123456789",
        exclude_client_id=None,
        db=db_session,
        current_user=User(username="test"),
    )

    assert response.matches[0].existing_client_id == exact.id
    assert response.matches[0].existing_client_name == exact.name


@pytest.mark.asyncio
async def test_registry_lookup_uses_jbkjs_for_budget_units_sharing_pib_and_maticni(monkeypatch, db_session):
    shared_values = {"pib": "123456789", "maticni_broj": "01234567"}
    first = Client(name="Budget unit one", jbkjs="11111", **shared_values)
    second = Client(name="Budget unit two", jbkjs="22222", **shared_values)
    db_session.add_all([first, second])
    await db_session.flush()

    async def fake_lookup(identifier_type, value):
        return {
            "query_type": identifier_type,
            "query_value": value,
            "matches": [
                {
                    "name": "Budget unit two",
                    "pib": shared_values["pib"],
                    "maticni_broj": shared_values["maticni_broj"],
                    "jbkjs": "22222",
                    "sources": [],
                }
            ],
            "refreshed_at": None,
            "apr_snapshot_date": None,
            "stale": False,
            "warning": None,
        }

    monkeypatch.setattr(clients_router, "lookup_company_registry", fake_lookup)

    response = await clients_router.lookup_client_company_registry(
        identifier_type="pib",
        value=shared_values["pib"],
        exclude_client_id=None,
        db=db_session,
        current_user=User(username="test"),
    )

    assert response.matches[0].existing_client_id == second.id
    assert response.matches[0].existing_client_name == second.name


@pytest.mark.asyncio
async def test_registry_lookup_falls_back_to_maticni_when_apr_has_no_pib(monkeypatch, db_session):
    existing = Client(name="APR-only client", pib="123456789", maticni_broj="01234567")
    db_session.add(existing)
    await db_session.flush()

    async def fake_lookup(identifier_type, value):
        return {
            "query_type": identifier_type,
            "query_value": value,
            "matches": [
                {
                    "name": "APR-only company",
                    "pib": None,
                    "maticni_broj": "01234567",
                    "sources": [],
                }
            ],
            "refreshed_at": None,
            "apr_snapshot_date": None,
            "stale": False,
            "warning": None,
        }

    monkeypatch.setattr(clients_router, "lookup_company_registry", fake_lookup)

    response = await clients_router.lookup_client_company_registry(
        identifier_type="maticni_broj",
        value="01234567",
        exclude_client_id=None,
        db=db_session,
        current_user=User(username="test"),
    )

    assert response.matches[0].existing_client_id == existing.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_values", "new_values", "detail_prefix"),
    [
        ({"pib": "RS 123-456-789"}, {"pib": "123456789"}, "PIB already belongs"),
        (
            {"maticni_broj": "01 234 567"},
            {"maticni_broj": "01234567"},
            "Matični broj already belongs",
        ),
    ],
)
async def test_create_client_rejects_normalized_duplicate_identifiers(
    db_session,
    existing_values,
    new_values,
    detail_prefix,
):
    db_session.add(Client(name="Existing company", **existing_values))
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await clients_router.create_client(
            ClientCreate(name="Duplicate company", **new_values),
            db=db_session,
            current_user=User(username="test"),
        )

    assert exc_info.value.status_code == 409
    assert str(exc_info.value.detail).startswith(detail_prefix)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("update_values", "detail_prefix"),
    [
        ({"pib": "123456789"}, "PIB already belongs"),
        ({"maticni_broj": "01234567"}, "Matični broj already belongs"),
    ],
)
async def test_update_client_rejects_changed_duplicate_identifiers(
    db_session,
    update_values,
    detail_prefix,
):
    owner = Client(name="Identifier owner", pib="123456789", maticni_broj="01234567")
    target_pib = None if "maticni_broj" in update_values else "987654321"
    target = Client(name="Target", pib=target_pib, maticni_broj="87654321")
    db_session.add_all([owner, target])
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await clients_router.update_client(
            target.id,
            ClientUpdate(**update_values),
            db=db_session,
            current_user=User(username="test"),
        )

    assert exc_info.value.status_code == 409
    assert str(exc_info.value.detail).startswith(detail_prefix)


@pytest.mark.asyncio
async def test_create_client_allows_budget_entities_with_distinct_pib_and_shared_maticni(db_session):
    db_session.add(Client(name="Budget parent", pib="111111111", maticni_broj="01234567"))
    await db_session.flush()

    response = await clients_router.create_client(
        ClientCreate(
            name="Budget unit",
            pib="222222222",
            maticni_broj="01234567",
        ),
        db=db_session,
        current_user=User(username="test"),
    )

    assert response.name == "Budget unit"
    assert response.pib == "222222222"


@pytest.mark.asyncio
async def test_create_client_allows_budget_units_with_distinct_jbkjs_and_shared_legal_identifiers(db_session):
    shared_values = {"pib": "123456789", "maticni_broj": "01234567"}
    db_session.add(Client(name="Budget unit one", jbkjs="11111", **shared_values))
    await db_session.flush()

    response = await clients_router.create_client(
        ClientCreate(name="Budget unit two", jbkjs="22222", **shared_values),
        db=db_session,
        current_user=User(username="test"),
    )

    assert response.name == "Budget unit two"
    assert response.jbkjs == "22222"


@pytest.mark.asyncio
async def test_create_client_rejects_duplicate_jbkjs(db_session):
    db_session.add(Client(name="Budget unit", jbkjs="12 345"))
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await clients_router.create_client(
            ClientCreate(name="Duplicate budget unit", jbkjs="12345"),
            db=db_session,
            current_user=User(username="test"),
        )

    assert exc_info.value.status_code == 409
    assert str(exc_info.value.detail).startswith("JBKJS already belongs")


@pytest.mark.asyncio
async def test_update_client_allows_unchanged_identifiers_on_legacy_duplicate(db_session):
    first = Client(
        name="First legacy duplicate",
        pib="RS 123-456-789",
        maticni_broj="01 234 567",
    )
    second = Client(
        name="Second legacy duplicate",
        pib="123456789",
        maticni_broj="01234567",
    )
    db_session.add_all([first, second])
    await db_session.flush()

    response = await clients_router.update_client(
        first.id,
        ClientUpdate(
            name="Renamed legacy client",
            pib="123456789",
            maticni_broj="01234567",
        ),
        db=db_session,
        current_user=User(username="test"),
    )

    assert response.name == "Renamed legacy client"
    assert response.pib == "123456789"
    assert response.maticni_broj == "01234567"
