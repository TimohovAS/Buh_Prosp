"""Модели базы данных ProspEl."""
from datetime import datetime, date
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, Date, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.database import Base
import enum


class UserRole(str, enum.Enum):
    """Роли пользователей."""
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    OBSERVER = "observer"
    CASHIER = "cashier"


class User(Base):
    """Пользователи системы."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(200))
    role = Column(String(20), default=UserRole.ACCOUNTANT.value)
    default_language = Column(String(5), default="sr")  # sr, ru
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Client(Base):
    """Справочник клиентов."""
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    address = Column(String(500))
    pib = Column(String(20))  # PIB/ИНН
    contact = Column(String(200))
    client_type = Column(String(20), default="legal")  # legal, individual
    document_language = Column(String(5), default="sr")
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    incomes = relationship("Income", back_populates="client")
    contracts = relationship("Contract", back_populates="client")
    projects = relationship("Project", back_populates="client")


class Enterprise(Base):
    """Данные предприятия (ИП)."""
    __tablename__ = "enterprise"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    address = Column(String(500))
    pib = Column(String(20))
    maticni_broj = Column(String(20))  # Регистрационный номер
    bank_name = Column(String(100))
    bank_account = Column(String(50))
    bank_swift = Column(String(20))
    main_activity_code = Column(String(20))  # Шифра деятельности
    opening_cash_balance = Column(Float, default=0)  # Начальный остаток денежных средств
    opening_cash_date = Column(Date)  # Дата, на которую указан начальный остаток (default 1 Jan текущего года)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContributionRates(Base):
    """Ставки налогов и взносов (из налогового решения). DEPRECATED: используйте YearDecision + MonthlyObligation."""
    __tablename__ = "contribution_rates"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    tax_amount = Column(Float, default=0)
    pio_amount = Column(Float, default=0)
    health_amount = Column(Float, default=0)
    unemployment_amount = Column(Float, default=0)
    pay_order_number = Column(String(50))
    start_date = Column(Date)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    payments = relationship("Payment", back_populates="rates")


# --- Обязательные платежи (ТЗ: решения Пореске управе) ---
class PaymentType(Base):
    """Тип обязательного платежа: Порез, PIO, Здравство, Безработица."""
    __tablename__ = "payment_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False)  # tax, pio, health, unemployment
    name_sr = Column(String(100), nullable=False)
    name_ru = Column(String(100))
    sort_order = Column(Integer, default=0)

    decisions = relationship("YearDecision", back_populates="payment_type")
    obligations = relationship("MonthlyObligation", back_populates="payment_type")


class YearDecision(Base):
    """Решение Пореске управе на год: параметры начисления и платежные реквизиты."""
    __tablename__ = "year_decisions"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    payment_type_id = Column(Integer, ForeignKey("payment_types.id"), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    monthly_amount = Column(Float, nullable=False)  # Месячная аконтация
    base_amount = Column(Float)  # Основница (опционально)
    rate_percent = Column(Float)  # Ставка % (опционально)
    recipient_name = Column(String(200), default="Пореска управа Републике Србије")
    recipient_account = Column(String(30), nullable=False)  # NNN-NNNNNNNNN-NN
    sifra_placanja = Column(String(10), default="253")
    model = Column(String(10), default="97")
    poziv_na_broj = Column(String(50), nullable=False)  # Позив на број за текущий год
    poziv_na_broj_next = Column(String(50))  # Позив для привремене аконтације след. года
    payment_purpose = Column(String(200), nullable=False)  # Сврха уплате (шаблон с YYYY)
    currency = Column(String(5), default="RSD")
    is_provisional = Column(Boolean, default=False)  # Привремене аконтације
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payment_type = relationship("PaymentType", back_populates="decisions")
    obligations = relationship("MonthlyObligation", back_populates="decision", cascade="all, delete-orphan")


class MonthlyObligation(Base):
    """Месячное обязательство: год, месяц, тип, сумма, дедлайн, статус."""
    __tablename__ = "monthly_obligations"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    payment_type_id = Column(Integer, ForeignKey("payment_types.id"), nullable=False)
    decision_id = Column(Integer, ForeignKey("year_decisions.id"))
    amount = Column(Float, nullable=False)
    deadline = Column(Date, nullable=False)  # 15-е число месяца, следующего за отчётным
    status = Column(String(20), default="unpaid")  # unpaid, paid, overdue
    paid_date = Column(Date)
    payment_reference = Column(String(100))
    payment_method = Column(String(20), default="manual")  # manual, bank_import
    expense_id = Column(Integer, ForeignKey("expenses.id"))  # Созданный расход при отметке оплаты
    note = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    payment_type = relationship("PaymentType", back_populates="obligations")
    decision = relationship("YearDecision", back_populates="obligations")


class InvoiceSequence(Base):
    """Счётчик номеров счетов по годам (блокировка конкуренции при присвоении YYYY-NNNN)."""
    __tablename__ = "invoice_sequence"

    year = Column(Integer, primary_key=True)
    last_number = Column(Integer, nullable=False, default=0)


class ProjectSequence(Base):
    """Счётчик кодов проектов по годам (формат PR-YYYY-NNNN)."""
    __tablename__ = "project_sequence"

    year = Column(Integer, primary_key=True)
    last_number = Column(Integer, nullable=False, default=0)


class Project(Base):
    """Проекты — центральная сущность, к ним привязываются доходы/расходы/договоры."""
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("code", name="uq_projects_code"),)

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50))  # PR-2026-0001, unique via __table_args__
    name = Column(String(200), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True)
    status = Column(String(20), nullable=False, default="active")  # lead | active | completed | archived
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    planned_income = Column(Float, nullable=True)
    planned_expense = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="projects")
    contract = relationship("Contract", back_populates="projects_as_main", foreign_keys="[Project.contract_id]")
    contracts = relationship("Contract", back_populates="project", foreign_keys="[Contract.project_id]")
    incomes = relationship("Income", back_populates="project")
    expenses = relationship("Expense", back_populates="project")


class CashTransaction(Base):
    """Денежные операции для cash-flow. Создаётся при mark-paid invoice."""
    __tablename__ = "cash_transactions"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(20), nullable=False)  # income | expense
    source = Column(String(30), nullable=False)  # invoice | expense | ...
    reference_id = Column(Integer, nullable=False)  # income.id или expense.id
    amount = Column(Float, nullable=False)
    date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Income(Base):
    """Книга доходов (КПО) - записи о доходах. Управленческая экономика: issued/paid/cancelled."""
    __tablename__ = "income"
    __table_args__ = (UniqueConstraint("invoice_year", "invoice_number", name="uq_income_invoice_per_year"),)

    id = Column(Integer, primary_key=True, index=True)
    issued_date = Column("date", Date, nullable=False)  # дата счёта (колонка в БД: date)
    invoice_number = Column(String(50), nullable=False)
    invoice_year = Column(Integer, nullable=True)  # Период счёта (год): нумерация YYYY-NNNN сбрасывается по годам
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    client_name = Column(String(200))  # На случай если клиент не в справочнике
    description = Column(String(500))   # Основание платежа / описание услуги
    amount_rsd = Column(Float, nullable=False)
    currency = Column(String(5), default="RSD")
    exchange_rate = Column(Float, default=1.0)
    is_paid = Column(Boolean, default=False)
    paid_date = Column(Date)
    status = Column(String(20), nullable=False, default="issued")  # issued | paid | cancelled
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    income_type = Column(String(20), nullable=True)  # advance | intermediate | final | other
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))

    client = relationship("Client", back_populates="incomes")
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True)
    contract_payment_type = Column(String(20))  # advance, intermediate, closing — тип платежа по договору
    bank_reference = Column(String(100))  # Референция банка при импорте из извода
    contract = relationship("Contract", back_populates="incomes", foreign_keys=[contract_id])
    project = relationship("Project", back_populates="incomes", foreign_keys=[project_id])

    @property
    def contract_number(self) -> Optional[str]:
        return self.contract.number if self.contract else None


class Contract(Base):
    """Договоры (по образцу 1С Моя фирма)."""
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    contract_type = Column(String(50), default="service")  # service, supply, rent, commission
    subject = Column(String(500))  # Предмет договора
    amount = Column(Float, default=0)
    currency = Column(String(5), default="RSD")
    validity_start = Column(Date)
    validity_end = Column(Date)
    status = Column(String(20), default="active")  # active, completed, cancelled
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))

    client = relationship("Client", back_populates="contracts")
    project = relationship("Project", back_populates="contracts", foreign_keys=[project_id])
    projects_as_main = relationship("Project", back_populates="contract", foreign_keys="[Project.contract_id]")
    items = relationship("ContractItem", back_populates="contract", cascade="all, delete-orphan")
    incomes = relationship("Income", back_populates="contract", foreign_keys="Income.contract_id")


class ContractItem(Base):
    """Позиции договора (услуги/товары)."""
    __tablename__ = "contract_items"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    description = Column(String(500), nullable=False)
    quantity = Column(Float, default=1)
    unit = Column(String(20), default="шт")
    price = Column(Float, default=0)
    amount = Column(Float, default=0)  # quantity * price
    sort_order = Column(Integer, default=0)

    contract = relationship("Contract", back_populates="items")


class Payment(Base):
    """Платежи налогов и взносов."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    rates_id = Column(Integer, ForeignKey("contribution_rates.id"))
    tax_amount = Column(Float, default=0)
    pio_amount = Column(Float, default=0)
    health_amount = Column(Float, default=0)
    unemployment_amount = Column(Float, default=0)
    total_amount = Column(Float, default=0)
    is_paid = Column(Boolean, default=False)
    paid_date = Column(Date)
    payment_reference = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    rates = relationship("ContributionRates", back_populates="payments")


class Expense(Base):
    """Расходы. Сторно вместо удаления для obligation/bank_import."""
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    description = Column(String(500), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(5), default="RSD")
    category = Column(String(50))  # materials, services, other, tax, etc.
    bank_reference = Column(String(100))  # Референция банка при импорте из извода
    paid_date = Column(Date)
    status = Column(String(20), nullable=False, default="paid")  # planned | paid | reversed
    is_tax_related = Column(Boolean, nullable=False, default=False)
    source = Column(String(20), nullable=False, default="manual")  # manual | planned | obligation | bank_import
    reversed_expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True)  # id сторнирующей записи
    reversal_of_id = Column(Integer, ForeignKey("expenses.id"), nullable=True)  # id сторнируемой записи
    note = Column(Text)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))

    project = relationship("Project", back_populates="expenses", foreign_keys=[project_id])
    reversal_of = relationship("Expense", remote_side=[id], foreign_keys=[reversal_of_id])
    reversed_by = relationship("Expense", remote_side=[id], foreign_keys=[reversed_expense_id])


class PeriodClosure(Base):
    """Закрытие периода (year, month) — для управленческого учёта."""
    __tablename__ = "period_closures"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    closed_at = Column(DateTime, nullable=False)
    closed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class PlannedExpense(Base):
    """Планируемые (периодические) расходы — аренда, интернет, телефон и т.д."""
    __tablename__ = "planned_expenses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)  # Название: Аренда, Интернет, Телефон
    description = Column(String(500))  # Доп. описание
    amount = Column(Float, nullable=False)
    currency = Column(String(5), default="RSD")
    category = Column(String(50))  # rent, internet, phone, utilities, insurance, other
    period = Column(String(20), default="monthly")  # weekly, monthly, quarterly, yearly
    payment_day = Column(Integer)  # День месяца (1-31) для monthly/quarterly/yearly
    payment_day_of_week = Column(Integer)  # День недели (0=пн, 6=вс) для weekly
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)  # Опционально — до какой даты действует
    reminder_days = Column(Integer, default=3)  # За сколько дней напоминать (0 = не напоминать)
    is_active = Column(Boolean, default=True)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PlannedExpensePayment(Base):
    """Отметки об оплате конкретного экземпляра планируемого расхода (planned_expense_id + due_date)."""
    __tablename__ = "planned_expense_payments"

    id = Column(Integer, primary_key=True, index=True)
    planned_expense_id = Column(Integer, ForeignKey("planned_expenses.id"), nullable=False)
    due_date = Column(Date, nullable=False)
    paid_date = Column(Date, nullable=False)
    expense_id = Column(Integer, ForeignKey("expenses.id"))  # Созданный расход
    note = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)


class EcoTax(Base):
    """Экологическая такса - учёт и напоминания."""
    __tablename__ = "eco_tax"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    category = Column(String(50), default="micro")  # micro, small, etc.
    amount = Column(Float, default=0)
    is_paid = Column(Boolean, default=False)
    paid_date = Column(Date)
    reminder_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """Журнал аудита."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(50))  # login, create, update, delete
    entity_type = Column(String(50))  # income, client, payment, etc.
    entity_id = Column(Integer)
    description = Column(Text)
    ip_address = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
