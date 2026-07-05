import asyncio
import os
import sys

# Add root directory to path so 'backend' module is recognized
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.database import AsyncSessionLocal as SessionLocal
from backend.models import Income, Expense, BankTransaction
from sqlalchemy import select


async def main():
    async with SessionLocal() as db:
        print("Starting migration...")
        # Migrate Incomes
        r_inc = await db.execute(select(Income).where(Income.is_paid == True))
        incomes = r_inc.scalars().all()

        migrated_incomes = 0
        for inc in incomes:
            r_exists = await db.execute(
                select(BankTransaction).where(
                    BankTransaction.matched_type == "income", BankTransaction.matched_id == inc.id
                )
            )
            if r_exists.scalar_one_or_none():
                continue

            tx = BankTransaction(
                date=inc.paid_date or inc.issued_date,
                amount=inc.amount_rsd,
                direction="in",
                currency=inc.currency,
                counterparty_name=inc.client_name,
                purpose=inc.description or f"Оплата по счету {inc.invoice_number}",
                bank_reference=inc.bank_reference,
                status="matched",
                matched_type="income",
                matched_id=inc.id,
                project_id=inc.project_id,
                raw_json='{"migration": "from_income_v1"}',
            )
            db.add(tx)
            migrated_incomes += 1

        # Migrate Expenses
        r_exp = await db.execute(select(Expense).where(Expense.status.in_(["paid", "reversed"])))
        expenses = r_exp.scalars().all()

        migrated_expenses = 0
        for exp in expenses:
            r_exists = await db.execute(
                select(BankTransaction).where(
                    BankTransaction.matched_type == "expense", BankTransaction.matched_id == exp.id
                )
            )
            if r_exists.scalar_one_or_none():
                continue

            tx = BankTransaction(
                date=exp.paid_date or exp.date,
                amount=exp.amount,
                direction="out",
                currency=exp.currency,
                counterparty_name=None,
                purpose=exp.description,
                bank_reference=exp.bank_reference,
                status="matched",
                matched_type="expense",
                matched_id=exp.id,
                project_id=exp.project_id,
                raw_json='{"migration": "from_expense_v1"}',
            )
            db.add(tx)
            migrated_expenses += 1

        await db.commit()
        print(f"Migration complete: {migrated_incomes} incomes, {migrated_expenses} expenses.")


if __name__ == "__main__":
    asyncio.run(main())
