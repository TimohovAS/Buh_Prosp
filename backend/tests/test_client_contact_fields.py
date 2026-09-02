import pytest

from backend.models import Client
from backend.routers.clients_router import _load_client
from backend.schemas import ClientResponse
from backend.work_diary_export import _contact_line


def test_contact_line_joins_filled_fields_only():
    client = Client(name="Muzej", contact="Ivana Ranimirov", phone="013/838-053", website="www.muzej.rs")

    assert _contact_line(client) == "Ivana Ranimirov; tel. 013/838-053; www.muzej.rs"


def test_contact_line_is_empty_without_contact_data():
    assert _contact_line(Client(name="Muzej")) == ""


@pytest.mark.asyncio
async def test_client_response_exposes_contact_fields(db_session):
    client = Client(
        name="GRADSKI MUZEJ VRŠAC",
        contact="Ivana Ranimirov, direktor",
        phone="013/838-053",
        email="muzejvrsac@open.telekom.rs",
        website="www.muzejvrsac.org.rs",
    )
    db_session.add(client)
    await db_session.flush()

    response = ClientResponse.model_validate(await _load_client(db_session, client.id))

    assert response.contact == "Ivana Ranimirov, direktor"
    assert response.phone == "013/838-053"
    assert response.email == "muzejvrsac@open.telekom.rs"
    assert response.website == "www.muzejvrsac.org.rs"
