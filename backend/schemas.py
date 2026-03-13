"""Pydantic РЎРѓРЎвЂ¦Р ВµР СРЎвЂ№ Р Т‘Р В»РЎРЏ API."""
from datetime import date, datetime
from decimal import Decimal

# Р С’Р В»Р С‘Р В°РЎРѓ Р Т‘Р В»РЎРЏ Р С‘Р В·Р В±Р ВµР В¶Р В°Р Р…Р С‘РЎРЏ Р С”Р С•Р Р…РЎвЂћР В»Р С‘Р С”РЎвЂљР В° Р С‘Р СР ВµР Р…Р С‘ Р С—Р С•Р В»РЎРЏ date РЎРѓ РЎвЂљР С‘Р С—Р С•Р С date
DateType = date
from typing import Optional
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field, field_validator, model_validator

MAX_EMBLEM_DATA_URL_LENGTH = 350000


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(
        json_encoders={Decimal: lambda value: float(value)},
    )


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

    class Config:
        from_attributes = True


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
    contact: Optional[str] = None
    client_type: str = "legal"
    document_language: str = "sr"


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    pib: Optional[str] = None
    maticni_broj: Optional[str] = None
    contact: Optional[str] = None
    client_type: Optional[str] = None
    document_language: Optional[str] = None
    is_archived: Optional[bool] = None


class ClientResponse(ClientBase):
    id: int
    is_archived: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ClientBrief(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


# --- Project ---
class ProjectBase(BaseModel):
    code: Optional[str] = None
    name: str
    client_id: Optional[int] = None
    is_internal: Optional[bool] = False
    status: str = "active"  # lead | active | completed | archived
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
    status: Optional[str] = None
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    planned_income: Optional[Decimal] = None
    planned_expense: Optional[Decimal] = None
    notes: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: int
    is_internal: Optional[bool] = False
    client_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProjectBrief(BaseModel):
    id: int
    code: Optional[str] = None
    name: str

    class Config:
        from_attributes = True


# --- Income ---
class IncomeBase(BaseModel):
    issued_date: DateType = Field(serialization_alias="date")  # Р Т‘Р В°РЎвЂљР В° РЎРѓРЎвЂЎРЎвЂРЎвЂљР В° (Р Р† Р вЂР вЂќ: date)
    due_date: Optional[DateType] = None  # Valuta / РЎРѓРЎР‚Р С•Р С” Р С•Р С—Р В»Р В°РЎвЂљРЎвЂ№
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
    note: Optional[str] = None


class IncomeCreate(IncomeBase):
    invoice_number: Optional[str] = None  # Р С—РЎС“РЎРѓРЎвЂљР С• = Р С—РЎР‚Р С‘РЎРѓР Р†Р С•Р С‘РЎвЂљРЎРЉ Р В°Р Р†РЎвЂљР С•Р СР В°РЎвЂљР С‘РЎвЂЎР ВµРЎРѓР С”Р С‘
    invoice_year: Optional[int] = None
    issued_date: Optional[DateType] = None  # Р С—РЎР‚Р С‘ Р С—РЎС“РЎРѓРЎвЂљР С• Р В±Р ВµРЎР‚РЎвЂРЎвЂљРЎРѓРЎРЏ date (backward compat)
    status: Optional[str] = None
    paid_date: Optional[DateType] = None
    project_id: Optional[int] = None
    income_type: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def date_to_issued_date(cls, data):
        if isinstance(data, dict) and data.get("issued_date") is None and data.get("date") is not None:
            data = dict(data)
            data["issued_date"] = data.pop("date", None)
        return data

    @field_validator("client_id", "contract_id", "contract_payment_type", "project_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
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
    note: Optional[str] = None

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
        if "contract_payment_type" in result and (result["contract_payment_type"] == "" or result["contract_payment_type"] is None):
            result["contract_payment_type"] = None
        if result.get("contract_id") is None:
            result["contract_payment_type"] = None
        return result


class IncomeMarkPaid(BaseModel):
    paid_date: DateType


class BulkAssignProject(BaseModel):
    """Р СљР В°РЎРѓРЎРѓР С•Р Р†Р С•Р Вµ Р Р…Р В°Р В·Р Р…Р В°РЎвЂЎР ВµР Р…Р С‘Р Вµ Р С—РЎР‚Р С•Р ВµР С”РЎвЂљР В°: ids + project_id (null = РЎРѓР Р…РЎРЏРЎвЂљРЎРЉ Р С—РЎР‚Р С•Р ВµР С”РЎвЂљ)."""
    ids: list[int]
    project_id: Optional[int] = None


class IncomeResponse(IncomeBase):
    id: int
    is_paid: bool
    paid_amount: Decimal = Decimal("0.00")
    created_at: datetime
    contract_number: Optional[str] = None

    class Config:
        from_attributes = True


class IncomePaymentTransactionResponse(BaseModel):
    id: int
    date: DateType
    amount: Decimal
    currency: str = "RSD"
    counterparty_name: Optional[str] = None
    purpose: Optional[str] = None
    bank_reference: Optional[str] = None
    project_id: Optional[int] = None

    class Config:
        from_attributes = True


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

class DashboardIncomeResponse(BaseModel):
    """Р Р€Р С—РЎР‚Р С•РЎвЂ°РЎвЂР Р…Р Р…РЎвЂ№Р в„– Р С•РЎвЂљР Р†Р ВµРЎвЂљ Р Т‘Р В»РЎРЏ Р С—Р В°Р Р…Р ВµР В»Р С‘."""
    id: int
    issued_date: DateType = Field(serialization_alias="date")
    invoice_number: str
    client_name: Optional[str] = None
    amount_rsd: Decimal

    class Config:
        from_attributes = True


# --- Contract ---
class ContractItemBase(BaseModel):
    description: str
    quantity: float = 1
    unit: str = "РЎв‚¬РЎвЂљ"
    price: Decimal = Decimal("0.00")


class ContractItemCreate(ContractItemBase):
    pass


class ContractItemResponse(ContractItemBase):
    id: int
    contract_id: int
    amount: Decimal
    sort_order: int

    class Config:
        from_attributes = True


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
    # Р РЋРЎС“Р СР СРЎвЂ№ Р С—Р С• РЎвЂљР С‘Р С—Р В°Р С Р С—Р В»Р В°РЎвЂљР ВµР В¶Р ВµР в„– (Р В°Р Р†Р В°Р Р…РЎРѓ, Р С—РЎР‚Р С•Р СР ВµР В¶РЎС“РЎвЂљР С•РЎвЂЎР Р…РЎвЂ№Р Вµ, Р В·Р В°Р С”РЎР‚РЎвЂ№Р Р†Р В°РЎР‹РЎвЂ°Р С‘Р в„–)
    advance_sum: Decimal = Decimal("0.00")
    intermediate_sum: Decimal = Decimal("0.00")
    closing_sum: Decimal = Decimal("0.00")
    total_received: Decimal = Decimal("0.00")
    total_expenses: Decimal = Decimal("0.00")
    profit: Decimal = Decimal("0.00")

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class EnterpriseBrandResponse(BaseModel):
    name: Optional[str] = None
    emblem_data_url: Optional[str] = None

    class Config:
        from_attributes = True

# --- PaymentType, YearDecision, MonthlyObligation (Р СћР вЂ”: Р С›Р В±РЎРЏР В·Р В°РЎвЂљР ВµР В»РЎРЉР Р…РЎвЂ№Р Вµ Р С—Р В»Р В°РЎвЂљР ВµР В¶Р С‘) ---
class PaymentTypeResponse(BaseModel):
    id: int
    code: str
    name_sr: str
    name_ru: Optional[str] = None
    sort_order: int

    class Config:
        from_attributes = True


class YearDecisionBase(BaseModel):
    year: int
    payment_type_id: int
    period_start: DateType
    period_end: DateType
    monthly_amount: Decimal
    base_amount: Optional[Decimal] = None
    rate_percent: Optional[float] = None
    recipient_name: str = "Р СџР С•РЎР‚Р ВµРЎРѓР С”Р В° РЎС“Р С—РЎР‚Р В°Р Р†Р В° Р В Р ВµР С—РЎС“Р В±Р В»Р С‘Р С”Р Вµ Р РЋРЎР‚Р В±Р С‘РЎВР Вµ"
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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class ObligationMarkPaid(BaseModel):
    paid_date: DateType
    payment_reference: Optional[str] = None


class IPSQRData(BaseModel):
    """Р вЂќР В°Р Р…Р Р…РЎвЂ№Р Вµ Р Т‘Р В»РЎРЏ IPS QR (NBS)."""
    payer: str
    recipient: str
    account: str
    amount: Decimal
    currency: str
    purpose: str
    model: str
    reference: str


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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
    """Р СњР ВµР С•Р С—Р В»Р В°РЎвЂЎР ВµР Р…Р Р…Р С•Р Вµ Р С•Р В±РЎРЏР В·Р В°РЎвЂљР ВµР В»РЎРЉРЎРѓРЎвЂљР Р†Р С• Р Т‘Р В»РЎРЏ Р С—РЎР‚Р ВµР Т‘РЎС“Р С—РЎР‚Р ВµР В¶Р Т‘Р ВµР Р…Р С‘РЎРЏ Р Р…Р В° Р Т‘Р В°РЎв‚¬Р В±Р С•РЎР‚Р Т‘Р Вµ."""
    id: int
    payment_type_name: str
    amount: Decimal
    deadline: str  # YYYY-MM-DD
    status: str  # overdue | upcoming
    days_until: int  # Р С•РЎвЂљРЎР‚Р С‘РЎвЂ Р В°РЎвЂљР ВµР В»РЎРЉР Р…Р С•Р Вµ Р ВµРЎРѓР В»Р С‘ Р С—РЎР‚Р С•РЎРѓРЎР‚Р С•РЎвЂЎР ВµР Р…Р С•


class UpcomingPlannedItem(BaseModel):
    """Р СџРЎР‚Р С•РЎРѓРЎР‚Р С•РЎвЂЎР ВµР Р…Р Р…РЎвЂ№Р в„– Р С‘Р В»Р С‘ Р С—РЎР‚Р С‘Р В±Р В»Р С‘Р В¶Р В°РЎР‹РЎвЂ°Р С‘Р в„–РЎРѓРЎРЏ Р С—Р ВµРЎР‚Р С‘Р С•Р Т‘Р С‘РЎвЂЎР ВµРЎРѓР С”Р С‘Р в„– РЎР‚Р В°РЎРѓРЎвЂ¦Р С•Р Т‘."""
    planned_expense_id: int
    name: str
    amount: Decimal
    currency: str
    due_date: str
    status: str  # overdue | upcoming
    days_until: int


class DashboardStats(BaseModel):
    year_income: Decimal
    month_income: Decimal
    year_expenses: Decimal
    month_expenses: Decimal
    balance_month: Decimal  # month_income - month_expenses
    balance_year: Decimal   # year_income - year_expenses
    balance_all_time: Decimal
    financial_result_all_time: Decimal
    planned_expenses_until_month_end: Decimal  # Р С—Р В»Р В°Р Р…Р С‘РЎР‚РЎС“Р ВµР СРЎвЂ№Р Вµ РЎР‚Р В°РЎРѓРЎвЂ¦Р С•Р Т‘РЎвЂ№ + Р С•Р В±РЎРЏР В·Р В°РЎвЂљР ВµР В»РЎРЉР Р…РЎвЂ№Р Вµ Р С—Р В»Р В°РЎвЂљР ВµР В¶Р С‘ Р Т‘Р С• Р С”Р С•Р Р…РЎвЂ Р В° Р СР ВµРЎРѓРЎРЏРЎвЂ Р В°
    income_limit_status: IncomeLimitStatus
    unpaid_payments_count: int
    upcoming_payment_date: Optional[str] = None
    upcoming_unpaid_obligations: list[UpcomingObligationItem] = []
    upcoming_planned_expenses: list[UpcomingPlannedItem] = []
    recent_incomes: list[DashboardIncomeResponse]


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
    bank_reference: Optional[str] = None  # Р СњР С•Р СР ВµРЎР‚ Р С—Р В»Р В°РЎвЂљРЎвЂР В¶Р С”Р С‘ / ID transakcije
    note: Optional[str] = None

    @field_validator("project_id", "contract_id", "category_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, value):
        if value == "" or value is None:
            return None
        return value


class ExpenseCreate(ExpenseBase):
    paid_date: Optional[DateType] = None


class ExpenseReverseRequest(BaseModel):
    date: Optional[DateType] = None
    comment: Optional[str] = None


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

    class Config:
        from_attributes = True


# --- PlannedExpense (Р СџР В»Р В°Р Р…Р С‘РЎР‚РЎС“Р ВµР СРЎвЂ№Р Вµ РЎР‚Р В°РЎРѓРЎвЂ¦Р С•Р Т‘РЎвЂ№) ---

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

    class Config:
        from_attributes = True


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
    period: str = "monthly"  # weekly, monthly, quarterly, yearly
    payment_day: Optional[int] = None  # 1-31 Р Т‘Р В»РЎРЏ monthly/quarterly/yearly
    payment_day_of_week: Optional[int] = None  # 0-6 Р Т‘Р В»РЎРЏ weekly (0=Р С—Р Р…)
    start_date: DateType
    end_date: Optional[DateType] = None
    reminder_days: int = 3
    is_active: bool = True
    note: Optional[str] = None

    @field_validator("project_id", "category_id", mode="before")
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
    period: Optional[str] = None
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
        for key in ("project_id", "category_id"):
            if key in result and (result[key] == "" or result[key] is None):
                result[key] = None
        return result


class PlannedExpenseResponse(PlannedExpenseBase):
    id: int
    category_id: Optional[int] = None
    project_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UpcomingPaymentItem(BaseModel):
    planned_expense_id: int
    name: str
    amount: Decimal
    currency: str
    due_date: str  # YYYY-MM-DD
    reminder_days: int
    is_paid: bool = False


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
    matched_type: Optional[str] = None   # income | expense | obligation | cash
    matched_id: Optional[int] = None
    project_id: Optional[int] = None
    raw_json: Optional[str] = None


class BankTransactionCreate(BankTransactionBase):
    pass


class BankTransactionUpdate(BaseModel):
    status: Optional[str] = None
    matched_type: Optional[str] = None
    matched_id: Optional[int] = None
    project_id: Optional[int] = None


class BankTransactionResponse(BankTransactionBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class CashSummaryResponse(BaseModel):
    current_balance: Decimal
    total_in: Decimal
    total_out: Decimal
    entries: list[CashEntryResponse] = Field(default_factory=list)
    available_withdrawals: list[CashBankWithdrawalCandidate] = Field(default_factory=list)


class CashWithdrawalCreate(BaseModel):
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


class MatchRequest(BaseModel):
    type: str  # income | expense | obligation
    id: int


# ---------- TransactionCategory ----------

class TransactionCategoryCreate(BaseModel):
    name_ru: str
    name_sr: str
    category_type: str = "expense"  # expense | income
    category_group: str = "admin"  # commercial | admin | tax
    is_active: bool = True
    sort_order: int = 0


class TransactionCategoryUpdate(BaseModel):
    name_ru: Optional[str] = None
    name_sr: Optional[str] = None
    category_type: Optional[str] = None
    category_group: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class TransactionCategoryResponse(BaseModel):
    id: int
    name_ru: str
    name_sr: str
    category_type: str
    category_group: str
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


