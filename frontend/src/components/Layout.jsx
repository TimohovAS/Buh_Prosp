import { Outlet, NavLink } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import { useEnterpriseBrand } from '../hooks/useEnterpriseBrand'
import {
  LayoutDashboard,
  LineChart,
  Wallet,
  AlertCircle,
  FileText,
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

export default function Layout({ lang, toggleLang }) {
  const brand = useEnterpriseBrand()
  const enterpriseName = brand.name && brand.name !== 'ProspEl' ? brand.name : ''

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
              <li><NavLink to="/finance/cashflow"><Wallet size={18} /> {tr('cashflowTitle')}</NavLink></li>
              <li><NavLink to="/finance/ar"><AlertCircle size={18} /> {tr('financeAR')}</NavLink></li>
            </ul>
          </div>

          <div className="sidebar-group">
            <div className="sidebar-group-title">Операции</div>
            <ul className="sidebar-nav">
              <li><NavLink to="/income"><FileText size={18} /> {tr('income')}</NavLink></li>
              <li><NavLink to="/expenses"><CreditCard size={18} /> {tr('expenses')}</NavLink></li>
              <li><NavLink to="/planned-expenses"><CalendarDays size={18} /> {tr('plannedExpenses')}</NavLink></li>
              <li><NavLink to="/payments"><Landmark size={18} /> {tr('payments')}</NavLink></li>
            </ul>
          </div>

          <div className="sidebar-group">
            <div className="sidebar-group-title">Банка</div>
            <ul className="sidebar-nav">
              <li><NavLink to="/bank"><Building2 size={18} /> {tr('bankTransactions')}</NavLink></li>
              <li><NavLink to="/bank-import"><ArrowRightLeft size={18} /> {tr('bankImport')}</NavLink></li>
              <li><NavLink to="/cash"><Wallet size={18} /> {tr('cashRegister')}</NavLink></li>
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
        <Outlet />
      </main>
    </div>
  )
}