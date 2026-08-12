import pytest
from sqlalchemy import select

from backend.models import Client, ClientBankAccount
from backend.routers.clients_router import _load_client, _sync_bank_accounts
from backend.schemas import ClientResponse


@pytest.mark.asyncio
async def test_client_bank_accounts_are_normalized_and_serialized(db_session):
    client = Client(name="S.B.H.-SO TRADE DOO")
    db_session.add(client)
    await db_session.flush()

    await _sync_bank_accounts(
        db_session,
        client,
        ["205-0000000216009-21", "205000000021600921"],
    )
    loaded_client = await _load_client(db_session, client.id)
    response = ClientResponse.model_validate(loaded_client)

    assert response.bank_accounts == ["205000000021600921"]
    records = list((await db_session.scalars(select(ClientBankAccount))).all())
    assert len(records) == 1
    assert records[0].source == "manual"


@pytest.mark.asyncio
async def test_client_bank_account_cannot_belong_to_two_clients(db_session):
    first = Client(name="First")
    second = Client(name="Second")
    db_session.add_all([first, second])
    await db_session.flush()
    await _sync_bank_accounts(db_session, first, ["205000000021600921"])

    with pytest.raises(ValueError, match="belongs to another client"):
        await _sync_bank_accounts(db_session, second, ["205000000021600921"])


@pytest.mark.asyncio
async def test_client_bank_account_rejects_invalid_checksum(db_session):
    client = Client(name="Client")
    db_session.add(client)
    await db_session.flush()

    with pytest.raises(ValueError, match="Invalid Serbian bank account"):
        await _sync_bank_accounts(db_session, client, ["205000000021600922"])
