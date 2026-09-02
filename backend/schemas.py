"""Pydantic схемы для API."""

from datetime import date, datetime
from decimal import Decimal

# Алиас для избежания конфликта имени поля date с типом date
from typing import Literal, Optional
from pydantic import (
    BaseModel as PydanticBaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

DateType = date

MAX_EMBLEM_DATA_URL_LENGTH = 350000


class BaseModel(PydanticBaseModel):
    # Decimal -> число в JSON (дефолт Pydantic v2 — строка, это сломало бы суммы).
    # Сериализатор видит только значение поля целиком: Decimal внутри list/dict
    # НЕ конвертируется — такие поля объявлять нельзя без своего сериализатора.
    @field_serializer("*", when_used="json")
    def serialize_decimal(self, value):
        if isinstance(value, Decimal):
            return float(value)
        return value


# --- User ---
class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = None
    role: str = "accountant"
    default_language: str = "sr"


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    default_language: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# --- Client ---
class ClientBase(BaseModel):
    name: str
    address: Optional[str] = None
    pib: Optional[str] = None
    maticni_broj: Optional[str] = None
    bank_accounts: list[str] = Field(default_factory=list)
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    client_type: str = "legal"
    document_language: str = "sr"


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    pib: Optional[str] = None
    maticni_broj: Optional[str] = None
    bank_accounts: Optional[list[str]] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    client_type: Optional[str] = None
    document_language: Optional[str] = None
    is_archived: Optional[bool] = None


class ClientResponse(ClientBase):
    id: int
    is_archived: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientBrief(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


# --- Project ---
class ProjectBase(BaseModel):
    code: Optional[str] = None
    name: str
    client_id: Optional[int] = None
    is_internal: Optional[bool] = False
    status: Literal["active", "completed"] = "active"
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    planned_income: Optional[Decimal] = None
    planned_expense: Optional[Decimal] = None
    notes: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    client_id: Optional[int] = None
    is_internal: Optional[bool] = None
    status: Optional[Literal["active", "completed"]] = None
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    planned_income: Optional[Decimal] = None
    planned_expense: Optional[Decimal] = None
    notes: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: int
    is_internal: Optional[bool] = False
    client_name: Optional[str] = None
    first_movement_date: Optional[DateType] = None
    last_movement_date: Optional[DateType] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ProjectBrief(BaseModel):
    id: int
    code: Optional[str] = None
    name: str

    model_config = ConfigDict(from_attributes=True)


class WorkDiaryProjectMetaBase(BaseModel):
    investor: Optional[str] = None
    permit_number: Optional[str] = None
    contractor: Optional[str] = None
    place: Optional[str] = None
    supervision: Optional[str] = None
    object_name: Optional[str] = None
    sector: Optional[str] = None
    responsible_person: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_values(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in (
            "investor",
            "permit_number",
            "contractor",
            "place",
            "supervision",
            "object_name",
            "sector",
            "responsible_person",
        ):
            if result.get(key) == "":
                result[key] = None
        return result


class WorkDiaryProjectMetaResponse(WorkDiaryProjectMetaBase):
    id: Optional[int] = None
    project_id: int
    project_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


WORK_DIARY_MATERIAL_UNITS = ("kom", "m", "m2", "m3", "kg", "t", "l", "pak", "h")


class WorkDiaryMaterialBase(BaseModel):
    description: str
    quantity: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = None
    source: Literal["stock", "expense"] = "stock"
    expense_id: Optional[int] = None
    source_item_type: Optional[Literal["expense_item", "receipt_item"]] = None
    source_item_id: Optional[int] = None
    unit_price_snapshot: Optional[float] = Field(default=None, ge=0)
    amount: float = Field(default=0, ge=0)

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_values(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in (
            "quantity",
            "unit",
            "expense_id",
            "source_item_type",
            "source_item_id",
            "unit_price_snapshot",
        ):
            if result.get(key) == "":
                result[key] = None
        return result

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value):
        if value is not None and value not in WORK_DIARY_MATERIAL_UNITS:
            raise ValueError("Unknown material unit")
        return value

    @model_validator(mode="after")
    def validate_expense_link(self):
        if self.source == "expense" and self.expense_id is None:
            raise ValueError("expense_id is required when source is 'expense'")
        if (self.source_item_type is None) != (self.source_item_id is None):
            raise ValueError("source_item_type and source_item_id must be provided together")
        if self.source_item_type is not None and self.source != "expense":
            raise ValueError("A source item can only be linked to an expense material")
        if self.source == "stock":
            self.expense_id = None
            self.source_item_type = None
            self.source_item_id = None
        return self


class WorkDiaryMaterialCreate(WorkDiaryMaterialBase):
    pass


class WorkDiaryMaterialResponse(BaseModel):
    id: int
    line_no: int
    description: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    source: str
    expense_id: Optional[int] = None
    source_item_type: Optional[str] = None
    source_item_id: Optional[int] = None
    unit_price_snapshot: Optional[float] = None
    expense_date: Optional[DateType] = None
    expense_description: Optional[str] = None
    amount: float


class WorkDiaryEntryBase(BaseModel):
    date: DateType
    project_id: int
    worker_ids: list[int] = Field(min_length=1)
    description: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_hours: Optional[float] = Field(default=None, gt=0)
    team_hourly_rate_snapshot: Optional[float] = Field(default=None, ge=0)
    # None => коэффициент из настроек предприятия
    material_billing_multiplier: Optional[float] = Field(default=None, gt=0)
    billable_amount_override: Optional[float] = Field(default=None, ge=0)
    # None => коэффициент из настроек предприятия
    overtime_multiplier: Optional[float] = Field(default=None, ge=1)
    per_diem: bool = False
    per_diem_amount: float = Field(default=0, ge=0)
    lodging_amount: float = Field(default=0, ge=0)
    food_allowance: bool = False
    food_amount: float = Field(default=0, ge=0)
    weather: Optional[str] = None
    temperature: Optional[str] = None
    note: Optional[str] = None
    materials: list[WorkDiaryMaterialCreate] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("worker_ids", mode="before")
    @classmethod
    def normalize_worker_ids(cls, value):
        if value in (None, ""):
            return []
        return list(dict.fromkeys(value))

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_values(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in (
            "duration_hours",
            "team_hourly_rate_snapshot",
            "material_billing_multiplier",
            "billable_amount_override",
            "overtime_multiplier",
            "start_time",
            "end_time",
            "weather",
            "temperature",
            "note",
        ):
            if result.get(key) == "":
                result[key] = None
        return result


class WorkDiaryEntryCreate(WorkDiaryEntryBase):
    pass


class WorkDiaryEntryUpdate(BaseModel):
    date: Optional[DateType] = None
    project_id: Optional[int] = None
    worker_ids: Optional[list[int]] = Field(default=None, min_length=1)
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_hours: Optional[float] = Field(default=None, gt=0)
    team_hourly_rate_snapshot: Optional[float] = Field(default=None, ge=0)
    material_billing_multiplier: Optional[float] = Field(default=None, gt=0)
    billable_amount_override: Optional[float] = Field(default=None, ge=0)
    overtime_multiplier: Optional[float] = Field(default=None, ge=1)
    per_diem: Optional[bool] = None
    per_diem_amount: Optional[float] = Field(default=None, ge=0)
    lodging_amount: Optional[float] = Field(default=None, ge=0)
    food_allowance: Optional[bool] = None
    food_amount: Optional[float] = Field(default=None, ge=0)
    weather: Optional[str] = None
    temperature: Optional[str] = None
    note: Optional[str] = None
    materials: Optional[list[WorkDiaryMaterialCreate]] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("worker_ids", mode="before")
    @classmethod
    def normalize_worker_ids(cls, value):
        if value is None:
            return None
        if value == "":
            return []
        return list(dict.fromkeys(value))

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_values(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in (
            "project_id",
            "duration_hours",
            "team_hourly_rate_snapshot",
            "material_billing_multiplier",
            "billable_amount_override",
            "overtime_multiplier",
            "start_time",
            "end_time",
            "weather",
            "temperature",
            "note",
        ):
            if result.get(key) == "":
                result[key] = None
        return result


class WorkDiaryInvoiceLinkResponse(BaseModel):
    income_id: int
    invoice_number: str
    invoice_status: str
    amount: float


class WorkDiaryEntryResponse(BaseModel):
    id: int
    date: DateType
    project_id: int
    project_name: Optional[str] = None
    worker_ids: list[int] = Field(default_factory=list)
    worker_names: list[str] = Field(default_factory=list)
    description: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_hours: float
    person_hours: float
    regular_person_hours: float
    overtime_person_hours: float
    team_hourly_rate_snapshot: float
    team_billing_hourly_rate_snapshot: float
    material_billing_multiplier: float
    billable_amount_override: Optional[float] = None
    overtime_multiplier: float
    labor_amount: float
    payout_amount: float
    allowance_amount: float
    material_amount: float
    billable_material_amount: float
    stock_material_amount: float
    linked_material_amount: float
    total_cost_amount: float
    calculated_billable_amount: float
    billable_amount: float
    invoiced_amount: float
    remaining_billable_amount: float
    billing_status: Literal["not_invoiced", "partially_invoiced", "invoiced"]
    invoice_links: list[WorkDiaryInvoiceLinkResponse] = Field(default_factory=list)
    per_diem: bool
    per_diem_amount: float
    lodging_amount: float
    food_allowance: bool
    food_amount: float
    weather: Optional[str] = None
    temperature: Optional[str] = None
    note: Optional[str] = None
    materials: list[WorkDiaryMaterialResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None


class WorkDiarySummaryResponse(BaseModel):
    entries_count: int
    days_count: int
    workers_count: int
    person_hours: float
    regular_person_hours: float
    overtime_person_hours: float
    labor_amount: float
    payout_amount: float
    allowance_amount: float
    material_amount: float
    billable_material_amount: float
    stock_material_amount: float
    linked_material_amount: float
    total_cost_amount: float
    billable_amount: float
    invoiced_amount: float
    remaining_billable_amount: float


class WorkDiaryProposalExportRequest(BaseModel):
    entry_ids: list[int] = Field(min_length=1)

    @field_validator("entry_ids")
    @classmethod
    def validate_entry_ids(cls, value):
        normalized = list(dict.fromkeys(value))
        if any(entry_id <= 0 for entry_id in normalized):
            raise ValueError("entry_ids must contain positive identifiers")
        return normalized


class WorkDiaryInvoiceLineCreate(BaseModel):
    entry_id: int
    name: str
    amount: Decimal = Field(gt=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Invoice line name is required")
        return normalized


class WorkDiaryInvoiceCreate(BaseModel):
    issued_date: DateType
    due_date: Optional[DateType] = None
    invoice_number: Optional[str] = None
    contract_id: Optional[int] = None
    contract_payment_type: Optional[Literal["advance", "intermediate", "closing"]] = None
    description: Optional[str] = None
    note: Optional[str] = None
    lines: list[WorkDiaryInvoiceLineCreate] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_values(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in ("due_date", "invoice_number", "contract_id", "contract_payment_type", "description", "note"):
            if result.get(key) == "":
                result[key] = None
        return result

    @model_validator(mode="after")
    def validate_unique_entries(self):
        entry_ids = [line.entry_id for line in self.lines]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("Each work diary entry can appear only once in an invoice")
        if self.due_date is not None and self.due_date < self.issued_date:
            raise ValueError("Due date cannot be before invoice date")
        if self.contract_id is None:
            self.contract_payment_type = None
        return self


class WorkDiaryInvoiceCreateResponse(BaseModel):
    income_id: int
    invoice_number: str
    amount_rsd: Decimal
    entries_count: int


class WorkDiaryExpenseItemOption(BaseModel):
    """Позиция чека или фактуры внутри расхода — для автозаполнения строки материалов."""

    source_item_type: Literal["expense_item", "receipt_item"]
    source_item_id: int
    name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    total_amount: float
    used_quantity: float = 0
    remaining_quantity: Optional[float] = None
    used_amount: float = 0
    remaining_amount: float = 0
    is_used: bool = False


class WorkDiaryExpenseOptionResponse(BaseModel):
    """Расход проекта, доступный для привязки строки материалов."""

    id: int
    date: DateType
    description: str
    amount: float
    source: str
    status: str
    used_amount: float = 0
    remaining_amount: float = 0
    items: list[WorkDiaryExpenseItemOption] = Field(default_factory=list)


class WorkDiaryProjectCostsResponse(BaseModel):
    """Затраты по объекту: расходы из модуля Расходы + труд и складские материалы из дневника."""

    project_id: int
    project_name: Optional[str] = None
    date_from: Optional[DateType] = None
    date_to: Optional[DateType] = None
    entries_count: int
    expenses_amount: float
    labor_amount: float
    allowance_amount: float
    stock_material_amount: float
    # Справочно: материалы дневника, уже учтенные внутри expenses_amount
    linked_material_amount: float
    total_cost_amount: float
    billable_amount: float


# --- Income ---
class IncomeItemBase(BaseModel):
    name: str
    quantity: Decimal = Decimal("1")
    unit: str = "kom"
    unit_price: Decimal = Decimal("0.00")
    total_amount: Optional[Decimal] = None
    tax_category: str = "SS"
    tax_rate: Decimal = Decimal("0.00")
    note: Optional[str] = None

    @field_validator("quantity", "unit_price", "total_amount", "tax_rate", mode="before")
    @classmethod
    def empty_decimal_to_none(cls, value):
        if value == "":
            return None
        return value


class IncomeItemCreate(IncomeItemBase):
    pass


class IncomeItemResponse(IncomeItemBase):
    id: int
    income_id: int
    line_no: int
    total_amount: Decimal = Decimal("0.00")

    model_config = ConfigDict(from_attributes=True)


class IncomeItemSuggestion(BaseModel):
    source: str
    match_scope: str = "global"
    name: str
    unit: str = "kom"
    quantity: Decimal = Decimal("1")
    unit_price: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    tax_category: str = "SS"
    tax_rate: Decimal = Decimal("0.00")
    invoice_id: Optional[int] = None
    invoice_number: Optional[str] = None
    issued_date: Optional[DateType] = None
    contract_id: Optional[int] = None
    contract_number: Optional[str] = None
    client_name: Optional[str] = None
    project_name: Optional[str] = None


class IncomeBase(BaseModel):
    issued_date: DateType = Field(serialization_alias="date")  # дата счёта (в БД: date)
    due_date: Optional[DateType] = None  # Valuta / срок оплаты
    invoice_number: str
    invoice_year: Optional[int] = None
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    contract_id: Optional[int] = None
    contract_payment_type: Optional[str] = None  # advance, intermediate, closing
    description: Optional[str] = None
    amount_rsd: Decimal
    currency: str = "RSD"
    exchange_rate: float = 1.0
    status: Optional[str] = None  # issued | partial | paid | cancelled
    paid_date: Optional[DateType] = None
    project_id: Optional[int] = None
    income_type: Optional[str] = None  # advance | intermediate | final | other
    efaktura_contract_number: Optional[str] = None
    efaktura_order_reference: Optional[str] = None
    efaktura_framework_agreement_number: Optional[str] = None
    efaktura_object_code: Optional[str] = None
    efaktura_buyer_reference: Optional[str] = None
    efaktura_payment_reference: Optional[str] = None
    efaktura_payment_model: Optional[str] = None
    note: Optional[str] = None


class IncomeCreate(IncomeBase):
    invoice_number: Optional[str] = None  # пусто = присвоить автоматически
    invoice_year: Optional[int] = None
    issued_date: Optional[DateType] = None  # при пусто берётся date (backward compat)
    status: Optional[str] = None
    paid_date: Optional[DateType] = None
    project_id: Optional[int] = None
    income_type: Optional[str] = None
    items: Optional[list[IncomeItemCreate]] = None

    @model_validator(mode="before")
    @classmethod
    def date_to_issued_date(cls, data):
        if isinstance(data, dict) and data.get("issued_date") is None and data.get("date") is not None:
            data = dict(data)
            data["issued_date"] = data.pop("date", None)
        return data

    @field_validator(
        "client_id",
        "contract_id",
        "contract_payment_type",
        "project_id",
        "efaktura_contract_number",
        "efaktura_order_reference",
        "efaktura_framework_agreement_number",
        "efaktura_object_code",
        "efaktura_buyer_reference",
        "efaktura_payment_reference",
        "efaktura_payment_model",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v


class IncomeUpdate(BaseModel):
    issued_date: Optional[DateType] = None
    due_date: Optional[DateType] = None
    invoice_year: Optional[int] = None
    invoice_number: Optional[str] = None
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    contract_id: Optional[int] = None
    contract_payment_type: Optional[str] = None
    description: Optional[str] = None
    amount_rsd: Optional[Decimal] = None
    is_paid: Optional[bool] = None
    paid_date: Optional[DateType] = None
    project_id: Optional[int] = None
    efaktura_contract_number: Optional[str] = None
    efaktura_order_reference: Optional[str] = None
    efaktura_framework_agreement_number: Optional[str] = None
    efaktura_object_code: Optional[str] = None
    efaktura_buyer_reference: Optional[str] = None
    efaktura_payment_reference: Optional[str] = None
    efaktura_payment_model: Optional[str] = None
    note: Optional[str] = None
    items: Optional[list[IncomeItemCreate]] = None

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        if result.get("issued_date") is None and result.get("date") is not None:
            result["issued_date"] = result.pop("date", None)
        for key in ("client_id", "contract_id", "project_id"):
            if key in result and (result[key] == "" or result[key] is None):
                result[key] = None
        if "invoice_year" in result and (result["invoice_year"] == "" or result["invoice_year"] is None):
            result["invoice_year"] = None
        if "contract_payment_type" in result and (
            result["contract_payment_type"] == "" or result["contract_payment_type"] is None
        ):
            result["contract_payment_type"] = None
        for key in (
            "efaktura_contract_number",
            "efaktura_order_reference",
            "efaktura_framework_agreement_number",
            "efaktura_object_code",
            "efaktura_buyer_reference",
            "efaktura_payment_reference",
            "efaktura_payment_model",
        ):
            if key in result:
                result[key] = str(result[key]).strip() if result[key] is not None else None
                if not result[key]:
                    result[key] = None
        if result.get("contract_id") is None:
            result["contract_payment_type"] = None
        return result


class IncomeMarkPaid(BaseModel):
    paid_date: DateType


class BulkAssignProject(BaseModel):
    """Массовое назначение проекта: ids + project_id (null = снять проект)."""

    ids: list[int]
    project_id: Optional[int] = None


class IncomeResponse(IncomeBase):
    id: int
    is_paid: bool
    paid_amount: Decimal = Decimal("0.00")
    created_at: datetime
    contract_number: Optional[str] = None
    items: list[IncomeItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class IncomePaymentTransactionResponse(BaseModel):
    id: int
    date: DateType
    amount: Decimal
    transaction_amount: Optional[Decimal] = None
    currency: str = "RSD"
    counterparty_name: Optional[str] = None
    purpose: Optional[str] = None
    bank_reference: Optional[str] = None
    project_id: Optional[int] = None
    link_kind: str = "direct"
    allocation_count: int = 1
    can_unlink: bool = True

    model_config = ConfigDict(from_attributes=True)


class ProjectMovementItemResponse(BaseModel):
    row_key: str
    source_id: Optional[int] = None
    receipt_id: Optional[int] = None
    date: DateType
    direction: Literal["in", "out"]
    movement_type: Literal["income", "expense"]
    source_kind: str
    document_number: Optional[str] = None
    counterparty_name: Optional[str] = None
    description: Optional[str] = None
    amount: Decimal
    status: Optional[str] = None


class ProjectMovementsResponse(BaseModel):
    project_id: int
    project_name: Optional[str] = None
    mode: Literal["accrual", "cash"]
    from_date: DateType
    to_date: DateType
    items: list[ProjectMovementItemResponse] = Field(default_factory=list)


class PurchaseReceiptItemResponse(BaseModel):
    id: int
    line_no: int
    gtin: Optional[str] = None
    name: str
    quantity: Decimal = Decimal("0.00")
    unit_price: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    label: Optional[str] = None
    label_rate: Optional[float] = None
    tax_base_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class PurchaseReceiptBase(BaseModel):
    verification_url: str
    invoice_number: Optional[str] = None
    seller_name: Optional[str] = None
    seller_tax_id: Optional[str] = None
    seller_address: Optional[str] = None
    seller_city: Optional[str] = None
    receipt_datetime: Optional[datetime] = None
    payment_type: Optional[str] = None
    payment_kind: str = "unknown"
    total_amount: Decimal = Decimal("0.00")
    currency: str = "RSD"
    is_valid: bool = True
    status: str = "new"
    project_id: Optional[int] = None
    category_id: Optional[int] = None
    expense_id: Optional[int] = None
    bank_transaction_id: Optional[int] = None
    cash_entry_id: Optional[int] = None


class PurchaseReceiptResponse(PurchaseReceiptBase):
    id: int
    project_name: Optional[str] = None
    project_code: Optional[str] = None
    expense_status: Optional[str] = None
    expense_source: Optional[str] = None
    expense_amount: Optional[Decimal] = None
    amount_delta: Optional[Decimal] = None
    amount_delta_abs: Optional[Decimal] = None
    matches_amount: bool = False
    item_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseReceiptDetailResponse(PurchaseReceiptResponse):
    items: list[PurchaseReceiptItemResponse] = Field(default_factory=list)


class PurchaseReceiptImportRequest(BaseModel):
    verification_url: str


class PurchaseReceiptImportResponse(BaseModel):
    created: bool
    receipt: PurchaseReceiptDetailResponse


class PurchaseReceiptAssignProjectRequest(BaseModel):
    project_id: Optional[int] = None

    @field_validator("project_id", mode="before")
    @classmethod
    def empty_project_to_none(cls, value):
        if value == "" or value is None:
            return None
        return value


class PurchaseReceiptLinkExpenseRequest(BaseModel):
    expense_id: int


class PurchaseReceiptCreateExpenseRequest(BaseModel):
    category_id: Optional[int] = None
    project_id: Optional[int] = None
    contract_id: Optional[int] = None
    description: Optional[str] = None
    note: Optional[str] = None
    payment_mode: Literal["auto", "bank", "cash"] = "auto"

    @field_validator("category_id", "project_id", "contract_id", mode="before")
    @classmethod
    def empty_link_to_none(cls, value):
        if value == "" or value is None:
            return None
        return value


class PurchaseReceiptExpenseCandidateResponse(BaseModel):
    id: int
    date: DateType
    description: str
    amount: Decimal
    currency: str = "RSD"
    status: Optional[str] = None
    source: Optional[str] = None
    category_id: Optional[int] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    project_code: Optional[str] = None
    contract_id: Optional[int] = None
    contract_number: Optional[str] = None
    bank_reference: Optional[str] = None
    amount_delta: Decimal = Decimal("0.00")
    amount_delta_abs: Decimal = Decimal("0.00")
    matches_amount: bool = False
    score: Optional[int] = None


class ProjectPurchaseItemResponse(BaseModel):
    receipt_id: int
    receipt_datetime: Optional[datetime] = None
    seller_name: Optional[str] = None
    invoice_number: Optional[str] = None
    payment_kind: str = "unknown"
    expense_id: Optional[int] = None
    expense_status: Optional[str] = None
    item_id: int
    item_name: str
    quantity: Decimal = Decimal("0.00")
    unit_price: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")


class ProjectPurchasesResponse(BaseModel):
    project_id: int
    project_name: Optional[str] = None
    from_date: DateType
    to_date: DateType
    items: list[ProjectPurchaseItemResponse] = Field(default_factory=list)


class IncomePaymentDetailsResponse(BaseModel):
    income_id: int
    status: str
    amount_rsd: Decimal
    paid_amount: Decimal = Decimal("0.00")
    paid_date: Optional[DateType] = None
    linked_total: Decimal = Decimal("0.00")
    manual_paid_amount: Decimal = Decimal("0.00")
    manual_paid_date: Optional[DateType] = None
    has_manual_payment: bool = False
    linked_transactions: list[IncomePaymentTransactionResponse] = Field(default_factory=list)


# --- Contract ---
class ContractItemBase(BaseModel):
    description: str
    quantity: float = 1
    unit: str = "шт"
    price: Decimal = Decimal("0.00")


class ContractItemCreate(ContractItemBase):
    pass


class ContractItemResponse(ContractItemBase):
    id: int
    contract_id: int
    amount: Decimal
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ContractBase(BaseModel):
    number: str
    date: DateType
    client_id: int
    project_id: Optional[int] = None
    contract_type: str = "service"
    subject: Optional[str] = None
    amount: Decimal = Decimal("0.00")
    currency: str = "RSD"
    validity_start: Optional[DateType] = None
    validity_end: Optional[DateType] = None
    status: str = "active"
    note: Optional[str] = None


class ContractCreate(ContractBase):
    items: Optional[list[ContractItemCreate]] = None


class ContractUpdate(BaseModel):
    number: Optional[str] = None
    date: Optional[DateType] = None
    client_id: Optional[int] = None
    project_id: Optional[int] = None
    contract_type: Optional[str] = None
    subject: Optional[str] = None
    amount: Optional[Decimal] = None
    validity_start: Optional[DateType] = None
    validity_end: Optional[DateType] = None
    status: Optional[str] = None
    note: Optional[str] = None
    items: Optional[list[ContractItemCreate]] = None


class ContractResponse(ContractBase):
    id: int
    created_at: datetime
    client_name: Optional[str] = None
    items: Optional[list[ContractItemResponse]] = None
    # Суммы по типам платежей (аванс, промежуточные, закрывающий)
    advance_sum: Decimal = Decimal("0.00")
    intermediate_sum: Decimal = Decimal("0.00")
    closing_sum: Decimal = Decimal("0.00")
    total_received: Decimal = Decimal("0.00")
    total_expenses: Decimal = Decimal("0.00")
    profit: Decimal = Decimal("0.00")

    model_config = ConfigDict(from_attributes=True)


# --- Enterprise ---
class EnterpriseBase(BaseModel):
    name: str
    address: Optional[str] = None
    pib: Optional[str] = None
    maticni_broj: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_swift: Optional[str] = None
    main_activity_code: Optional[str] = None
    opening_cash_balance: Optional[Decimal] = Decimal("0.00")
    opening_cash_date: Optional[DateType] = None
    emblem_data_url: Optional[str] = None
    # Закон о раде РС: надбавка за сверхурочные минимум +26% => коэффициент не ниже 1.26
    work_diary_overtime_multiplier: Optional[Decimal] = Field(default=Decimal("1.26"), ge=1)
    work_diary_material_billing_multiplier: Decimal = Field(default=Decimal("1.2"), gt=0)

    @field_validator("emblem_data_url", mode="before")
    @classmethod
    def validate_emblem_data_url(cls, value):
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise ValueError("Enterprise emblem must be an image data URL")
        normalized = value.strip()
        if not normalized.startswith("data:image/"):
            raise ValueError("Enterprise emblem must be an image data URL")
        if len(normalized) > MAX_EMBLEM_DATA_URL_LENGTH:
            raise ValueError("Enterprise emblem image is too large")
        return normalized


class EnterpriseUpdate(EnterpriseBase):
    name: Optional[str] = None


class EnterpriseResponse(EnterpriseBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EnterpriseBrandResponse(BaseModel):
    name: Optional[str] = None
    emblem_data_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EfakturaSettingsBase(BaseModel):
    efaktura_enabled: bool = False
    efaktura_api_base_url: Optional[str] = None
    efaktura_api_key: Optional[str] = None
    efaktura_api_key_header: str = "ApiKey"
    efaktura_api_key_prefix: Optional[str] = ""
    efaktura_sync_incoming: bool = True
    efaktura_sync_outgoing: bool = True
    efaktura_sync_lookback_days: int = 30
    efaktura_incoming_list_path: Optional[str] = None
    efaktura_incoming_document_path: Optional[str] = None
    efaktura_outgoing_list_path: Optional[str] = None
    efaktura_outgoing_document_path: Optional[str] = None
    efaktura_save_pdf: bool = False
    efaktura_incoming_pdf_path: Optional[str] = None
    efaktura_outgoing_pdf_path: Optional[str] = None


class EfakturaSettingsUpdate(EfakturaSettingsBase):
    pass


class EfakturaSettingsResponse(EfakturaSettingsBase):
    pass


class EfakturaImportHistoryItem(BaseModel):
    id: int
    document_key: str
    external_id: Optional[str] = None
    direction: str
    invoice_number: str
    issued_date: DateType
    amount_rsd: Decimal
    supplier_name: Optional[str] = None
    supplier_pib: Optional[str] = None
    customer_name: Optional[str] = None
    customer_pib: Optional[str] = None
    imported_as: str
    imported_record_id: int
    source: str
    file_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EfakturaImportSummary(BaseModel):
    file_name: Optional[str] = None
    document_type: Optional[str] = None
    income_id: Optional[int] = None
    expense_id: Optional[int] = None
    invoice_number: Optional[str] = None
    counterparty_name: Optional[str] = None
    reason: Optional[str] = None
    error: Optional[str] = None


class EfakturaPdfDownload(BaseModel):
    file_name: str
    content_type: str = "application/pdf"
    content_base64: str


class EfakturaImportResult(BaseModel):
    created_count: int = 0
    created_income_count: int = 0
    created_expense_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    pdf_download_count: int = 0
    download_error_count: int = 0
    created: list[EfakturaImportSummary] = Field(default_factory=list)
    skipped: list[EfakturaImportSummary] = Field(default_factory=list)
    errors: list[EfakturaImportSummary] = Field(default_factory=list)
    download_errors: list[EfakturaImportSummary] = Field(default_factory=list)
    pdf_downloads: list[EfakturaPdfDownload] = Field(default_factory=list)


class EfakturaSyncResponse(EfakturaImportResult):
    fetched_count: int = 0


# --- PaymentType, YearDecision, MonthlyObligation (ТЗ: Обязательные платежи) ---
class PaymentTypeResponse(BaseModel):
    id: int
    code: str
    name_sr: str
    name_ru: Optional[str] = None
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class YearDecisionBase(BaseModel):
    year: int
    payment_type_id: int
    period_start: DateType
    period_end: DateType
    monthly_amount: Decimal
    base_amount: Optional[Decimal] = None
    rate_percent: Optional[float] = None
    recipient_name: str = "Пореска управа Републике Србије"
    recipient_account: str
    sifra_placanja: str = "253"
    model: str = "97"
    poziv_na_broj: str
    poziv_na_broj_next: Optional[str] = None
    payment_purpose: str
    currency: str = "RSD"
    is_provisional: bool = False


class YearDecisionCreate(YearDecisionBase):
    pass


class YearDecisionUpdate(BaseModel):
    period_start: Optional[DateType] = None
    period_end: Optional[DateType] = None
    monthly_amount: Optional[Decimal] = None
    base_amount: Optional[Decimal] = None
    rate_percent: Optional[float] = None
    recipient_name: Optional[str] = None
    recipient_account: Optional[str] = None
    sifra_placanja: Optional[str] = None
    model: Optional[str] = None
    poziv_na_broj: Optional[str] = None
    poziv_na_broj_next: Optional[str] = None
    payment_purpose: Optional[str] = None
    is_provisional: Optional[bool] = None
    is_active: Optional[bool] = None


class YearDecisionResponse(YearDecisionBase):
    id: int
    is_active: bool = True
    payment_type_code: Optional[str] = None
    payment_type_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MonthlyObligationResponse(BaseModel):
    id: int
    year: int
    month: int
    payment_type_id: int
    payment_type_code: Optional[str] = None
    payment_type_name: Optional[str] = None
    amount: Decimal
    deadline: str
    status: str
    paid_date: Optional[DateType] = None
    payment_reference: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ObligationMarkPaid(BaseModel):
    paid_date: DateType
    payment_reference: Optional[str] = None


class IPSQRData(BaseModel):
    """Данные для IPS QR (NBS)."""

    payer: str
    recipient: str
    account: str
    amount: Decimal
    currency: str
    purpose: str
    model: str
    reference: str
    payload: str  # строка NBS IPS QR (K:PR|V:01|...)
    qr_png: str  # data-URL PNG с QR-кодом


# --- ContributionRates ---
class ContributionRatesBase(BaseModel):
    year: int
    tax_amount: Decimal = Decimal("0.00")
    pio_amount: Decimal = Decimal("0.00")
    health_amount: Decimal = Decimal("0.00")
    unemployment_amount: Decimal = Decimal("0.00")
    pay_order_number: Optional[str] = None


class ContributionRatesCreate(ContributionRatesBase):
    pass


class ContributionRatesResponse(ContributionRatesBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# --- Payment ---
class PaymentBase(BaseModel):
    year: int
    month: int
    tax_amount: Decimal = Decimal("0.00")
    pio_amount: Decimal = Decimal("0.00")
    health_amount: Decimal = Decimal("0.00")
    unemployment_amount: Decimal = Decimal("0.00")


class PaymentCreate(PaymentBase):
    rates_id: Optional[int] = None


class PaymentUpdate(BaseModel):
    is_paid: Optional[bool] = None
    paid_date: Optional[DateType] = None
    payment_reference: Optional[str] = None


class PaymentResponse(PaymentBase):
    id: int
    total_amount: Decimal
    is_paid: bool
    paid_date: Optional[DateType] = None
    payment_reference: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# --- Dashboard / Stats ---
class IncomeLimitStatus(BaseModel):
    year_income: Decimal
    income_12m: Decimal
    limit_6m: int
    limit_8m: int
    percent_6m: float
    percent_8m: float
    warning_6m: bool
    warning_8m: bool
    exceeded_6m: bool
    exceeded_8m: bool


class FinanceLimitsResponse(BaseModel):
    annual_total: Decimal
    annual_limit: int
    annual_percent: float
    rolling_12_total: Decimal
    vat_limit: int
    vat_percent: float
    average_monthly_income: Decimal
    forecast_year_end: Decimal
    estimated_limit_date: Optional[str] = None
    risk: str


class FinancePnlMonthItem(BaseModel):
    month: int
    revenue: Decimal
    expenses: Decimal
    taxes: Decimal
    profit: Decimal


class FinancePnlTotals(BaseModel):
    revenue: Decimal
    expenses: Decimal
    taxes: Decimal
    profit: Decimal


class FinancePnlResponse(BaseModel):
    year: int
    items: list[FinancePnlMonthItem] = Field(default_factory=list)
    totals: FinancePnlTotals


class UpcomingObligationItem(BaseModel):
    """Неоплаченное обязательство для предупреждения на дашборде."""

    id: int
    payment_type_name: str
    amount: Decimal
    deadline: str  # YYYY-MM-DD
    status: str  # overdue | upcoming
    days_until: int  # отрицательное если просрочено


class UpcomingPlannedItem(BaseModel):
    """Просроченный или приближающийся планируемый расход."""

    planned_expense_id: int
    name: str
    amount: Decimal
    currency: str
    due_date: str
    status: str  # overdue | upcoming
    days_until: int


class DashboardIncomingInvoiceItem(BaseModel):
    """Неоплаченная входящая фактура для блока кредиторки на панели."""

    id: int
    invoice_number: str
    counterparty_name: str
    date: str  # YYYY-MM-DD
    remaining: Decimal


class DashboardTripSettlementItem(BaseModel):
    payout_id: int
    worker_name: str
    remaining_amount: Decimal
    period_start: Optional[str] = None
    period_end: str
    days_until: int


class DashboardStats(BaseModel):
    year_income: Decimal
    month_income: Decimal
    year_expenses: Decimal
    month_expenses: Decimal
    balance_month: Decimal  # month_income - month_expenses
    balance_year: Decimal  # year_income - year_expenses
    balance_all_time: Decimal
    available_bank_balance: Decimal = Decimal("0")
    pending_cash_withdrawal_total: Decimal = Decimal("0")
    available_money_now: Decimal = Decimal("0")
    financial_result_all_time: Decimal
    cash_register_balance: Decimal  # текущий остаток наличных в кассе
    planned_expenses_until_month_end: Decimal  # планируемые расходы + обязательные платежи до конца месяца
    planned_expenses_only_until_month_end: Decimal = Decimal("0")
    trip_settlement_remaining_total: Decimal = Decimal("0")
    trip_settlement_open_count: int = 0
    trip_settlement_until_month_end: Decimal = Decimal("0")
    open_trip_settlements: list[DashboardTripSettlementItem] = Field(default_factory=list)
    income_limit_status: IncomeLimitStatus
    unpaid_payments_count: int
    upcoming_payment_date: Optional[str] = None
    upcoming_unpaid_obligations: list[UpcomingObligationItem] = []
    upcoming_planned_expenses: list[UpcomingPlannedItem] = []
    unpaid_incoming_invoices: list[DashboardIncomingInvoiceItem] = []
    unpaid_incoming_total: Decimal = Decimal("0")


class PendingLinkCountsResponse(BaseModel):
    bank_unmatched_count: int = 0
    incoming_invoices_pending_count: int = 0


# --- Expense ---
class ExpenseBase(BaseModel):
    date: DateType
    description: str
    amount: Decimal
    currency: str = "RSD"
    category: Optional[str] = None
    paid_date: Optional[DateType] = None
    status: Optional[str] = None  # planned | paid | reversed
    is_tax_related: Optional[bool] = None
    project_id: Optional[int] = None
    contract_id: Optional[int] = None
    category_id: Optional[int] = None
    source: Optional[str] = None  # manual | planned | obligation | bank_import | cash | cash_transfer
    reversal_of_id: Optional[int] = None
    bank_reference: Optional[str] = None  # Номер платёжки / ID transakcije
    note: Optional[str] = None

    @field_validator("project_id", "contract_id", "category_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, value):
        if value == "" or value is None:
            return None
        return value


class ExpenseItemCreate(BaseModel):
    name: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    total_amount: Decimal = Decimal("0.00")
    note: Optional[str] = None


class ExpenseItemResponse(ExpenseItemCreate):
    id: int
    line_no: int

    model_config = ConfigDict(from_attributes=True)


class ExpenseCreate(ExpenseBase):
    paid_date: Optional[DateType] = None
    items: list[ExpenseItemCreate] = Field(default_factory=list)


class ExpenseReverseRequest(BaseModel):
    date: Optional[DateType] = None
    comment: Optional[str] = None


class ExpenseHardDeleteRequest(BaseModel):
    ids: list[int]


class ExpenseUpdate(BaseModel):
    date: Optional[DateType] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    paid_date: Optional[DateType] = None
    project_id: Optional[int] = None
    contract_id: Optional[int] = None
    category_id: Optional[int] = None
    note: Optional[str] = None
    items: Optional[list[ExpenseItemCreate]] = None

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in ("project_id", "contract_id", "category_id"):
            if key in result and (result[key] == "" or result[key] is None):
                result[key] = None
        return result


class ExpenseResponse(ExpenseBase):
    id: int
    category_id: Optional[int] = None
    reversed_expense_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseDetailResponse(ExpenseResponse):
    receipt: Optional[PurchaseReceiptDetailResponse] = None
    items: list[ExpenseItemResponse] = Field(default_factory=list)


# --- PlannedExpense (Планируемые расходы) ---


class ExpenseDuplicateItem(BaseModel):
    id: int
    date: DateType
    description: str
    amount: Decimal
    bank_reference: Optional[str] = None
    project_id: Optional[int] = None
    contract_id: Optional[int] = None
    category_id: Optional[int] = None
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExpenseDuplicateGroup(BaseModel):
    reason: str
    amount: Decimal
    payment_reference: Optional[str] = None
    description: Optional[str] = None
    item_count: int
    items: list[ExpenseDuplicateItem] = Field(default_factory=list)


class ExpenseMergeRequest(BaseModel):
    keep_id: int
    merge_ids: list[int]


class PlannedExpenseBase(BaseModel):
    name: str
    description: Optional[str] = None
    amount: Decimal
    currency: str = "RSD"
    category: Optional[str] = None
    category_id: Optional[int] = None
    project_id: Optional[int] = None
    worker_id: Optional[int] = None
    period: Literal["once", "weekly", "monthly", "quarterly", "yearly"] = "once"
    payment_day: Optional[int] = None  # 1-31 для monthly/quarterly/yearly
    payment_day_of_week: Optional[int] = None  # 0-6 для weekly (0=пн)
    start_date: DateType
    end_date: Optional[DateType] = None
    reminder_days: int = 3
    is_active: bool = True
    note: Optional[str] = None

    @field_validator("project_id", "category_id", "worker_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, value):
        if value == "" or value is None:
            return None
        return value


class PlannedExpenseCreate(PlannedExpenseBase):
    pass


class PlannedExpenseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    category_id: Optional[int] = None
    project_id: Optional[int] = None
    worker_id: Optional[int] = None
    period: Optional[Literal["once", "weekly", "monthly", "quarterly", "yearly"]] = None
    payment_day: Optional[int] = None
    payment_day_of_week: Optional[int] = None
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    reminder_days: Optional[int] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in ("project_id", "category_id", "worker_id"):
            if key in result and (result[key] == "" or result[key] is None):
                result[key] = None
        return result


class PlannedExpenseResponse(PlannedExpenseBase):
    id: int
    category_id: Optional[int] = None
    project_id: Optional[int] = None
    worker_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UpcomingPaymentItem(BaseModel):
    planned_expense_id: int
    name: str
    amount: Decimal
    currency: str
    due_date: str  # YYYY-MM-DD
    reminder_days: int
    is_paid: bool = False
    worker_id: Optional[int] = None
    worker_payout_id: Optional[int] = None


class PlannedExpenseMarkPaid(BaseModel):
    planned_expense_id: int
    due_date: DateType
    paid_date: DateType
    note: Optional[str] = None


class PlannedExpenseUnmarkPaid(BaseModel):
    planned_expense_id: int
    due_date: DateType


# --- BankTransaction ---
class BankTransactionBase(BaseModel):
    date: DateType
    amount: Decimal
    direction: str  # in | out
    currency: str = "RSD"
    counterparty_name: Optional[str] = None
    purpose: Optional[str] = None
    bank_reference: Optional[str] = None
    status: str = "unmatched"  # unmatched | matched | ignored
    matched_type: Optional[str] = None  # income | expense | obligation | cash
    matched_id: Optional[int] = None
    project_id: Optional[int] = None
    raw_json: Optional[str] = None


class BankTransactionCreate(BankTransactionBase):
    pass


class BankTransactionResponse(BankTransactionBase):
    id: int
    created_at: datetime
    allocation_count: int = 0
    allocated_amount: Decimal = Decimal("0.00")
    allocation_remaining: Decimal = Decimal("0.00")
    loan_id: Optional[int] = None
    loan_type: Optional[str] = None
    loan_movement_type: Optional[str] = None
    loan_outstanding_amount: Optional[Decimal] = None
    loan_counterparty_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BankTransactionBulkAssignProject(BaseModel):
    ids: list[int]
    project_id: Optional[int] = None


class CashEntryResponse(BaseModel):
    id: int
    date: DateType
    direction: str
    amount: Decimal
    currency: str = "RSD"
    description: str
    entry_type: str
    note: Optional[str] = None
    bank_transaction_id: Optional[int] = None
    expense_id: Optional[int] = None
    worker_payout_id: Optional[int] = None
    worker_payout_type: Optional[str] = None
    worker_payout_worker_name: Optional[str] = None
    worker_payout_period_start: Optional[DateType] = None
    worker_payout_period_end: Optional[DateType] = None
    worker_payout_gross_amount: Optional[Decimal] = None
    worker_payout_remaining_amount: Optional[Decimal] = None
    bank_reference: Optional[str] = None
    counterparty_name: Optional[str] = None
    purpose: Optional[str] = None
    expense_status: Optional[str] = None
    category_id: Optional[int] = None
    contract_id: Optional[int] = None
    project_id: Optional[int] = None
    balance_after: Decimal
    created_at: datetime


class CashBankWithdrawalCandidate(BaseModel):
    id: int
    date: DateType
    amount: Decimal
    currency: str = "RSD"
    counterparty_name: Optional[str] = None
    purpose: Optional[str] = None
    bank_reference: Optional[str] = None
    project_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CashSummaryResponse(BaseModel):
    current_balance: Decimal
    total_in: Decimal
    total_out: Decimal
    entries: list[CashEntryResponse] = Field(default_factory=list)
    available_withdrawals: list[CashBankWithdrawalCandidate] = Field(default_factory=list)


class CashWithdrawalCreate(BaseModel):
    bank_transaction_id: int
    note: Optional[str] = None


class CashPendingWithdrawalCreate(BaseModel):
    date: DateType
    amount: Decimal = Field(gt=0)
    currency: str = "RSD"
    description: str
    note: Optional[str] = None


class CashPendingWithdrawalLink(BaseModel):
    bank_transaction_id: int
    note: Optional[str] = None


class CashAdjustmentCreate(BaseModel):
    date: DateType
    direction: str
    amount: Decimal = Field(gt=0)
    description: str
    note: Optional[str] = None


class CashExpenseCreate(BaseModel):
    date: DateType
    description: str
    amount: Decimal = Field(gt=0)
    currency: str = "RSD"
    category: Optional[str] = None
    category_id: Optional[int] = None
    project_id: Optional[int] = None
    contract_id: Optional[int] = None
    note: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in ("project_id", "contract_id", "category_id"):
            if key in result and (result[key] == "" or result[key] is None):
                result[key] = None
        return result


class WorkerBase(BaseModel):
    name: str
    worker_type: str = "temporary"
    pay_scheme: str = "per_day"
    phone: Optional[str] = None
    note: Optional[str] = None
    regular_day_rate: Decimal = Field(default=0, ge=0)
    billing_hourly_rate: Decimal = Field(default=0, ge=0)
    weekly_rate: Decimal = Field(default=0, ge=0)
    monthly_rate: Decimal = Field(default=0, ge=0)
    trip_pricing_mode: str = "allowances"
    trip_work_day_rate: Decimal = Field(default=0, ge=0)
    trip_per_diem_rate: Decimal = Field(default=2500, ge=0)
    trip_food_rate: Decimal = Field(default=3000, ge=0)
    trip_advance_day_rate: Decimal = Field(default=3000, ge=0)
    lodging_night_rate: Decimal = Field(default=0, ge=0)
    lodging_nights_offset: int = -1
    default_project_id: Optional[int] = None
    default_category_id: Optional[int] = None
    is_active: bool = True

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in ("default_project_id", "default_category_id"):
            if key in result and (result[key] == "" or result[key] is None):
                result[key] = None
        return result


class WorkerCreate(WorkerBase):
    pass


class WorkerUpdate(BaseModel):
    name: Optional[str] = None
    worker_type: Optional[str] = None
    pay_scheme: Optional[str] = None
    phone: Optional[str] = None
    note: Optional[str] = None
    regular_day_rate: Optional[Decimal] = Field(default=None, ge=0)
    billing_hourly_rate: Optional[Decimal] = Field(default=None, ge=0)
    weekly_rate: Optional[Decimal] = Field(default=None, ge=0)
    monthly_rate: Optional[Decimal] = Field(default=None, ge=0)
    trip_pricing_mode: Optional[str] = None
    trip_work_day_rate: Optional[Decimal] = Field(default=None, ge=0)
    trip_per_diem_rate: Optional[Decimal] = Field(default=None, ge=0)
    trip_food_rate: Optional[Decimal] = Field(default=None, ge=0)
    trip_advance_day_rate: Optional[Decimal] = Field(default=None, ge=0)
    lodging_night_rate: Optional[Decimal] = Field(default=None, ge=0)
    lodging_nights_offset: Optional[int] = None
    default_project_id: Optional[int] = None
    default_category_id: Optional[int] = None
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in ("default_project_id", "default_category_id"):
            if key in result and (result[key] == "" or result[key] is None):
                result[key] = None
        return result


class WorkerResponse(WorkerBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WorkerPayoutCreate(BaseModel):
    worker_id: int
    payout_type: str = "regular"
    date: DateType
    period_start: Optional[DateType] = None
    period_end: Optional[DateType] = None
    work_days: Decimal = Field(default=0, ge=0)
    trip_days: Decimal = Field(default=0, ge=0)
    lodging_nights: Optional[Decimal] = Field(default=None, ge=0)
    lodging_amount: Optional[Decimal] = Field(default=None, ge=0)
    advance_paid: Decimal = Field(default=0, ge=0)
    cash_paid_amount: Optional[Decimal] = Field(default=None, ge=0)
    regular_day_rate: Optional[Decimal] = Field(default=None, ge=0)
    weekly_rate: Optional[Decimal] = Field(default=None, ge=0)
    monthly_rate: Optional[Decimal] = Field(default=None, ge=0)
    trip_pricing_mode: Optional[str] = None
    trip_work_day_rate: Optional[Decimal] = Field(default=None, ge=0)
    trip_per_diem_rate: Optional[Decimal] = Field(default=None, ge=0)
    trip_food_rate: Optional[Decimal] = Field(default=None, ge=0)
    trip_advance_day_rate: Optional[Decimal] = Field(default=None, ge=0)
    lodging_night_rate: Optional[Decimal] = Field(default=None, ge=0)
    project_id: Optional[int] = None
    contract_id: Optional[int] = None
    category_id: Optional[int] = None
    description: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_values(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in (
            "project_id",
            "contract_id",
            "category_id",
            "lodging_nights",
            "lodging_night_rate",
            "lodging_amount",
        ):
            if key in result and (result[key] == "" or result[key] is None):
                result[key] = None
        return result


class WorkerPayoutResponse(BaseModel):
    id: int
    worker_id: int
    worker_name: Optional[str] = None
    cash_entry_id: Optional[int] = None
    expense_id: Optional[int] = None
    payout_type: str
    date: DateType
    period_start: Optional[DateType] = None
    period_end: Optional[DateType] = None
    work_days: Decimal
    trip_days: Decimal
    lodging_nights: Decimal
    lodging_night_rate: Decimal
    lodging_amount: Decimal
    advance_paid: Decimal
    gross_amount: Decimal
    cash_paid_amount: Decimal
    remaining_amount: Decimal
    description: str
    note: Optional[str] = None
    project_id: Optional[int] = None
    contract_id: Optional[int] = None
    category_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkerPayoutCreateResponse(BaseModel):
    payout: WorkerPayoutResponse
    cash_entry: CashEntryResponse


class CashEntryUpdate(BaseModel):
    date: Optional[DateType] = None
    direction: Optional[str] = None
    amount: Optional[Decimal] = Field(default=None, gt=0)
    currency: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    project_id: Optional[int] = None
    contract_id: Optional[int] = None
    note: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in ("project_id", "contract_id", "category_id"):
            if key in result and (result[key] == "" or result[key] is None):
                result[key] = None
        return result


class BankTransactionCreateExpenseRequest(BaseModel):
    date: Optional[DateType] = None
    description: Optional[str] = None
    category: Optional[str] = None
    category_id: Optional[int] = None
    project_id: Optional[int] = None
    contract_id: Optional[int] = None
    note: Optional[str] = None

    @field_validator("project_id", "contract_id", "category_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, value):
        if value == "" or value is None:
            return None
        return value


class MatchCandidate(BaseModel):
    id: int
    type: str
    invoice_number: Optional[str] = None
    client_name: Optional[str] = None
    description: Optional[str] = None
    amount: Decimal
    amount_full: Optional[Decimal] = None
    amount_paid: Optional[Decimal] = None
    date: Optional[DateType] = None
    status: Optional[str] = None
    score: Optional[int] = None
    section: Optional[str] = None
    match_reason: Optional[str] = None


class MatchRequest(BaseModel):
    type: str  # income | expense | obligation
    id: int


class BankTransactionIncomeAllocationItem(BaseModel):
    income_id: int
    amount: Decimal = Field(gt=0)


class BankTransactionIncomeAllocationRequest(BaseModel):
    allocations: list[BankTransactionIncomeAllocationItem] = Field(default_factory=list)


class BankTransactionIncomeAllocationLineResponse(BaseModel):
    income_id: int
    invoice_number: str
    client_name: Optional[str] = None
    description: Optional[str] = None
    date: Optional[DateType] = None
    status: Optional[str] = None
    amount_full: Decimal = Decimal("0.00")
    amount_paid: Decimal = Decimal("0.00")
    available_amount: Decimal = Decimal("0.00")
    allocated_amount: Decimal = Decimal("0.00")
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    project_code: Optional[str] = None


class BankTransactionIncomeAllocationResponse(BaseModel):
    tx_id: int
    total_amount: Decimal
    allocated_amount: Decimal = Decimal("0.00")
    remaining_amount: Decimal = Decimal("0.00")
    allocations: list[BankTransactionIncomeAllocationLineResponse] = Field(default_factory=list)
    candidates: list[MatchCandidate] = Field(default_factory=list)


# ---------- TransactionCategory ----------


class TransactionCategoryCreate(BaseModel):
    name_ru: str
    name_sr: str
    category_type: str = "expense"  # expense | income
    category_group: str = "admin"  # commercial | admin | tax
    default_project_id: Optional[int] = None
    is_active: bool = True
    sort_order: int = 0

    @field_validator("default_project_id", mode="before")
    @classmethod
    def empty_default_project_to_none(cls, value):
        if value == "" or value is None:
            return None
        return value


class TransactionCategoryUpdate(BaseModel):
    name_ru: Optional[str] = None
    name_sr: Optional[str] = None
    category_type: Optional[str] = None
    category_group: Optional[str] = None
    default_project_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None

    @field_validator("default_project_id", mode="before")
    @classmethod
    def empty_default_project_to_none(cls, value):
        if value == "" or value is None:
            return None
        return value


class TransactionCategoryResponse(BaseModel):
    id: int
    name_ru: str
    name_sr: str
    category_type: str
    category_group: str
    default_project_id: Optional[int] = None
    is_active: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ServiceBackupInfo(BaseModel):
    name: str
    kind: str
    created_at: datetime
    db_size_bytes: int
    archive_size_bytes: int


class ServiceBackupSettings(BaseModel):
    supported: bool
    backup_dir: str
    database_path: Optional[str] = None
    current_db_size_bytes: int = 0
    auto_enabled: bool
    auto_interval_hours: int
    auto_retention_count: int
    manual_retention_count: int
    pre_restore_retention_count: int
    scheduler_check_minutes: int


class ServiceBackupSettingsUpdate(BaseModel):
    backup_dir: Optional[str] = None
    auto_enabled: Optional[bool] = None
    auto_interval_hours: Optional[int] = Field(default=None, ge=1, le=24 * 365)
    auto_retention_count: Optional[int] = Field(default=None, ge=1, le=1000)
    manual_retention_count: Optional[int] = Field(default=None, ge=1, le=1000)
    pre_restore_retention_count: Optional[int] = Field(default=None, ge=1, le=1000)
    scheduler_check_minutes: Optional[int] = Field(default=None, ge=1, le=24 * 60)

    @field_validator("backup_dir", mode="before")
    @classmethod
    def normalize_backup_dir(cls, value):
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class ServiceBackupStatusResponse(BaseModel):
    settings: ServiceBackupSettings
    backups: list[ServiceBackupInfo] = Field(default_factory=list)


class ServiceBackupOperationResponse(BaseModel):
    backup: ServiceBackupInfo
    message: str


class ServiceRestoreResponse(BaseModel):
    restored_backup: ServiceBackupInfo
    pre_restore_backup: Optional[ServiceBackupInfo] = None
    message: str


# --- IncomingInvoice ---


class IncomingInvoiceBase(BaseModel):
    invoice_number: str
    date: DateType
    client_id: Optional[int] = None
    counterparty_name: str
    project_id: Optional[int] = None
    amount: Decimal
    currency: str = "RSD"
    description: Optional[str] = None
    note: Optional[str] = None

    @field_validator("client_id", "project_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


class IncomingInvoiceCreate(IncomingInvoiceBase):
    source: str = "manual"


class IncomingInvoiceUpdate(BaseModel):
    invoice_number: Optional[str] = None
    date: Optional[DateType] = None
    client_id: Optional[int] = None
    counterparty_name: Optional[str] = None
    project_id: Optional[int] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    description: Optional[str] = None
    note: Optional[str] = None

    @field_validator("client_id", "project_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


class IncomingInvoiceResponse(IncomingInvoiceBase):
    id: int
    status: str
    settled_amount: Decimal = Decimal("0")
    remaining_amount: Decimal = Decimal("0")
    source: str = "manual"
    expense_id: Optional[int] = None
    efaktura_record_id: Optional[int] = None
    created_at: Optional[datetime] = None
    client_name: Optional[str] = None
    project_name: Optional[str] = None
    project_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class IncomingInvoiceLinkSummary(BaseModel):
    id: int
    invoice_number: str
    date: DateType
    amount: Decimal
    currency: str = "RSD"
    status: str
    counterparty_name: str
    client_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    project_code: Optional[str] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class IncomingInvoiceAttachExpenseRequest(BaseModel):
    expense_id: int


class IncomingInvoiceExpenseCandidateResponse(BaseModel):
    id: int
    date: DateType
    paid_date: Optional[DateType] = None
    description: str
    amount: Decimal
    currency: str = "RSD"
    category: Optional[str] = None
    category_id: Optional[int] = None
    status: Optional[str] = None
    source: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    project_code: Optional[str] = None
    contract_id: Optional[int] = None
    contract_number: Optional[str] = None
    bank_reference: Optional[str] = None
    note: Optional[str] = None
    bank_transaction_id: Optional[int] = None
    bank_counterparty_name: Optional[str] = None
    bank_purpose: Optional[str] = None


class IncomingInvoiceSettlementCreate(BaseModel):
    amount: Decimal
    date: DateType
    note: Optional[str] = None


class BankSettlementCreate(IncomingInvoiceSettlementCreate):
    bank_transaction_id: int


class OffsetSettlementCreate(IncomingInvoiceSettlementCreate):
    income_id: int


class IncomingInvoiceAdvanceLinkRequest(BaseModel):
    advance_invoice_id: int


class IncomingInvoiceClosingLinkRequest(BaseModel):
    closing_invoice_id: int


class IncomingInvoiceSettlementResponse(BaseModel):
    id: int
    incoming_invoice_id: int
    settlement_type: str
    amount: Decimal
    date: DateType
    note: Optional[str] = None
    bank_transaction_id: Optional[int] = None
    cash_entry_id: Optional[int] = None
    income_id: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class IncomingInvoiceDetailResponse(IncomingInvoiceResponse):
    settlements: list[IncomingInvoiceSettlementResponse] = Field(default_factory=list)
    advance_invoice: Optional[IncomingInvoiceLinkSummary] = None
    closing_invoice: Optional[IncomingInvoiceLinkSummary] = None


class CounterpartyBalanceItem(BaseModel):
    client_id: Optional[int] = None
    client_name: str
    document_receivables: Decimal = Decimal("0")
    issued_loans: Decimal = Decimal("0")
    receivables: Decimal = Decimal("0")
    document_payables: Decimal = Decimal("0")
    borrowed_loans: Decimal = Decimal("0")
    payables: Decimal = Decimal("0")
    net_balance: Decimal = Decimal("0")


class CounterpartyBalanceResponse(BaseModel):
    items: list[CounterpartyBalanceItem] = Field(default_factory=list)
    total_document_receivables: Decimal = Decimal("0")
    total_issued_loans: Decimal = Decimal("0")
    total_receivables: Decimal = Decimal("0")
    total_document_payables: Decimal = Decimal("0")
    total_borrowed_loans: Decimal = Decimal("0")
    total_payables: Decimal = Decimal("0")
    total_net_balance: Decimal = Decimal("0")


# --- Counterparty loans ---


class CounterpartyLoanCreateFromBank(BaseModel):
    loan_type: str  # borrowed | issued
    client_id: Optional[int] = None
    counterparty_name: Optional[str] = None
    agreement_number: Optional[str] = None
    agreement_date: Optional[DateType] = None
    due_date: Optional[DateType] = None
    note: Optional[str] = None

    @field_validator("client_id", mode="before")
    @classmethod
    def loan_empty_client_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


class CounterpartyLoanUpdate(BaseModel):
    client_id: Optional[int] = None
    counterparty_name: Optional[str] = None
    agreement_number: Optional[str] = None
    agreement_date: Optional[DateType] = None
    due_date: Optional[DateType] = None
    note: Optional[str] = None

    @field_validator("client_id", mode="before")
    @classmethod
    def loan_update_empty_client_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


class CounterpartyLoanMovementFromBank(BaseModel):
    movement_type: str  # disbursement | repayment
    note: Optional[str] = None


class CounterpartyLoanMovementResponse(BaseModel):
    id: int
    loan_id: int
    movement_type: str
    date: DateType
    amount: Decimal
    currency: str = "RSD"
    bank_transaction_id: Optional[int] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None
    bank_reference: Optional[str] = None
    bank_purpose: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CounterpartyLoanResponse(BaseModel):
    id: int
    loan_type: str
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    counterparty_name: str
    agreement_number: Optional[str] = None
    agreement_date: Optional[DateType] = None
    start_date: DateType
    due_date: Optional[DateType] = None
    currency: str = "RSD"
    note: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    disbursed_amount: Decimal = Decimal("0")
    repaid_amount: Decimal = Decimal("0")
    outstanding_amount: Decimal = Decimal("0")
    movements: list[CounterpartyLoanMovementResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class OwnerFundsMovementResponse(BaseModel):
    id: int
    date: DateType
    direction: str
    amount: Decimal
    currency: str = "RSD"
    counterparty_name: Optional[str] = None
    purpose: Optional[str] = None
    bank_reference: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
