import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, useLocation, matchPath } from 'react-router-dom'
import { getToken, setUser, getUser, api } from './api'
import { getLang, setLang, tr } from './i18n'
import ToastProvider from './components/ToastProvider'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Income from './pages/Income'
import Clients from './pages/Clients'
import Contracts from './pages/Contracts'
import Settings from './pages/Settings'
import Expenses from './pages/Expenses'
import PlannedExpenses from './pages/PlannedExpenses'
import BankImport from './pages/BankImport'
import BankTransactions from './pages/BankTransactions'
import FinanceOverview from './pages/FinanceOverview'
import ProfitAndLoss from './pages/ProfitAndLoss'
import AccountsReceivable from './pages/AccountsReceivable'
import CashFlow from './pages/CashFlow'
import CashRegister from './pages/CashRegister'
import Projects from './pages/Projects'
import Obligations from './pages/Obligations'
import Efaktura from './pages/Efaktura'
import IncomingInvoices from './pages/IncomingInvoices'
import CounterpartyBalance from './pages/CounterpartyBalance'
import Receipts from './pages/Receipts'
import CounterpartyLoans from './pages/CounterpartyLoans'

const APP_PAGE_ROUTES = [
  { id: 'dashboard', path: '/', Component: Dashboard },
  { id: 'income', path: '/income', Component: Income },
  { id: 'efaktura', path: '/efaktura', Component: Efaktura },
  { id: 'incoming-invoices', path: '/incoming-invoices', Component: IncomingInvoices },
  { id: 'counterparty-balance', path: '/counterparty-balance', Component: CounterpartyBalance },
  { id: 'counterparty-loans', path: '/counterparty-loans', Component: CounterpartyLoans },
  { id: 'clients', path: '/clients', Component: Clients },
  { id: 'finance', path: '/finance', Component: FinanceOverview },
  { id: 'finance-pnl', path: '/finance/pnl', Component: ProfitAndLoss },
  { id: 'finance-ar', path: '/finance/ar', Component: AccountsReceivable },
  { id: 'finance-cashflow', path: '/finance/cashflow', Component: CashFlow },
  { id: 'cash', path: '/cash', Component: CashRegister },
  { id: 'projects', path: '/projects', Component: Projects },
  { id: 'payments', path: '/payments', Component: Obligations },
  { id: 'contracts', path: '/contracts', Component: Contracts },
  { id: 'expenses', path: '/expenses', Component: Expenses },
  { id: 'receipts', path: '/receipts', Component: Receipts },
  { id: 'planned-expenses', path: '/planned-expenses', Component: PlannedExpenses },
  { id: 'bank-import', path: '/bank-import', Component: BankImport },
  { id: 'bank', path: '/bank', Component: BankTransactions },
  { id: 'settings', path: '/settings', Component: Settings },
]

function ProtectedRoute({ children }) {
  const [checking, setChecking] = useState(true)
  const [authenticated, setAuthenticated] = useState(false)

  useEffect(() => {
    setAuthenticated(!!getToken())
    setChecking(false)
  }, [])

  if (checking) return <div style={{ padding: '2rem', textAlign: 'center' }}>{tr('loading')}</div>
  if (!authenticated) return <Navigate to="/login" replace />
  return children
}

function PersistentPages() {
  const location = useLocation()
  const activeRoute = APP_PAGE_ROUTES.find((route) =>
    !!matchPath({ path: route.path, end: true }, location.pathname),
  )
  const [visitedRouteIds, setVisitedRouteIds] = useState(() => (activeRoute ? [activeRoute.id] : []))

  useEffect(() => {
    if (!activeRoute) return
    setVisitedRouteIds((prev) => (prev.includes(activeRoute.id) ? prev : [...prev, activeRoute.id]))
  }, [activeRoute])

  if (!activeRoute) {
    return <Navigate to="/" replace />
  }

  return APP_PAGE_ROUTES
    .filter((route) => visitedRouteIds.includes(route.id))
    .map((route) => {
      const PageComponent = route.Component
      const isActive = route.id === activeRoute.id
      return (
        <div
          key={route.id}
          className={`route-cache-slot${isActive ? ' active' : ''}`}
          aria-hidden={!isActive}
        >
          <PageComponent />
        </div>
      )
    })
}

function App() {
  const [lang, setLangState] = useState(getLang())

  useEffect(() => {
    const user = getUser()
    if (getToken() && user?.default_language && user.default_language !== getLang()) {
      setLang(user.default_language)
      setLangState(user.default_language)
    }
  }, [])

  // Allow users to copy text inside clickable rows (`.record-row`) without
  // the row's onClick firing. Without this guard a drag-to-select or a
  // double-click-to-select inside a table cell opens the row's detail
  // modal as soon as the mouse releases, making it impossible to copy
  // visible text. The handler runs in the capture phase so it can stop
  // React's delegated onClick before it bubbles up.
  useEffect(() => {
    let downX = 0
    let downY = 0
    const onMouseDown = (event) => {
      downX = event.clientX
      downY = event.clientY
    }
    const onClickCapture = (event) => {
      const row = event.target?.closest?.('.record-row')
      if (!row) return
      // Don't swallow clicks on form controls / links / explicit click targets
      // (checkboxes, buttons, anchors) inside the row.
      if (event.target.closest?.('input, button, a, select, textarea, label')) return
      const dx = Math.abs(event.clientX - downX)
      const dy = Math.abs(event.clientY - downY)
      if (dx > 4 || dy > 4) {
        event.stopImmediatePropagation()
        return
      }
      const selection = window.getSelection?.()
      if (selection && selection.rangeCount > 0 && selection.toString().trim()) {
        event.stopImmediatePropagation()
      }
    }
    document.addEventListener('mousedown', onMouseDown, true)
    document.addEventListener('click', onClickCapture, true)
    return () => {
      document.removeEventListener('mousedown', onMouseDown, true)
      document.removeEventListener('click', onClickCapture, true)
    }
  }, [])

  const handleLoginSuccess = (data) => {
    const lang = data.user?.default_language || 'sr'
    setLang(lang)
    setLangState(lang)
  }

  const toggleLang = async () => {
    const next = lang === 'sr' ? 'ru' : 'sr'
    setLang(next)
    setLangState(next)
    try {
      const updated = await api.auth.updateMe({ default_language: next })
      if (updated) setUser(updated)
    } catch {
    }
  }

  return (
    <>
      <Routes>
        <Route path="/login" element={<Login onLoginSuccess={handleLoginSuccess} />} />
        <Route
          path="*"
          element={
            <ProtectedRoute>
              <Layout lang={lang} toggleLang={toggleLang}>
                <PersistentPages />
              </Layout>
            </ProtectedRoute>
          }
        />
      </Routes>
      <ToastProvider />
    </>
  )
}

export default App
