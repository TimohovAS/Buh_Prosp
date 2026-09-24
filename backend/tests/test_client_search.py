import pytest

from backend.models import Client, ClientBankAccount
from backend.routers.clients_router import list_clients, list_clients_brief
from backend.text_utils import fold_search_text, matches_search


def test_fold_search_text_ignores_script_diacritics_and_case():
    assert fold_search_text("АИМА ДРУШТВО") == "aima drustvo"
    assert fold_search_text("Vršac") == fold_search_text("VRSAC") == fold_search_text("Вршац") == "vrsac"
    assert fold_search_text("Љубиша Њиве Џеп") == "ljubisa njive dzep"
    assert fold_search_text("Ćevap Čačak Žabalj") == "cevap cacak zabalj"
    assert fold_search_text(None) == ""


def test_fold_search_text_treats_dj_and_d_as_the_same_letter():
    for spelling in ("ĐURĐEVO", "Djurdjevo", "durdevo", "Ђурђево"):
        assert fold_search_text(spelling) == "durdevo"


def test_matches_search_needs_every_word_in_some_field():
    assert matches_search("muzej vrsac", "GRADSKI MUZEJ", "Beogradski put, Vršac")
    assert not matches_search("muzej novi sad", "GRADSKI MUZEJ", "Beogradski put, Vršac")
    assert matches_search("   ", "anything")


async def _add_clients(db_session):
    aima = Client(name="АИМА ДРУШТВО СА ОГРАНИЧЕНОМ ОДГОВОРНОШЋУ ВРШАЦ", pib="108755328")
    struja = Client(name="DOO STRUJA DD TIM ĐURĐEVO", pib="110299370")
    so_trade = Client(name="S.B.H.-SO TRADE DOO Nova Pazova")
    archived = Client(name="AIMA STARA", is_archived=True)
    db_session.add_all([aima, struja, so_trade, archived])
    await db_session.flush()
    db_session.add(ClientBankAccount(client_id=so_trade.id, account_number="205000000021600921", source="manual"))
    await db_session.flush()
    return aima, struja, so_trade


async def _search(db_session, search):
    return [client.name for client in await list_clients(search=search, archived=False, db=db_session)]


@pytest.mark.asyncio
async def test_client_list_finds_cyrillic_name_by_latin_search(db_session):
    aima, struja, _ = await _add_clients(db_session)

    assert await _search(db_session, "aima") == [aima.name]
    assert await _search(db_session, "аима вршац") == [aima.name]
    assert await _search(db_session, "Vršac") == [aima.name]
    assert await _search(db_session, "djurdjevo") == [struja.name]
    assert await _search(db_session, "108755") == [aima.name]


@pytest.mark.asyncio
async def test_client_list_still_finds_bank_account_typed_with_dashes(db_session):
    _, _, so_trade = await _add_clients(db_session)

    assert await _search(db_session, "205-0000000216009-21") == [so_trade.name]
    assert len(await _search(db_session, "")) == 3


@pytest.mark.asyncio
async def test_client_brief_search_uses_the_same_matching(db_session):
    aima, _, _ = await _add_clients(db_session)

    result = await list_clients_brief(search="Aima", db=db_session)

    assert [client.name for client in result] == [aima.name]
