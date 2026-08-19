import { useState, useEffect, lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation, matchPath } from 'react-router-dom'
import { getToken, setUser, getUser, api } from './api'
import { getLang, setLang, tr } from './i18n'
import ToastProvider from './components/ToastProvider'
import Layout from './components/Layout'
import Login from './pages/Login'
import useResizableTableColumns from './hooks/useResizableTableColumns'

// Страницы грузятся лениво: код страницы (и тяжёлые зависимости вроде
// recharts) скачивается при первом заходе на маршрут, а не на экране логина.
const APP_PAGE_ROUTES = [
  { id: 'dashboard', path: '/', Component: lazy(() => import('./pages/Dashboard')) },
  { id: 'income', path: '/income', Component: lazy(() => import('./pages/Income')) },
  { id: 'efaktura', path: '/efaktura', Component: lazy(() => import('./pages/Efaktura')) },
  {
    id: 'incoming-invoices',
    path: '/incoming-invoices',
    Component: lazy(() => import('./pages/IncomingInvoices')),
  },
  {
    id: 'counterparty-balance',
    path: '/counterparty-balance',
    Component: lazy(() => import('./pages/CounterpartyBalance')),
  },
  {
    id: 'counterparty-loans',
    path: '/counterparty-loans',
    Component: lazy(() => import('./pages/CounterpartyLoans')),
  },
  { id: 'clients', path: '/clients', Component: lazy(() => import('./pages/Clients')) },
  { id: 'workers', path: '/workers', Component: lazy(() => import('./pages/Workers')) },
  { id: 'finance', path: '/finance', Component: lazy(() => import('./pages/FinanceOverview')) },
  { id: 'finance-pnl', path: '/finance/pnl', Component: lazy(() => import('./pages/ProfitAndLoss')) },
  { id: 'finance-ar', path: '/finance/ar', Component: lazy(() => import('./pages/AccountsReceivable')) },
  { id: 'finance-cashflow', path: '/finance/cashflow', Component: lazy(() => import('./pages/CashFlow')) },
  { id: 'cash', path: '/cash', Component: lazy(() => import('./pages/CashRegister')) },
  { id: 'projects', path: '/projects', Component: lazy(() => import('./pages/Projects')) },
  { id: 'payments', path: '/payments', Component: lazy(() => import('./pages/Obligations')) },
  { id: 'contracts', path: '/contracts', Component: lazy(() => import('./pages/Contracts')) },
  { id: 'expenses', path: '/expenses', Component: lazy(() => import('./pages/Expenses')) },
  { id: 'receipts', path: '/receipts', Component: lazy(() => import('./pages/Receipts')) },
  { id: 'work-diaries', path: '/work-diaries', Component: lazy(() => import('./pages/WorkDiaries')) },
  {
    id: 'planned-expenses',
    path: '/planned-expenses',
    Component: lazy(() => import('./pages/PlannedExpenses')),
  },
  { id: 'bank-import', path: '/bank-import', Component: lazy(() => import('./pages/BankImport')) },
  { id: 'bank', path: '/bank', Component: lazy(() => import('./pages/BankTransactions')) },
  { id: 'settings', path: '/settings', Component: lazy(() => import('./pages/Settings')) },
]

function ProtectedRoute({ children }) {
  const [authStatus, setAuthStatus] = useState('checking')
  const [retryAttempt, setRetryAttempt] = useState(0)

  useEffect(() => {
    let active = true

    async function checkAuthentication() {
      if (getToken()) {
        setAuthStatus('authenticated')
        return
      }

      const restoreStatus = await api.auth.restoreSession()
      if (active) {
        setAuthStatus(
          restoreStatus === 'refreshed'
            ? 'authenticated'
            : restoreStatus === 'expired'
              ? 'unauthorized'
              : 'unavailable'
        )
      }
    }

    setAuthStatus('checking')
    checkAuthentication()
    return () => {
      active = false
    }
  }, [retryAttempt])

  if (authStatus === 'checking') {
    return <div style={{ padding: '2rem', textAlign: 'center' }}>{tr('loading')}</div>
  }
  if (authStatus === 'unavailable') {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <p>{tr('sessionCheckUnavailable')}</p>
        <button
          className="btn btn-primary"
          type="button"
          onClick={() => setRetryAttempt((value) => value + 1)}
        >
          {tr('retry')}
        </button>
      </div>
    )
  }
  if (authStatus === 'unauthorized') return <Navigate to="/login" replace />
  return children
}

function PersistentPages() {
  const location = useLocation()
  const activeRoute = APP_PAGE_ROUTES.find(
    (route) => !!matchPath({ path: route.path, end: true }, location.pathname)
  )
  const [visitedRouteIds, setVisitedRouteIds] = useState(() => (activeRoute ? [activeRoute.id] : []))

  useEffect(() => {
    if (!activeRoute) return
    setVisitedRouteIds((prev) => (prev.includes(activeRoute.id) ? prev : [...prev, activeRoute.id]))
  }, [activeRoute])

  if (!activeRoute) {
    return <Navigate to="/" replace />
  }

  return APP_PAGE_ROUTES.filter((route) => visitedRouteIds.includes(route.id)).map((route) => {
    const PageComponent = route.Component
    const isActive = route.id === activeRoute.id
    return (
      <div key={route.id} className={`route-cache-slot${isActive ? ' active' : ''}`} aria-hidden={!isActive}>
        <Suspense fallback={<div style={{ padding: '2rem', textAlign: 'center' }}>{tr('loading')}</div>}>
          <PageComponent />
        </Suspense>
      </div>
    )
  })
}

function App() {
  const [lang, setLangState] = useState(getLang())
  useResizableTableColumns()

  useEffect(() => {
    const user = getUser()
    if (user?.default_language && user.default_language !== getLang()) {
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
    } catch {}
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
