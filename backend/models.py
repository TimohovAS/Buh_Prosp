"""Модели базы данных ProspEl."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, Float, Numeric, Boolean, Date, DateTime, ForeignKey, Enum, Index, UniqueConstraint, text
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
    maticni_broj = Column(String(20))  # MB / maticni broj
    contact = Column(String(200))
    client_type = Column(String(20), default="legal")  # legal, individual
    document_language = Column(String(5), default="sr")
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    incomes = relationship("Income", back_populates="client")
    contracts = relationship("Contract", back_populates="client")
    projects = relationship("Project", back_populates="client")


class Worker(Base):
    """Workers and contractors paid through the cash register."""
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    worker_type = Column(String(20), nullable=False, default="temporary")  # permanent | temporary
    pay_scheme = Column(String(20), nullable=False, default="per_day")  # monthly | weekly | per_day
    phone = Column(String(50))
    note = Column(Text)
    regular_day_rate = Column(Numeric(14, 2), default=0)
    weekly_rate = Column(Numeric(14, 2), default=0)
    monthly_rate = Column(Numeric(14, 2), default=0)
    trip_pricing_mode = Column(String(30), nullable=False, default="allowances")  # allowances | fixed_plus_lodging
    trip_work_day_rate = Column(Numeric(14, 2), default=0)
    trip_per_diem_rate = Column(Numeric(14, 2), default=2500)
    trip_food_rate = Column(Numeric(14, 2), default=3000)
    trip_advance_day_rate = Column(Numeric(14, 2), default=3000)
    lodging_night_rate = Column(Numeric(14, 2), default=0)
    lodging_nights_offset = Column(Integer, default=-1)
    default_project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    default_category_id = Column(Integer, ForeignKey("transaction_categories.id"), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    default_project = relationship("Project", foreign_keys=[default_project_id])
    default_category = relationship("TransactionCategory", foreign_keys=[default_category_id])
    payouts = relationship("WorkerPayout", back_populates="worker")


class WorkerPayout(Base):
    """Calculated worker payment recorded as a cash expense."""
    __tablename__ = "worker_payouts"

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False, index=True)
    cash_entry_id = Column(Integer, ForeignKey("cash_entries.id"), unique=True, nullable=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), unique=True, nullable=True)
    payout_type = Column(String(20), nullable=False, index=True)  # regular | monthly | trip_advance | trip_final
    date = Column(Date, nullable=False, index=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    work_days = Column(Numeric(8, 2), default=0)
    trip_days = Column(Numeric(8, 2), default=0)
    lodging_nights = Column(Numeric(8, 2), default=0)
    regular_day_rate = Column(Numeric(14, 2), default=0)
    weekly_rate = Column(Numeric(14, 2), default=0)
    monthly_rate = Column(Numeric(14, 2), default=0)
    trip_pricing_mode = Column(String(30), nullable=False, default="allowances")
    trip_work_day_rate = Column(Numeric(14, 2), default=0)
    trip_per_diem_rate = Column(Numeric(14, 2), default=0)
    trip_food_rate = Column(Numeric(14, 2), default=0)
    trip_advance_day_rate = Column(Numeric(14, 2), default=0)
    lodging_amount = Column(Numeric(14, 2), default=0)
    advance_paid = Column(Numeric(14, 2), default=0)
    gross_amount = Column(Numeric(14, 2), nullable=False)
    cash_paid_amount = Column(Numeric(14, 2), nullable=False)
    remaining_amount = Column(Numeric(14, 2), default=0)
    description = Column(String(500), nullable=False)
    note = Column(Text)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("transaction_categories.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    worker = relationship("Worker", back_populates="payouts")
    cash_entry = relationship("CashEntry", foreign_keys=[cash_entry_id])
    expense = relationship("Expense", foreign_keys=[expense_id])
    project = relationship("Project", foreign_keys=[project_id])
    contract = relationship("Contract", foreign_keys=[contract_id])
    category = relationship("TransactionCategory", foreign_keys=[category_id])


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
    opening_cash_balance = Column(Numeric(14, 2), default=0)  # Начальный остаток денежных средств
    opening_cash_date = Column(Date)  # Дата, на которую указан начальный остаток (default 1 Jan текущего года)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    emblem_data_url = Column(Text)
    efaktura_enabled = Column(Boolean, default=False)
    efaktura_api_base_url = Column(String(500))
    efaktura_api_key = Column(Text)
    efaktura_api_key_header = Column(String(100), default="ApiKey")
    efaktura_api_key_prefix = Column(String(50), default="")
    efaktura_sync_incoming = Column(Boolean, default=True)
    efaktura_sync_outgoing = Column(Boolean, default=True)
    efaktura_sync_lookback_days = Column(Integer, default=30)
    efaktura_incoming_list_path = Column(String(500))
    efaktura_incoming_document_path = Column(String(500))
    efaktura_outgoing_list_path = Column(String(500))
    efaktura_outgoing_document_path = Column(String(500))
    efaktura_save_pdf = Column(Boolean, default=False)
    efaktura_incoming_pdf_path = Column(String(500))
    efaktura_outgoing_pdf_path = Column(String(500))
    backup_dir = Column(String(500))
    backup_auto_enabled = Column(Boolean)
    backup_auto_interval_hours = Column(Integer)
    backup_auto_retention_count = Column(Integer)
    backup_manual_retention_count = Column(Integer)
    backup_pre_restore_retention_count = Column(Integer)
    backup_scheduler_check_minutes = Column(Integer)


class EfakturaImportRecord(Base):
    """Р–СѓСЂРЅР°Р» РёРјРїРѕСЂС‚РѕРІ eFaktura."""
    __tablename__ = "efaktura_import_records"
    __table_args__ = (UniqueConstraint("document_key", name="uq_efaktura_document_key"),)

    id = Column(Integer, primary_key=True, index=True)
    document_key = Column(String(500), nullable=False, unique=True, index=True)
    external_id = Column(String(200), index=True)
    direction = Column(String(20), nullable=False)
    invoice_number = Column(String(100), nullable=False)
    issued_date = Column(Date, nullable=False)
    amount_rsd = Column(Numeric(14, 2), nullable=False)
    supplier_name = Column(String(200))
    supplier_pib = Column(String(20))
    customer_name = Column(String(200))
    customer_pib = Column(String(20))
    imported_as = Column(String(20), nullable=False)
    imported_record_id = Column(Integer, nullable=False)
    source = Column(String(20), nullable=False, default="xml")
    file_name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)


class IncomingInvoice(Base):
    """Входящая фактура — наш долг перед контрагентом."""
    __tablename__ = "incoming_invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(100), nullable=False)
    date = Column(Date, nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    counterparty_name = Column(String(200), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(10), default="RSD")
    description = Column(Text)
    status = Column(String(20), nullable=False, default="unpaid")  # unpaid | partial | paid | cancelled
    settled_amount = Column(Numeric(14, 2), nullable=False, default=0)
    source = Column(String(20), nullable=False, default="manual")  # manual | efaktura
    efaktura_record_id = Column(Integer, ForeignKey("efaktura_import_records.id"), nullable=True, unique=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True, unique=True)
    advance_invoice_id = Column(Integer, ForeignKey("incoming_invoices.id"), nullable=True)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    client = relationship("Client")
    project = relationship("Project")
    expense = relationship("Expense")
    advance_invoice = relationship("IncomingInvoice", remote_side=[id], foreign_keys=[advance_invoice_id], uselist=False)
    efaktura_record = relationship("EfakturaImportRecord")
    settlements = relationship(
        "IncomingInvoiceSettlement",
        back_populates="incoming_invoice",
        cascade="all, delete-orphan",
    )

    @property
    def remaining_amount(self) -> Decimal:
        return Decimal(str(self.amount or 0)) - Decimal(str(self.settled_amount or 0))


class IncomingInvoiceSettlement(Base):
    """Журнал закрытия входящей фактуры: банк, наличка, взаимозачёт."""
    __tablename__ = "incoming_invoice_settlements"

    id = Column(Integer, primary_key=True, index=True)
    incoming_invoice_id = Column(Integer, ForeignKey("incoming_invoices.id"), nullable=False, index=True)
    settlement_type = Column(String(20), nullable=False)  # bank | cash | offset
    amount = Column(Numeric(14, 2), nullable=False)
    date = Column(Date, nullable=False)
    note = Column(Text)
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id"), nullable=True)
    cash_entry_id = Column(Integer, ForeignKey("cash_entries.id"), nullable=True)
    income_id = Column(Integer, ForeignKey("income.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    incoming_invoice = relationship("IncomingInvoice", back_populates="settlements")


class ContributionRates(Base):
    """Ставки налогов и взносов (из налогового решения). DEPRECATED: используйте YearDecision + MonthlyObligation."""
    __tablename__ = "contribution_rates"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    tax_amount = Column(Numeric(14, 2), default=0)
    pio_amount = Column(Numeric(14, 2), default=0)
    health_amount = Column(Numeric(14, 2), default=0)
    unemployment_amount = Column(Numeric(14, 2), default=0)
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
    monthly_amount = Column(Numeric(14, 2), nullable=False)  # Месячная аконтация
    base_amount = Column(Numeric(14, 2))  # Основница (опционально)
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
    amount = Column(Numeric(14, 2), nullable=False)
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
    """Счётчик номеров счетов по годам (блокировка конкуренции при присвоении NNNN-YYYY)."""
    __tablename__ = "invoice_sequence"

    year = Column(Integer, primary_key=True)
    last_number = Column(Integer, nullable=False, default=0)


class ProjectSequence(Base):
    """Счётчик кодов проектов по годам (формат PR-YYYY-NNNN)."""
    __tablename__ = "project_sequence"

    year = Column(Integer, primary_key=True)
    last_number = Column(Integer, nullable=False, default=0)


class Project(Base):
    """Проекты — центральная сущность (ЦФО), к ним привязываются доходы/расходы/договоры."""
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("code", name="uq_projects_code"),)

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50))  # PR-2026-0001, unique via __table_args__
    name = Column(String(200), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    is_internal = Column(Boolean, default=False)  # Внутренний (служебный) проект
    status = Column(String(20), nullable=False, default="active")  # lead | active | completed | archived
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    planned_income = Column(Numeric(14, 2), nullable=True)
    planned_expense = Column(Numeric(14, 2), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="projects")
    contracts = relationship("Contract", back_populates="project", foreign_keys="[Contract.project_id]")
    incomes = relationship("Income", back_populates="project")
    expenses = relationship("Expense", back_populates="project")
    purchase_receipts = relationship("PurchaseReceipt", back_populates="project")





class BankTransaction(Base):
    """Строка выписки банка (поступление/списание)."""
    __tablename__ = "bank_transactions"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    direction = Column(String(10), nullable=False, index=True)  # in | out
    currency = Column(String(5), default="RSD")
    counterparty_name = Column(String(200))
    purpose = Column(Text)
    bank_reference = Column(String(100), unique=True, nullable=True)
    status = Column(String(20), default="unmatched", index=True)  # unmatched | matched | ignored
    matched_type = Column(String(50))  # income | expense | obligation | cash | owner_funds | loan_movement
    matched_id = Column(Integer)
    project_id = Column(Integer, ForeignKey("projects.id"))
    raw_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", foreign_keys=[project_id])
    income_allocations = relationship(
        "BankTransactionIncomeAllocation",
        back_populates="bank_transaction",
        cascade="all, delete-orphan",
    )
    loan_movement = relationship(
        "CounterpartyLoanMovement",
        back_populates="bank_transaction",
        uselist=False,
    )


class CounterpartyLoan(Base):
    """Principal-only loan received from or issued to a counterparty."""
    __tablename__ = "counterparty_loans"

    id = Column(Integer, primary_key=True, index=True)
    loan_type = Column(String(20), nullable=False, index=True)  # borrowed | issued
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    counterparty_name = Column(String(200), nullable=False)
    agreement_number = Column(String(100))
    agreement_date = Column(Date)
    start_date = Column(Date, nullable=False, index=True)
    due_date = Column(Date)
    currency = Column(String(5), nullable=False, default="RSD")
    note = Column(Text)
    status = Column(String(20), nullable=False, default="open", index=True)  # open | repaid | cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    client = relationship("Client")
    movements = relationship(
        "CounterpartyLoanMovement",
        back_populates="loan",
        cascade="all, delete-orphan",
        order_by="CounterpartyLoanMovement.date.asc(), CounterpartyLoanMovement.id.asc()",
    )


class CounterpartyLoanMovement(Base):
    """A principal drawdown or repayment tied to one bank transaction."""
    __tablename__ = "counterparty_loan_movements"
    __table_args__ = (
        Index(
            "ux_counterparty_loan_movements_bank_transaction_id_not_null",
            "bank_transaction_id",
            unique=True,
            sqlite_where=text("bank_transaction_id IS NOT NULL"),
            postgresql_where=text("bank_transaction_id IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("counterparty_loans.id", ondelete="CASCADE"), nullable=False, index=True)
    movement_type = Column(String(20), nullable=False, index=True)  # disbursement | repayment
    date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(5), nullable=False, default="RSD")
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id"), nullable=True)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    loan = relationship("CounterpartyLoan", back_populates="movements")
    bank_transaction = relationship("BankTransaction", back_populates="loan_movement", foreign_keys=[bank_transaction_id])


class BankImportFile(Base):
    """Журнал импортированных банковских файлов (защита от повторного импорта)."""
    __tablename__ = "bank_import_files"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255), nullable=False)
    file_hash = Column(String(64), unique=True, index=True, nullable=False)
    file_size = Column(Integer)
    transaction_count = Column(Integer, default=0)
    created_income = Column(Integer, default=0)
    created_expense = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    imported_by = Column(Integer, ForeignKey("users.id"))
    imported_at = Column(DateTime, default=datetime.utcnow, index=True)


class CashEntry(Base):
    """Реестр налички: пополнение из банка, наличные расходы и корректировки."""
    __tablename__ = "cash_entries"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    direction = Column(String(10), nullable=False, index=True)  # in | out
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(5), default="RSD")
    description = Column(String(500), nullable=False)
    entry_type = Column(String(20), nullable=False, index=True)  # withdrawal | expense | adjustment
    note = Column(Text)
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id"), unique=True, nullable=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))

    bank_transaction = relationship("BankTransaction", foreign_keys=[bank_transaction_id])
    expense = relationship("Expense", foreign_keys=[expense_id])


class Income(Base):
    """Книга доходов (КПО) - записи о доходах. Управленческая экономика: issued/paid/cancelled."""
    __tablename__ = "income"
    __table_args__ = (UniqueConstraint("invoice_year", "invoice_number", name="uq_income_invoice_per_year"),)

    id = Column(Integer, primary_key=True, index=True)
    issued_date = Column("date", Date, nullable=False)  # дата счёта (колонка в БД: date)
    invoice_number = Column(String(50), nullable=False)
    invoice_year = Column(Integer, nullable=True)  # Период счёта (год): нумерация NNNN-YYYY сбрасывается по годам
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    client_name = Column(String(200))  # На случай если клиент не в справочнике
    description = Column(String(500))   # Основание платежа / описание услуги
    amount_rsd = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(5), default="RSD")
    exchange_rate = Column(Float, default=1.0)
    is_paid = Column(Boolean, default=False)
    paid_date = Column(Date)
    due_date = Column(Date)  # Valuta / срок оплаты
    paid_amount = Column(Numeric(14, 2), default=0.0)  # Сумма уже полученных платежей (для частичной оплаты)
    status = Column(String(20), nullable=False, default="issued")  # issued | partial | paid | cancelled

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
    bank_allocations = relationship(
        "BankTransactionIncomeAllocation",
        back_populates="income",
        cascade="all, delete-orphan",
    )

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
    amount = Column(Numeric(14, 2), default=0)
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
    items = relationship("ContractItem", back_populates="contract", cascade="all, delete-orphan")
    incomes = relationship("Income", back_populates="contract", foreign_keys="Income.contract_id")
    expenses = relationship("Expense", back_populates="contract", foreign_keys="Expense.contract_id")


class BankTransactionIncomeAllocation(Base):
    """Р Р°СЃРїСЂРµРґРµР»РµРЅРёРµ РѕРґРЅРѕРіРѕ РІС…РѕРґСЏС‰РµРіРѕ РїР»Р°С‚РµР¶Р° РїРѕ РЅРµСЃРєРѕР»СЊРєРёРј С„Р°РєС‚СѓСЂР°Рј."""
    __tablename__ = "bank_transaction_income_allocations"
    __table_args__ = (
        UniqueConstraint("bank_transaction_id", "income_id", name="uq_bank_tx_income_allocation"),
    )

    id = Column(Integer, primary_key=True, index=True)
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id"), nullable=False, index=True)
    income_id = Column(Integer, ForeignKey("income.id"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    bank_transaction = relationship("BankTransaction", back_populates="income_allocations")
    income = relationship("Income", back_populates="bank_allocations")


class ContractItem(Base):
    """Позиции договора (услуги/товары)."""
    __tablename__ = "contract_items"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    description = Column(String(500), nullable=False)
    quantity = Column(Float, default=1)
    unit = Column(String(20), default="шт")
    price = Column(Numeric(14, 2), default=0)
    amount = Column(Numeric(14, 2), default=0)  # quantity * price
    sort_order = Column(Integer, default=0)

    contract = relationship("Contract", back_populates="items")


class Payment(Base):
    """Платежи налогов и взносов."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    rates_id = Column(Integer, ForeignKey("contribution_rates.id"))
    tax_amount = Column(Numeric(14, 2), default=0)
    pio_amount = Column(Numeric(14, 2), default=0)
    health_amount = Column(Numeric(14, 2), default=0)
    unemployment_amount = Column(Numeric(14, 2), default=0)
    total_amount = Column(Numeric(14, 2), default=0)
    is_paid = Column(Boolean, default=False)
    paid_date = Column(Date)
    payment_reference = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    rates = relationship("ContributionRates", back_populates="payments")


class TransactionCategory(Base):
    """Справочник категорий доходов/расходов (статьи ДДС)."""
    __tablename__ = "transaction_categories"

    id = Column(Integer, primary_key=True, index=True)
    name_ru = Column(String(100), nullable=False)
    name_sr = Column(String(100), nullable=False)
    category_type = Column(String(20), default="expense")  # expense | income
    category_group = Column(String(20), default="admin")  # commercial | admin | tax
    default_project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    default_project = relationship("Project", foreign_keys=[default_project_id])


class Expense(Base):
    """Расходы. Сторно вместо удаления для obligation/bank_import."""
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(5), default="RSD")
    category = Column(String(50))  # legacy: materials, services, other, tax, etc.
    category_id = Column(Integer, ForeignKey("transaction_categories.id"), nullable=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True)
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

    category_ref = relationship("TransactionCategory")
    project = relationship("Project", back_populates="expenses", foreign_keys=[project_id])
    contract = relationship("Contract", back_populates="expenses", foreign_keys=[contract_id])
    reversal_of = relationship("Expense", remote_side=[id], foreign_keys=[reversal_of_id])
    reversed_by = relationship("Expense", remote_side=[id], foreign_keys=[reversed_expense_id])
    purchase_receipt = relationship("PurchaseReceipt", back_populates="expense", uselist=False)
    items = relationship(
        "ExpenseItem",
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by="ExpenseItem.line_no.asc()",
    )


class ExpenseItem(Base):
    __tablename__ = "expense_items"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True)
    line_no = Column(Integer, nullable=False, default=1)
    name = Column(String(500), nullable=False)
    quantity = Column(Numeric(14, 3), nullable=True)
    unit_price = Column(Numeric(14, 2), nullable=True)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    expense = relationship("Expense", back_populates="items", foreign_keys=[expense_id])


class PurchaseReceipt(Base):
    __tablename__ = "purchase_receipts"
    __table_args__ = (
        UniqueConstraint("qr_hash", name="uq_purchase_receipts_qr_hash"),
    )

    id = Column(Integer, primary_key=True, index=True)
    verification_url = Column(Text, nullable=False)
    qr_hash = Column(String(64), nullable=False, unique=True, index=True)
    invoice_number = Column(String(100), index=True)
    token = Column(String(100))
    seller_name = Column(String(200))
    seller_tax_id = Column(String(20))
    seller_address = Column(String(500))
    seller_city = Column(String(100))
    receipt_datetime = Column(DateTime, index=True)
    payment_type = Column(String(100))
    payment_kind = Column(String(20), default="unknown")  # cash | cashless | unknown
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    currency = Column(String(5), default="RSD")
    is_valid = Column(Boolean, default=True)
    status = Column(String(30), nullable=False, default="new")  # new | linked_expense | waiting_bank | matched_bank | cash_expense | error
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("transaction_categories.id"), nullable=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True, unique=True)
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id"), nullable=True)
    cash_entry_id = Column(Integer, ForeignKey("cash_entries.id"), nullable=True)
    raw_html = Column(Text)
    raw_specifications_json = Column(Text)
    raw_recapitulation_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    project = relationship("Project", back_populates="purchase_receipts", foreign_keys=[project_id])
    category_ref = relationship("TransactionCategory", foreign_keys=[category_id])
    expense = relationship("Expense", back_populates="purchase_receipt", foreign_keys=[expense_id])
    bank_transaction = relationship("BankTransaction", foreign_keys=[bank_transaction_id])
    cash_entry = relationship("CashEntry", foreign_keys=[cash_entry_id])
    items = relationship(
        "PurchaseReceiptItem",
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="PurchaseReceiptItem.line_no.asc()",
    )


class PurchaseReceiptItem(Base):
    __tablename__ = "purchase_receipt_items"

    id = Column(Integer, primary_key=True, index=True)
    receipt_id = Column(Integer, ForeignKey("purchase_receipts.id"), nullable=False, index=True)
    line_no = Column(Integer, nullable=False, default=1)
    gtin = Column(String(100))
    name = Column(String(500), nullable=False)
    quantity = Column(Numeric(14, 3), nullable=False, default=0)
    unit_price = Column(Numeric(14, 2), nullable=False, default=0)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    label = Column(String(20))
    label_rate = Column(Float)
    tax_base_amount = Column(Numeric(14, 2))
    vat_amount = Column(Numeric(14, 2))
    raw_json = Column(Text)

    receipt = relationship("PurchaseReceipt", back_populates="items", foreign_keys=[receipt_id])


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
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(5), default="RSD")
    category = Column(String(50))  # legacy: rent, internet, phone, utilities, insurance, other
    category_id = Column(Integer, ForeignKey("transaction_categories.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
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

    category_ref = relationship("TransactionCategory")
    project = relationship("Project")


class PlannedExpensePayment(Base):
    """Отметки об оплате конкретного экземпляра планируемого расхода (planned_expense_id + due_date)."""
    __tablename__ = "planned_expense_payments"

    id = Column(Integer, primary_key=True, index=True)
    planned_expense_id = Column(Integer, ForeignKey("planned_expenses.id"), nullable=False)
    due_date = Column(Date, nullable=False)
    paid_date = Column(Date, nullable=False)
    note = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)


class EcoTax(Base):
    """Экологическая такса - учёт и напоминания."""
    __tablename__ = "eco_tax"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    category = Column(String(50), default="micro")  # micro, small, etc.
    amount = Column(Numeric(14, 2), default=0)
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
