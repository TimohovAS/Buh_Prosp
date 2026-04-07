from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.models import PurchaseReceipt, User
from backend.receipt_service import (
    ReceiptImportError,
    assign_receipt_project,
    create_expense_from_receipt,
    get_project_receipt_purchases,
    get_receipt_expense_candidates,
    get_receipt_or_error,
    import_receipt_from_qr,
    link_receipt_to_expense,
    list_receipts,
    unlink_receipt_expense,
)
from backend.schemas import (
    ProjectPurchasesResponse,
    PurchaseReceiptAssignProjectRequest,
    PurchaseReceiptCreateExpenseRequest,
    PurchaseReceiptDetailResponse,
    PurchaseReceiptExpenseCandidateResponse,
    PurchaseReceiptImportRequest,
    PurchaseReceiptImportResponse,
    PurchaseReceiptLinkExpenseRequest,
    PurchaseReceiptResponse,
)

router = APIRouter(prefix="/receipts", tags=["receipts"])


def _serialize_receipt(receipt: PurchaseReceipt) -> PurchaseReceiptResponse:
    payload = PurchaseReceiptResponse.model_validate(receipt).model_dump()
    payload["project_name"] = getattr(receipt.project, "name", None)
    payload["project_code"] = getattr(receipt.project, "code", None)
    payload["expense_status"] = getattr(receipt.expense, "status", None)
    payload["expense_source"] = getattr(receipt.expense, "source", None)
    payload["item_count"] = len(receipt.items or [])
    return PurchaseReceiptResponse.model_validate(payload)


def _serialize_receipt_detail(receipt: PurchaseReceipt) -> PurchaseReceiptDetailResponse:
    payload = _serialize_receipt(receipt).model_dump()
    payload["items"] = receipt.items or []
    return PurchaseReceiptDetailResponse.model_validate(payload)


@router.get("", response_model=list[PurchaseReceiptResponse])
async def list_purchase_receipts(
    status: str | None = Query(None),
    project_id: int | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    items = await list_receipts(db, status=status, project_id=project_id, search=search)
    return [_serialize_receipt(item) for item in items]


@router.post("/import-from-qr", response_model=PurchaseReceiptImportResponse)
async def import_purchase_receipt(
    body: PurchaseReceiptImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        receipt, created = await import_receipt_from_qr(db, body.verification_url, current_user_id=current_user.id)
        await db.commit()
        receipt = await get_receipt_or_error(db, receipt.id)
        return PurchaseReceiptImportResponse(created=created, receipt=_serialize_receipt_detail(receipt))
    except ReceiptImportError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{receipt_id}", response_model=PurchaseReceiptDetailResponse)
async def get_purchase_receipt(
    receipt_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    try:
        receipt = await get_receipt_or_error(db, receipt_id)
        return _serialize_receipt_detail(receipt)
    except ReceiptImportError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{receipt_id}/expense-candidates", response_model=list[PurchaseReceiptExpenseCandidateResponse])
async def get_purchase_receipt_expense_candidates(
    receipt_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    try:
        candidates = await get_receipt_expense_candidates(db, receipt_id)
        return [PurchaseReceiptExpenseCandidateResponse.model_validate(item) for item in candidates]
    except ReceiptImportError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{receipt_id}/assign-project", response_model=PurchaseReceiptDetailResponse)
async def assign_purchase_receipt_project(
    receipt_id: int,
    body: PurchaseReceiptAssignProjectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        receipt = await assign_receipt_project(db, receipt_id, body.project_id)
        await db.commit()
        receipt = await get_receipt_or_error(db, receipt.id)
        return _serialize_receipt_detail(receipt)
    except ReceiptImportError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{receipt_id}/link-expense", response_model=PurchaseReceiptDetailResponse)
async def link_purchase_receipt_expense(
    receipt_id: int,
    body: PurchaseReceiptLinkExpenseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        receipt = await link_receipt_to_expense(db, receipt_id, body.expense_id)
        await db.commit()
        receipt = await get_receipt_or_error(db, receipt.id)
        return _serialize_receipt_detail(receipt)
    except ReceiptImportError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{receipt_id}/create-expense", response_model=PurchaseReceiptDetailResponse)
async def create_expense_for_purchase_receipt(
    receipt_id: int,
    body: PurchaseReceiptCreateExpenseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        receipt = await create_expense_from_receipt(
            db,
            receipt_id,
            category_id=body.category_id,
            project_id=body.project_id,
            contract_id=body.contract_id,
            description=body.description,
            note=body.note,
            payment_mode=body.payment_mode,
            current_user_id=current_user.id,
        )
        await db.commit()
        receipt = await get_receipt_or_error(db, receipt.id)
        return _serialize_receipt_detail(receipt)
    except ReceiptImportError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{receipt_id}/unlink-expense", response_model=PurchaseReceiptDetailResponse)
async def unlink_purchase_receipt(
    receipt_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        receipt = await unlink_receipt_expense(db, receipt_id)
        await db.commit()
        receipt = await get_receipt_or_error(db, receipt.id)
        return _serialize_receipt_detail(receipt)
    except ReceiptImportError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/by-project/{project_id}", response_model=ProjectPurchasesResponse)
async def list_project_purchase_receipts(
    project_id: int,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    try:
        payload = await get_project_receipt_purchases(db, project_id=project_id, from_date=from_date, to_date=to_date)
        return ProjectPurchasesResponse.model_validate(payload)
    except ReceiptImportError as exc:
        raise HTTPException(400, str(exc)) from exc
