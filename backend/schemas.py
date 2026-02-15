"""Pydantic схемы для API."""
from datetime import date, datetime

# Алиас для избежания конфликта имени поля date с типом date
DateType = date
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


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
    contact: Optional[str] = None
    client_type: str = "legal"
    document_language: str = "sr"


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    pib: Optional[str] = None
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
    contract_id: Optional[int] = None
    status: str = "active"  # lead | active | completed | archived
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    planned_income: Optional[float] = None
    planned_expense: Optional[float] = None
    notes: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    client_id: Optional[int] = None
    contract_id: Optional[int] = None
    status: Optional[str] = None
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    planned_income: Optional[float] = None
    planned_expense: Optional[float] = None
    notes: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: int
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
    issued_date: DateType = Field(serialization_alias="date")  # дата счёта (в БД: date)
    invoice_number: str
    invoice_year: Optional[int] = None
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    contract_id: Optional[int] = None
    contract_payment_type: Optional[str] = None  # advance, intermediate, closing
    description: Optional[str] = None
    amount_rsd: float
    currency: str = "RSD"
    exchange_rate: float = 1.0
    status: Optional[str] = None  # issued | paid | cancelled
    paid_date: Optional[DateType] = None
    project_id: Optional[int] = None
    income_type: Optional[str] = None  # advance | intermediate | final | other
    note: Optional[str] = None


class IncomeCreate(IncomeBase):
    invoice_number: Optional[str] = None  # пусто = присвоить автоматически
    invoice_year: Optional[int] = None
    issued_date: Optional[DateType] = None  # при пусто берётся date (backward compat)
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

    @field_validator("client_id", "contract_id", "contract_payment_type", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


class IncomeUpdate(BaseModel):
    issued_date: Optional[DateType] = None
    invoice_number: Optional[str] = None
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    contract_id: Optional[int] = None
    contract_payment_type: Optional[str] = None
    description: Optional[str] = None
    amount_rsd: Optional[float] = None
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
        for key in ("client_id", "contract_id", "project_id"):
            if key in result and (result[key] == "" or result[key] is None):
                result[key] = None
        if "contract_payment_type" in result and (result["contract_payment_type"] == "" or result["contract_payment_type"] is None):
            result["contract_payment_type"] = None
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
    created_at: datetime
    contract_number: Optional[str] = None

    class Config:
        from_attributes = True


class DashboardIncomeResponse(BaseModel):
    """Упрощённый ответ для панели."""
    id: int
    issued_date: DateType = Field(serialization_alias="date")
    invoice_number: str
    client_name: Optional[str] = None
    amount_rsd: float

    class Config:
        from_attributes = True


# --- Contract ---
class ContractItemBase(BaseModel):
    description: str
    quantity: float = 1
    unit: str = "шт"
    price: float = 0


class ContractItemCreate(ContractItemBase):
    pass


class ContractItemResponse(ContractItemBase):
    id: int
    contract_id: int
    amount: float
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
    amount: float = 0
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
    amount: Optional[float] = None
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
    advance_sum: float = 0
    intermediate_sum: float = 0
    closing_sum: float = 0
    total_received: float = 0

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
    opening_cash_balance: Optional[float] = 0
    opening_cash_date: Optional[DateType] = None


class EnterpriseUpdate(EnterpriseBase):
    name: Optional[str] = None


class EnterpriseResponse(EnterpriseBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- PaymentType, YearDecision, MonthlyObligation (ТЗ: Обязательные платежи) ---
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
    monthly_amount: float
    base_amount: Optional[float] = None
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
    monthly_amount: Optional[float] = None
    base_amount: Optional[float] = None
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
    amount: float
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
    """Данные для IPS QR (NBS)."""
    payer: str
    recipient: str
    account: str
    amount: float
    currency: str
    purpose: str
    model: str
    reference: str


# --- ContributionRates ---
class ContributionRatesBase(BaseModel):
    year: int
    tax_amount: float = 0
    pio_amount: float = 0
    health_amount: float = 0
    unemployment_amount: float = 0
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
    tax_amount: float = 0
    pio_amount: float = 0
    health_amount: float = 0
    unemployment_amount: float = 0


class PaymentCreate(PaymentBase):
    rates_id: Optional[int] = None


class PaymentUpdate(BaseModel):
    is_paid: Optional[bool] = None
    paid_date: Optional[DateType] = None
    payment_reference: Optional[str] = None


class PaymentResponse(PaymentBase):
    id: int
    total_amount: float
    is_paid: bool
    paid_date: Optional[DateType] = None
    payment_reference: Optional[str] = None

    class Config:
        from_attributes = True


# --- Dashboard / Stats ---
class IncomeLimitStatus(BaseModel):
    year_income: float
    limit_6m: int
    limit_8m: int
    percent_6m: float
    percent_8m: float
    warning_6m: bool
    warning_8m: bool
    exceeded_6m: bool
    exceeded_8m: bool


class UpcomingObligationItem(BaseModel):
    """Неоплаченное обязательство для предупреждения на дашборде."""
    id: int
    payment_type_name: str
    amount: float
    deadline: str  # YYYY-MM-DD
    status: str  # overdue | upcoming
    days_until: int  # отрицательное если просрочено


class UpcomingPlannedItem(BaseModel):
    """Просроченный или приближающийся периодический расход."""
    planned_expense_id: int
    name: str
    amount: float
    currency: str
    due_date: str
    status: str  # overdue | upcoming
    days_until: int


class DashboardStats(BaseModel):
    year_income: float
    month_income: float
    year_expenses: float
    month_expenses: float
    balance_month: float  # month_income - month_expenses
    balance_year: float   # year_income - year_expenses
    planned_expenses_until_month_end: float  # планируемые расходы + обязательные платежи до конца месяца
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
    amount: float
    currency: str = "RSD"
    category: Optional[str] = None
    paid_date: Optional[DateType] = None
    status: Optional[str] = None  # planned | paid | reversed
    is_tax_related: Optional[bool] = None
    project_id: Optional[int] = None
    source: Optional[str] = None  # manual | planned | obligation | bank_import
    reversal_of_id: Optional[int] = None
    bank_reference: Optional[str] = None  # Номер платёжки / ID transakcije
    note: Optional[str] = None


class ExpenseCreate(ExpenseBase):
    paid_date: Optional[DateType] = None


class ExpenseReverseRequest(BaseModel):
    date: Optional[DateType] = None
    comment: Optional[str] = None


class ExpenseUpdate(BaseModel):
    date: Optional[DateType] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    paid_date: Optional[DateType] = None
    project_id: Optional[int] = None
    note: Optional[str] = None


class ExpenseResponse(ExpenseBase):
    id: int
    reversed_expense_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- PlannedExpense (Планируемые расходы) ---
class PlannedExpenseBase(BaseModel):
    name: str
    description: Optional[str] = None
    amount: float
    currency: str = "RSD"
    category: Optional[str] = None
    period: str = "monthly"  # weekly, monthly, quarterly, yearly
    payment_day: Optional[int] = None  # 1-31 для monthly/quarterly/yearly
    payment_day_of_week: Optional[int] = None  # 0-6 для weekly (0=пн)
    start_date: DateType
    end_date: Optional[DateType] = None
    reminder_days: int = 3
    is_active: bool = True
    note: Optional[str] = None


class PlannedExpenseCreate(PlannedExpenseBase):
    pass


class PlannedExpenseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    period: Optional[str] = None
    payment_day: Optional[int] = None
    payment_day_of_week: Optional[int] = None
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    reminder_days: Optional[int] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None


class PlannedExpenseResponse(PlannedExpenseBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UpcomingPaymentItem(BaseModel):
    planned_expense_id: int
    name: str
    amount: float
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
