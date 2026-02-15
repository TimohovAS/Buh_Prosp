import { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { getToken, setUser, getUser, api } from './api'
import { getLang, setLang, tr } from './i18n'
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
import FinanceOverview from './pages/FinanceOverview'
import AccountsReceivable from './pages/AccountsReceivable'
import CashFlow from './pages/CashFlow'
import Projects from './pages/Projects'
import Obligations from './pages/Obligations'

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

function App() {
  const [lang, setLangState] = useState(getLang())

  useEffect(() => {
    const user = getUser()
    if (getToken() && user?.default_language && user.default_language !== getLang()) {
      setLang(user.default_language)
      setLangState(user.default_language)
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
    <Routes>
      <Route path="/login" element={<Login onLoginSuccess={handleLoginSuccess} />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout lang={lang} toggleLang={toggleLang} />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="income" element={<Income />} />
        <Route path="clients" element={<Clients />} />
        <Route path="finance" element={<FinanceOverview />} />
        <Route path="finance/ar" element={<AccountsReceivable />} />
        <Route path="finance/cashflow" element={<CashFlow />} />
        <Route path="projects" element={<Projects />} />
        <Route path="payments" element={<Obligations />} />
        <Route path="contracts" element={<Contracts />} />
        <Route path="expenses" element={<Expenses />} />
        <Route path="planned-expenses" element={<PlannedExpenses />} />
        <Route path="bank-import" element={<BankImport />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
