import { Outlet } from 'react-router-dom'
import { NavLink } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
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
  return (
    <div className="app">
      <aside className="sidebar">
        <div style={{ padding: '2rem 1.25rem 1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <strong style={{ fontSize: '1.25rem' }}>ProspEl <span style={{ fontSize: '0.75rem', opacity: 0.7 }}>v2</span></strong>
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
              <li><NavLink to="/finance"><LineChart size={18} /> {tr('finance')}</NavLink></li>
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
            </ul>
          </div>

          <div className="sidebar-group">
            <div className="sidebar-group-title">Справочники</div>
            <ul className="sidebar-nav">
              <li><NavLink to="/clients"><Users size={18} /> {tr('clients')}</NavLink></li>
              <li><NavLink to="/contracts"><Briefcase size={18} /> {tr('contracts')}</NavLink></li>
              <li><NavLink to="/projects"><FolderKanban size={18} /> {tr('projects')}</NavLink></li>
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
