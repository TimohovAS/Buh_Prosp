import pytest

from backend.client_contact_utils import format_contact_line, split_contact_line
from backend.models import Client
from backend.routers.clients_router import _load_client
from backend.schemas import ClientResponse


def test_split_contact_line_separates_person_phone_email_and_site():
    parts = split_contact_line(
        "STEFAN; Ivana Ranimirov, direktor; tel. 013/838-053, 013/832-902; "
        "muzejvrsac@open.telekom.rs; www.muzejvrsac.org.rs"
    )

    assert parts == {
        "contact": "STEFAN; Ivana Ranimirov, direktor",
        "phone": "013/838-053, 013/832-902",
        "email": "muzejvrsac@open.telekom.rs",
        "website": "www.muzejvrsac.org.rs",
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Номер без пометки «tel» — распознаём по количеству цифр.
        ("Nenad 060 5777129", {"contact": "Nenad", "phone": "060 5777129", "email": "", "website": ""}),
        (
            "IGOR,  BRANISLAV; tel.0611353741",
            {"contact": "IGOR, BRANISLAV", "phone": "0611353741", "email": "", "website": ""},
        ),
        ("ALEKSANDAR PUZAREVIC", {"contact": "ALEKSANDAR PUZAREVIC", "phone": "", "email": "", "website": ""}),
        ("", {"contact": "", "phone": "", "email": "", "website": ""}),
        (None, {"contact": "", "phone": "", "email": "", "website": ""}),
    ],
)
def test_split_contact_line_handles_free_form_records(raw, expected):
    assert split_contact_line(raw) == expected


def test_format_contact_line_joins_filled_fields_only():
    client = Client(name="Muzej", contact="Ivana Ranimirov", phone="013/838-053", website="www.muzej.rs")

    assert format_contact_line(client) == "Ivana Ranimirov; tel. 013/838-053; www.muzej.rs"


def test_format_contact_line_is_empty_without_contact_data():
    assert format_contact_line(Client(name="Muzej")) == ""


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
