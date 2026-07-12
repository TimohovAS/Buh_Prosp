import { NavLink } from 'react-router-dom'
import { tr } from '../i18n'

// Группы маршрутов, объединённые в один пункт бокового меню.
// Ярлыки вычисляются при рендере, чтобы реагировать на смену языка.
const TAB_GROUPS = {
  finance: () => [
    { to: '/finance', label: tr('financeOverviewTab'), end: true },
    { to: '/finance/pnl', label: tr('pnlTitle') },
    { to: '/finance/cashflow', label: tr('cashflowTitle') },
    { to: '/finance/ar', label: tr('financeAR') },
  ],
  counterparties: () => [
    { to: '/counterparty-balance', label: tr('counterpartyBalance') },
    { to: '/counterparty-loans', label: tr('counterpartyLoans') },
  ],
  expenses: () => [
    { to: '/expenses', label: tr('expenses') },
    { to: '/planned-expenses', label: tr('plannedExpenses') },
  ],
  bank: () => [
    { to: '/bank', label: tr('bankTransactions') },
    { to: '/bank-import', label: tr('bankImport') },
  ],
}

export default function PageTabs({ group }) {
  const tabs = TAB_GROUPS[group]()
  return (
    <div className="page-tabs no-print">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) => `page-tab${isActive ? ' active' : ''}`}
        >
          {tab.label}
        </NavLink>
      ))}
    </div>
  )
}
