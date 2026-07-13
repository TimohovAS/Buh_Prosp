from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.models import Enterprise, ExpenseItem, PurchaseReceipt, PurchaseReceiptItem, User, Worker
from backend.routers.work_diaries_router import (
    create_entry,
    get_project_costs,
    get_summary,
    list_entries,
    list_expense_options,
    update_entry,
)
from backend.schemas import (
    WorkDiaryEntryCreate,
    WorkDiaryEntryUpdate,
    WorkDiaryMaterialCreate,
)


def _make_user(db_session, name="diary-admin"):
    user = User(username=name, password_hash="hash", role="admin")
    db_session.add(user)
    return user


@pytest.mark.asyncio
async def test_work_diary_entry_supports_multiple_workers(db_session, make_project):
    project = await make_project(db_session)
    user = _make_user(db_session)
    worker_a = Worker(name="Ana", regular_day_rate=Decimal("800"), billing_hourly_rate=Decimal("300"))
    worker_b = Worker(name="Boris", regular_day_rate=Decimal("1200"), billing_hourly_rate=Decimal("450"))
    db_session.add_all([worker_a, worker_b])
    await db_session.flush()

    entry = await create_entry(
        WorkDiaryEntryCreate(
            date=date(2026, 7, 10),
            project_id=project.id,
            worker_ids=[worker_b.id, worker_a.id, worker_b.id],
            description="Installation work",
            start_time="07:00",
            end_time="15:00",
        ),
        db_session,
        user,
    )

    assert set(entry.worker_ids) == {worker_a.id, worker_b.id}
    assert entry.worker_names == ["Ana", "Boris"]
    assert entry.duration_hours == 8
    assert entry.person_hours == 16
    assert entry.regular_person_hours == 16
    assert entry.overtime_person_hours == 0
    assert entry.team_hourly_rate_snapshot == 250
    assert entry.team_billing_hourly_rate_snapshot == 750
    assert entry.labor_amount == 2000
    assert entry.billable_amount == 6000


@pytest.mark.asyncio
async def test_work_diary_worker_filter_and_summary_use_all_assigned_workers(db_session, make_project):
    project = await make_project(db_session)
    user = _make_user(db_session, "diary-filter-admin")
    worker_a = Worker(name="Ana", regular_day_rate=Decimal("800"), billing_hourly_rate=Decimal("100"))
    worker_b = Worker(name="Boris", regular_day_rate=Decimal("1200"), billing_hourly_rate=Decimal("100"))
    db_session.add_all([worker_a, worker_b])
    await db_session.flush()

    entry = await create_entry(
        WorkDiaryEntryCreate(
            date=date(2026, 7, 10),
            project_id=project.id,
            worker_ids=[worker_a.id, worker_b.id],
            description="Team work",
            duration_hours=4,
            materials=[WorkDiaryMaterialCreate(description="Cable", quantity=1, unit="kom", amount=50)],
        ),
        db_session,
        user,
    )

    filtered = await list_entries(project.id, worker_b.id, None, None, db_session, user)
    summary = await get_summary(project.id, None, None, None, db_session, user)

    assert len(filtered) == 1
    assert filtered[0].worker_ids == [worker_a.id, worker_b.id]
    assert summary.entries_count == 1
    assert summary.workers_count == 2
    assert summary.person_hours == 8
    assert summary.regular_person_hours == 8
    assert summary.overtime_person_hours == 0
    assert summary.stock_material_amount == 50
    assert summary.linked_material_amount == 0
    assert entry.team_billing_hourly_rate_snapshot == 200
    assert entry.billable_amount == 850


@pytest.mark.asyncio
async def test_work_diary_overtime_uses_legal_default_multiplier(db_session, make_project):
    project = await make_project(db_session)
    user = _make_user(db_session, "diary-overtime-admin")
    worker_a = Worker(name="Ana", regular_day_rate=Decimal("800"))
    worker_b = Worker(name="Boris", regular_day_rate=Decimal("1200"))
    db_session.add_all([worker_a, worker_b])
    await db_session.flush()

    entry = await create_entry(
        WorkDiaryEntryCreate(
            date=date(2026, 7, 10),
            project_id=project.id,
            worker_ids=[worker_a.id, worker_b.id],
            description="Long team shift",
            duration_hours=10,
        ),
        db_session,
        user,
    )

    assert entry.duration_hours == 10
    assert entry.person_hours == 20
    assert entry.regular_person_hours == 16
    assert entry.overtime_person_hours == 4
    assert entry.overtime_multiplier == 1.26
    assert entry.labor_amount == 8 * 250 + 2 * 250 * 1.26


@pytest.mark.asyncio
async def test_work_diary_overtime_multiplier_comes_from_enterprise_settings(db_session, make_project):
    project = await make_project(db_session)
    user = _make_user(db_session, "diary-settings-admin")
    worker = Worker(name="Ana", regular_day_rate=Decimal("800"), billing_hourly_rate=Decimal("200"))
    db_session.add_all([worker, Enterprise(name="Test", work_diary_overtime_multiplier=Decimal("1.5"))])
    await db_session.flush()

    entry = await create_entry(
        WorkDiaryEntryCreate(
            date=date(2026, 7, 10),
            project_id=project.id,
            worker_ids=[worker.id],
            description="Overtime shift",
            duration_hours=10,
        ),
        db_session,
        user,
    )

    assert entry.overtime_multiplier == 1.5
    assert entry.labor_amount == 8 * 100 + 2 * 100 * 1.5


@pytest.mark.asyncio
async def test_work_diary_per_diem_and_food_are_per_worker(db_session, make_project):
    project = await make_project(db_session)
    user = _make_user(db_session, "diary-allowance-admin")
    worker_a = Worker(name="Ana", regular_day_rate=Decimal("800"))
    worker_b = Worker(name="Boris", regular_day_rate=Decimal("1200"))
    db_session.add_all([worker_a, worker_b])
    await db_session.flush()

    entry = await create_entry(
        WorkDiaryEntryCreate(
            date=date(2026, 7, 10),
            project_id=project.id,
            worker_ids=[worker_a.id, worker_b.id],
            description="Trip work",
            duration_hours=8,
            per_diem=True,
            per_diem_amount=1000,
            food_allowance=True,
            food_amount=500,
            lodging_amount=3000,
        ),
        db_session,
        user,
    )

    # Дневница и питание — на человека, проживание — на бригаду целиком
    assert entry.allowance_amount == 1000 * 2 + 500 * 2 + 3000
    assert entry.payout_amount == entry.labor_amount + entry.allowance_amount


@pytest.mark.asyncio
async def test_work_diary_linked_material_is_not_double_counted(db_session, make_project, make_expense):
    project = await make_project(db_session)
    user = _make_user(db_session, "diary-material-admin")
    worker = Worker(name="Ana", regular_day_rate=Decimal("800"), billing_hourly_rate=Decimal("200"))
    db_session.add(worker)
    await db_session.flush()
    expense = await make_expense(
        db_session,
        amount=Decimal("500"),
        status="paid",
        description="Kabl 3x2.5",
        project_id=project.id,
        expense_date=date(2026, 7, 9),
    )

    entry = await create_entry(
        WorkDiaryEntryCreate(
            date=date(2026, 7, 10),
            project_id=project.id,
            worker_ids=[worker.id],
            description="Wiring",
            duration_hours=4,
            materials=[
                WorkDiaryMaterialCreate(description="", source="expense", expense_id=expense.id),
                WorkDiaryMaterialCreate(description="Gips sa sklada", quantity=2, unit="kg", amount=250),
            ],
        ),
        db_session,
        user,
    )

    # Описание и сумма привязанной строки подтягиваются из расхода
    assert [(m.description, m.source, m.amount) for m in entry.materials] == [
        ("Kabl 3x2.5", "expense", 500),
        ("Gips sa sklada", "stock", 250),
    ]
    assert entry.linked_material_amount == 500
    assert entry.stock_material_amount == 250
    assert entry.material_amount == 750
    assert entry.billable_amount == 4 * 200 + 750

    costs = await get_project_costs(project.id, None, None, db_session, user)
    assert costs.expenses_amount == 500
    assert costs.labor_amount == 400
    assert costs.stock_material_amount == 250
    assert costs.linked_material_amount == 500
    # Привязанный материал уже внутри expenses_amount и не прибавляется второй раз
    assert costs.total_cost_amount == 500 + 400 + 0 + 250


@pytest.mark.asyncio
async def test_work_diary_material_expense_must_match_project(db_session, make_project, make_expense):
    project = await make_project(db_session)
    other_project = await make_project(db_session, code="PR-2", name="Other")
    user = _make_user(db_session, "diary-mismatch-admin")
    worker = Worker(name="Ana", regular_day_rate=Decimal("800"))
    db_session.add(worker)
    await db_session.flush()
    foreign_expense = await make_expense(db_session, amount=Decimal("500"), status="paid", project_id=other_project.id)

    with pytest.raises(HTTPException) as exc_info:
        await create_entry(
            WorkDiaryEntryCreate(
                date=date(2026, 7, 10),
                project_id=project.id,
                worker_ids=[worker.id],
                description="Wiring",
                duration_hours=4,
                materials=[
                    WorkDiaryMaterialCreate(description="Kabl", source="expense", expense_id=foreign_expense.id)
                ],
            ),
            db_session,
            user,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_work_diary_expense_options_show_only_active_project_expenses(db_session, make_project, make_expense):
    project = await make_project(db_session)
    other_project = await make_project(db_session, code="PR-2", name="Other")
    user = _make_user(db_session, "diary-options-admin")
    visible = await make_expense(
        db_session, amount=Decimal("500"), status="paid", description="Kabl", project_id=project.id
    )
    await make_expense(db_session, amount=Decimal("100"), status="planned", project_id=project.id)
    await make_expense(db_session, amount=Decimal("200"), status="paid", source="cash_transfer", project_id=project.id)
    await make_expense(db_session, amount=Decimal("300"), status="paid", project_id=other_project.id)

    options = await list_expense_options(project.id, None, None, db_session, user)

    assert [option.id for option in options] == [visible.id]
    assert options[0].description == "Kabl"
    assert options[0].amount == 500
    assert options[0].items == []


@pytest.mark.asyncio
async def test_work_diary_expense_options_include_receipt_and_invoice_items(db_session, make_project, make_expense):
    project = await make_project(db_session)
    user = _make_user(db_session, "diary-items-admin")

    receipt_expense = await make_expense(
        db_session, amount=Decimal("2180"), status="paid", description="FARBARA", project_id=project.id
    )
    receipt = PurchaseReceipt(
        verification_url="https://suf.purs.gov.rs/v/?vl=test",
        qr_hash="hash-items-test",
        total_amount=Decimal("2180"),
        expense_id=receipt_expense.id,
    )
    db_session.add(receipt)
    await db_session.flush()
    db_session.add_all(
        [
            PurchaseReceiptItem(
                receipt_id=receipt.id,
                line_no=1,
                name="KLEMA 2X0,2-4MM2 /kom",
                quantity=Decimal("5"),
                unit_price=Decimal("100"),
                total_amount=Decimal("500"),
            ),
            PurchaseReceiptItem(
                receipt_id=receipt.id,
                line_no=2,
                name="Kabal N2XH 3x2.5 /m",
                quantity=Decimal("20"),
                unit_price=Decimal("84"),
                total_amount=Decimal("1680"),
            ),
        ]
    )

    invoice_expense = await make_expense(
        db_session, amount=Decimal("300"), status="paid", description="eFaktura", project_id=project.id
    )
    db_session.add(
        ExpenseItem(
            expense_id=invoice_expense.id,
            line_no=1,
            name="Postarina",
            quantity=Decimal("1"),
            unit_price=Decimal("300"),
            total_amount=Decimal("300"),
        )
    )
    await db_session.flush()

    options = await list_expense_options(project.id, None, None, db_session, user)
    options_by_id = {option.id: option for option in options}

    receipt_items = options_by_id[receipt_expense.id].items
    assert [item.name for item in receipt_items] == ["KLEMA 2X0,2-4MM2 /kom", "Kabal N2XH 3x2.5 /m"]
    assert receipt_items[0].unit == "kom"
    assert receipt_items[1].unit == "m"
    assert receipt_items[1].quantity == 20
    assert receipt_items[1].unit_price == 84
    assert receipt_items[1].total_amount == 1680

    invoice_items = options_by_id[invoice_expense.id].items
    assert [item.name for item in invoice_items] == ["Postarina"]
    assert invoice_items[0].unit is None


@pytest.mark.asyncio
async def test_work_diary_entry_can_be_edited(db_session, make_project):
    project = await make_project(db_session)
    user = _make_user(db_session, "diary-edit-admin")
    worker_a = Worker(name="Ana", regular_day_rate=Decimal("800"), billing_hourly_rate=Decimal("100"))
    worker_b = Worker(name="Boris", regular_day_rate=Decimal("1200"), billing_hourly_rate=Decimal("150"))
    db_session.add_all([worker_a, worker_b])
    await db_session.flush()

    created = await create_entry(
        WorkDiaryEntryCreate(
            date=date(2026, 7, 10),
            project_id=project.id,
            worker_ids=[worker_a.id],
            description="Initial work",
            start_time="07:00",
            end_time="11:00",
        ),
        db_session,
        user,
    )

    updated = await update_entry(
        created.id,
        WorkDiaryEntryUpdate(
            worker_ids=[worker_a.id, worker_b.id],
            description="Updated work",
            start_time=None,
            end_time=None,
            duration_hours=3,
            team_hourly_rate_snapshot=None,
            materials=[WorkDiaryMaterialCreate(description="Sealant", quantity=2, unit="kom", amount=90)],
        ),
        db_session,
        user,
    )

    assert updated.description == "Updated work"
    assert updated.worker_names == ["Ana", "Boris"]
    assert updated.duration_hours == 3
    assert updated.person_hours == 6
    assert updated.team_hourly_rate_snapshot == 250
    assert updated.team_billing_hourly_rate_snapshot == 250
    assert updated.billable_amount == 840
    assert [(item.description, item.quantity, item.unit, item.amount) for item in updated.materials] == [
        ("Sealant", 2, "kom", 90),
    ]


@pytest.mark.asyncio
async def test_work_diary_patch_duration_overrides_stored_times(db_session, make_project):
    project = await make_project(db_session)
    user = _make_user(db_session, "diary-duration-admin")
    worker = Worker(name="Ana", regular_day_rate=Decimal("800"))
    db_session.add(worker)
    await db_session.flush()

    created = await create_entry(
        WorkDiaryEntryCreate(
            date=date(2026, 7, 10),
            project_id=project.id,
            worker_ids=[worker.id],
            description="Timed work",
            start_time="07:00",
            end_time="15:00",
        ),
        db_session,
        user,
    )

    updated = await update_entry(
        created.id,
        WorkDiaryEntryUpdate(duration_hours=5),
        db_session,
        user,
    )

    assert updated.duration_hours == 5
    assert updated.start_time is None
    assert updated.end_time is None


def test_work_diary_payload_contract():
    fields = WorkDiaryEntryCreate.model_fields

    assert "worker_ids" in fields
    assert "worker_id" not in fields
    assert "duration_hours" in fields
    assert "person_hours" not in fields
    assert "hours" not in fields
    assert "team_hourly_rate_snapshot" in fields
    assert "team_billing_hourly_rate_snapshot" not in fields
    assert "hourly_rate_snapshot" not in fields

    with pytest.raises(ValidationError):
        WorkDiaryEntryCreate.model_validate(
            {
                "date": "2026-07-10",
                "project_id": 1,
                "worker_ids": [1],
                "description": "Old payload",
                "hours": 4,
            }
        )


def test_work_diary_material_validation():
    with pytest.raises(ValidationError):
        WorkDiaryMaterialCreate(description="Kabl", source="expense")

    with pytest.raises(ValidationError):
        WorkDiaryMaterialCreate(description="Kabl", unit="unknown")

    stock = WorkDiaryMaterialCreate(description="Kabl", source="stock", expense_id=5)
    assert stock.expense_id is None
