import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { api, PENDING_LINKS_UPDATE_EVENT } from '../api'
import { tr } from '../i18n'
import { useEnterpriseBrand } from '../hooks/useEnterpriseBrand'
import {
  LayoutDashboard,
  LineChart,
  Wallet,
  AlertCircle,
  FileText,
  FileInput,
  Scale,
  CreditCard,
  CalendarDays,
  Landmark,
  Building2,
  ArrowRightLeft,
  Users,
  Briefcase,
  FolderKanban,
  QrCode,
  Settings,
  LogOut,
  Menu,
  X,
  AlertTriangle,
} from 'lucide-react'

const DEFAULT_PRODUCTION_HOSTS = ['192.168.10.20']

function normalizeHost(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .split('/')[0]
    .split(':')[0]
}

function getProductionHosts() {
  const configured = import.meta.env.VITE_PRODUCTION_HOSTS || ''
  const hosts = configured.split(',').map(normalizeHost).filter(Boolean)
  return hosts.length ? hosts : DEFAULT_PRODUCTION_HOSTS
}

function isProductionHost() {
  if (typeof window === 'undefined') return true
  const currentHost = normalizeHost(window.location.hostname)
  return getProductionHosts().includes(currentHost)
}

export default function Layout({ lang, toggleLang, children }) {
  const location = useLocation()
  const brand = useEnterpriseBrand()
  const enterpriseName = brand.name && brand.name !== 'ProspEl' ? brand.name : ''
  const showNonProductionBanner = !isProductionHost()
  const currentHostLabel = typeof window === 'undefined' ? '' : window.location.host
  const [pendingCounts, setPendingCounts] = useState({
    bank_unmatched_count: 0,
    incoming_invoices_pending_count: 0,
  })
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  async function refreshPendingCounts() {
    try {
      const data = await api.dashboard.pendingLinks()
      setPendingCounts({
        bank_unmatched_count: Number(data?.bank_unmatched_count || 0),
        incoming_invoices_pending_count: Number(data?.incoming_invoices_pending_count || 0),
      })
    } catch {}
  }

  useEffect(() => {
    refreshPendingCounts()
  }, [location.pathname])

  useEffect(() => {
    setMobileNavOpen(false)
  }, [location.pathname])

  useEffect(() => {
    const handleRefresh = () => {
      refreshPendingCounts()
    }

    window.addEventListener(PENDING_LINKS_UPDATE_EVENT, handleRefresh)
    window.addEventListener('focus', handleRefresh)
    return () => {
      window.removeEventListener(PENDING_LINKS_UPDATE_EVENT, handleRefresh)
      window.removeEventListener('focus', handleRefresh)
    }
  }, [])

  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const previousOverflow = document.body.style.overflow
    if (mobileNavOpen) {
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [mobileNavOpen])

  const incomingInvoicesBadge =
    pendingCounts.incoming_invoices_pending_count > 0
      ? ` (${pendingCounts.incoming_invoices_pending_count})`
      : ''
  const bankTransactionsBadge =
    pendingCounts.bank_unmatched_count > 0 ? ` (${pendingCounts.bank_unmatched_count})` : ''

  return (
    <div className={`app${mobileNavOpen ? ' mobile-nav-open' : ''}`}>
      <button
        type="button"
        className="mobile-nav-overlay"
        aria-label="Close navigation"
        onClick={() => setMobileNavOpen(false)}
      />
      <aside className={`sidebar${mobileNavOpen ? ' open' : ''}`}>
        <div className="sidebar-brand">
          <div className="sidebar-brand-main">
            <div className="brand-mark" aria-hidden="true">
              {brand.emblem_data_url ? <img src={brand.emblem_data_url} alt="" /> : <Building2 size={20} />}
            </div>
            <div className="sidebar-brand-copy">
              <strong style={{ fontSize: '1.25rem' }}>
                ProspEl <span style={{ fontSize: '0.75rem', opacity: 0.7 }}>v2</span>
              </strong>
              {enterpriseName ? <div className="sidebar-brand-subtitle">{enterpriseName}</div> : null}
            </div>
          </div>
          <button
            onClick={toggleLang}
            className="btn btn-sm btn-secondary"
            title={lang === 'sr' ? tr('langRu') : tr('langSr')}
          >
            {lang === 'sr' ? 'RU' : 'SR'}
          </button>
          <button
            type="button"
            className="mobile-sidebar-close"
            aria-label="Close navigation"
            onClick={() => setMobileNavOpen(false)}
          >
            <X size={18} />
          </button>
        </div>
        <nav
          style={{ flex: 1, overflowY: 'auto', paddingBottom: '1rem' }}
          onClick={(event) => {
            if (event.target.closest('a')) {
              setMobileNavOpen(false)
            }
          }}
        >
          <div className="sidebar-group">
            <div className="sidebar-group-title">{tr('sidebarOverview')}</div>
            <ul className="sidebar-nav">
              <li>
                <NavLink to="/" end>
                  <LayoutDashboard size={18} /> {tr('dashboard')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/finance" end>
                  <LineChart size={18} /> {tr('finance')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/finance/pnl">
                  <LineChart size={18} /> {tr('pnlTitle')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/finance/cashflow">
                  <Wallet size={18} /> {tr('cashflowTitle')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/finance/ar">
                  <AlertCircle size={18} /> {tr('financeAR')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/counterparty-balance">
                  <Scale size={18} /> {tr('counterpartyBalance')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/counterparty-loans">
                  <Landmark size={18} /> {tr('counterpartyLoans')}
                </NavLink>
              </li>
            </ul>
          </div>

          <div className="sidebar-group">
            <div className="sidebar-group-title">{tr('sidebarOperations')}</div>
            <ul className="sidebar-nav">
              <li>
                <NavLink to="/income">
                  <FileText size={18} /> {tr('income')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/efaktura">
                  <FileText size={18} /> {tr('efakturaModule')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/incoming-invoices">
                  <FileInput size={18} /> {tr('incomingInvoices')}
                  {incomingInvoicesBadge}
                </NavLink>
              </li>
              <li>
                <NavLink to="/expenses">
                  <CreditCard size={18} /> {tr('expenses')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/receipts">
                  <QrCode size={18} /> {tr('receipts')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/planned-expenses">
                  <CalendarDays size={18} /> {tr('plannedExpenses')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/payments">
                  <Landmark size={18} /> {tr('payments')}
                </NavLink>
              </li>
            </ul>
          </div>

          <div className="sidebar-group">
            <div className="sidebar-group-title">{tr('sidebarBank')}</div>
            <ul className="sidebar-nav">
              <li>
                <NavLink to="/bank">
                  <Building2 size={18} /> {tr('bankTransactions')}
                  {bankTransactionsBadge}
                </NavLink>
              </li>
              <li>
                <NavLink to="/cash">
                  <Wallet size={18} /> {tr('cashRegister')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/bank-import">
                  <ArrowRightLeft size={18} /> {tr('bankImport')}
                </NavLink>
              </li>
            </ul>
          </div>

          <div className="sidebar-group">
            <div className="sidebar-group-title">{tr('sidebarDirectories')}</div>
            <ul className="sidebar-nav">
              <li>
                <NavLink to="/clients">
                  <Users size={18} /> {tr('clients')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/workers">
                  <Users size={18} /> {tr('workersTitle')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/projects">
                  <FolderKanban size={18} /> {tr('projects')}
                </NavLink>
              </li>
              <li>
                <NavLink to="/contracts">
                  <Briefcase size={18} /> {tr('contracts')}
                </NavLink>
              </li>
            </ul>
          </div>

          <div className="sidebar-group">
            <div className="sidebar-group-title">{tr('sidebarSystem')}</div>
            <ul className="sidebar-nav">
              <li>
                <NavLink to="/settings">
                  <Settings size={18} /> {tr('settings')}
                </NavLink>
              </li>
            </ul>
          </div>
        </nav>
        <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
          <button
            className="btn btn-sm btn-secondary"
            style={{
              width: '100%',
              display: 'flex',
              justifyContent: 'center',
              gap: '0.5rem',
              alignItems: 'center',
            }}
            onClick={() => {
              api.auth.logout()
              window.location.href = '/login'
            }}
          >
            <LogOut size={16} /> {tr('logout')}
          </button>
        </div>
      </aside>
      <main className="main">
        <div className="mobile-topbar">
          <button
            type="button"
            className="mobile-nav-toggle"
            aria-label="Open navigation"
            onClick={() => setMobileNavOpen(true)}
          >
            <Menu size={18} />
          </button>
          <div className="mobile-topbar-copy">
            <strong>
              ProspEl <span style={{ fontSize: '0.72rem', opacity: 0.72 }}>v2</span>
            </strong>
            {enterpriseName ? <span>{enterpriseName}</span> : null}
          </div>
          <button
            onClick={toggleLang}
            className="btn btn-sm btn-secondary mobile-lang-toggle"
            title={lang === 'sr' ? tr('langRu') : tr('langSr')}
          >
            {lang === 'sr' ? 'RU' : 'SR'}
          </button>
        </div>
        {showNonProductionBanner ? (
          <div className="environment-banner" role="alert">
            <AlertTriangle size={20} aria-hidden="true" />
            <strong>{tr('nonProductionBannerTitle')}</strong>
            <span>{tr('nonProductionBannerText', { host: currentHostLabel })}</span>
          </div>
        ) : null}
        {children}
      </main>
    </div>
  )
}
