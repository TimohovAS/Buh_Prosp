from datetime import date

import pytest

from backend.db_utils import resolve_project_contract_links
from backend.models import Client, Contract
from backend.tests.conftest import TEST_NOW


async def test_unbound_contract_is_not_attached_to_completed_project(db_session, make_project):
    client = Client(name="ACME")
    db_session.add(client)
    await db_session.flush()
    project = await make_project(db_session, code="PR-C", status="completed")
    contract = Contract(
        number="C-2",
        date=date(2026, 1, 1),
        client_id=client.id,
        project_id=None,
        created_at=TEST_NOW,
        updated_at=TEST_NOW,
    )
    db_session.add(contract)
    await db_session.flush()

    with pytest.raises(ValueError, match="Cannot use completed project"):
        await resolve_project_contract_links(
            db_session,
            project.id,
            contract.id,
            validation_exc_cls=ValueError,
            allow_completed=True,
        )

    assert contract.project_id is None
