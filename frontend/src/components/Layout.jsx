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
  Settings,
  LogOut
} from 'lucide-react'

export default function Layout({ lang, toggleLang, children }) {
  const location = useLocation()
  const brand = useEnterpriseBrand()
  const enterpriseName = brand.name && brand.name !== 'ProspEl' ? brand.name : ''
  const [pendingCounts, setPendingCounts] = useState({
    bank_unmatched_count: 0,
    incoming_invoices_pending_count: 0,
  })

  async function refreshPendingCounts() {
    try {
      const data = await api.dashboard.pendingLinks()
      setPendingCounts({
        bank_unmatched_count: Number(data?.bank_unmatched_count || 0),
        incoming_invoices_pending_count: Number(data?.incoming_invoices_pending_count || 0),
      })
    } catch {
    }
  }

  useEffect(() => {
    refreshPendingCounts()
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

  const incomingInvoicesBadge = pendingCounts.incoming_invoices_pending_count > 0
    ? ` (${pendingCounts.incoming_invoices_pending_count})`
    : ''
  const bankTransactionsBadge = pendingCounts.bank_unmatched_count > 0
    ? ` (${pendingCounts.bank_unmatched_count})`
    : ''

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-main">
            <div className="brand-mark" aria-hidden="true">
              {brand.emblem_data_url ? <img src={brand.emblem_data_url} alt="" /> : <Building2 size={20} />}
            </div>
            <div className="sidebar-brand-copy">
              <strong style={{ fontSize: '1.25rem' }}>ProspEl <span style={{ fontSize: '0.75rem', opacity: 0.7 }}>v2</span></strong>
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
        </div>
        <nav style={{ flex: 1, overflowY: 'auto', paddingBottom: '1rem' }}>
          <div className="sidebar-group">
            <div className="sidebar-group-title">Обзор</div>
            <ul className="sidebar-nav">
              <li><NavLink to="/" end><LayoutDashboard size={18} /> {tr('dashboard')}</NavLink></li>
              <li><NavLink to="/finance" end><LineChart size={18} /> {tr('finance')}</NavLink></li>
              <li><NavLink to="/finance/pnl"><LineChart size={18} /> {tr('pnlTitle')}</NavLink></li>
              <li><NavLink to="/finance/cashflow"><Wallet size={18} /> {tr('cashflowTitle')}</NavLink></li>
              <li><NavLink to="/finance/ar"><AlertCircle size={18} /> {tr('financeAR')}</NavLink></li>
              <li><NavLink to="/counterparty-balance"><Scale size={18} /> {tr('counterpartyBalance')}</NavLink></li>
            </ul>
          </div>

          <div className="sidebar-group">
            <div className="sidebar-group-title">Операции</div>
            <ul className="sidebar-nav">
              <li><NavLink to="/income"><FileText size={18} /> {tr('income')}</NavLink></li>
              <li><NavLink to="/efaktura"><FileText size={18} /> {tr('efakturaModule')}</NavLink></li>
              <li><NavLink to="/incoming-invoices"><FileInput size={18} /> {tr('incomingInvoices')}{incomingInvoicesBadge}</NavLink></li>
              <li><NavLink to="/expenses"><CreditCard size={18} /> {tr('expenses')}</NavLink></li>
              <li><NavLink to="/planned-expenses"><CalendarDays size={18} /> {tr('plannedExpenses')}</NavLink></li>
              <li><NavLink to="/payments"><Landmark size={18} /> {tr('payments')}</NavLink></li>
            </ul>
          </div>

          <div className="sidebar-group">
            <div className="sidebar-group-title">Банка</div>
            <ul className="sidebar-nav">
              <li><NavLink to="/bank"><Building2 size={18} /> {tr('bankTransactions')}{bankTransactionsBadge}</NavLink></li>
              <li><NavLink to="/cash"><Wallet size={18} /> {tr('cashRegister')}</NavLink></li>
              <li><NavLink to="/bank-import"><ArrowRightLeft size={18} /> {tr('bankImport')}</NavLink></li>
            </ul>
          </div>

          <div className="sidebar-group">
            <div className="sidebar-group-title">Справочники</div>
            <ul className="sidebar-nav">
              <li><NavLink to="/clients"><Users size={18} /> {tr('clients')}</NavLink></li>
              <li><NavLink to="/projects"><FolderKanban size={18} /> {tr('projects')}</NavLink></li>
              <li><NavLink to="/contracts"><Briefcase size={18} /> {tr('contracts')}</NavLink></li>
            </ul>
          </div>

          <div className="sidebar-group">
            <div className="sidebar-group-title">Система</div>
            <ul className="sidebar-nav">
              <li><NavLink to="/settings"><Settings size={18} /> {tr('settings')}</NavLink></li>
            </ul>
          </div>
        </nav>
        <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
          <button
            className="btn btn-sm btn-secondary"
            style={{ width: '100%', display: 'flex', justifyContent: 'center', gap: '0.5rem', alignItems: 'center' }}
            onClick={() => { api.auth.logout(); window.location.href = '/login'; }}
          >
            <LogOut size={16} /> {tr('logout')}
          </button>
        </div>
      </aside>
      <main className="main">
        {children}
      </main>
    </div>
  )
}
