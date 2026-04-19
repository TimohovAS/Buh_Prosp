// В dev — через proxy Vite (чтобы избежать CORS и Failed to fetch)
const API_BASE = '/api';
export const PENDING_LINKS_UPDATE_EVENT = 'pending-links-updated';

let token = null;

function shouldBroadcastPendingLinksUpdate(endpoint, options = {}) {
  const method = String(options.method || 'GET').toUpperCase();
  if (method === 'GET') return false;
  return (
    endpoint.startsWith('/bank-transactions') ||
    endpoint.startsWith('/incoming-invoices') ||
    endpoint.startsWith('/bank-import') ||
    endpoint.startsWith('/efaktura')
  );
}

export function broadcastPendingLinksUpdate() {
  window.dispatchEvent(new CustomEvent(PENDING_LINKS_UPDATE_EVENT));
}

export function setToken(t) {
  token = t;
  if (t) localStorage.setItem('prospel_token', t);
  else localStorage.removeItem('prospel_token');
}

export function setUser(u) {
  if (u) localStorage.setItem('prospel_user', JSON.stringify(u));
  else localStorage.removeItem('prospel_user');
}

export function getUser() {
  try {
    const s = localStorage.getItem('prospel_user');
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}

export function getToken() {
  if (!token) token = localStorage.getItem('prospel_token');
  return token;
}

async function request(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  const t = getToken();
  if (t) headers['Authorization'] = `Bearer ${t}`;

  const res = await fetch(API_BASE + endpoint, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    setToken(null);
    setUser(null);
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const msg = typeof err.detail === 'string' ? err.detail : (Array.isArray(err.detail) ? err.detail.map(e => e.msg).join(', ') : err.message || `HTTP ${res.status}`);
    window.dispatchEvent(new CustomEvent('api-error', { detail: msg }));
    const e = new Error(msg);
    e.status = res.status;
    throw e;
  }

  if (shouldBroadcastPendingLinksUpdate(endpoint, options)) {
    broadcastPendingLinksUpdate();
  }

  const contentType = res.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return res.json();
  }
  return res;
}

const dashboardApi = () => request('/dashboard');
dashboardApi.pendingLinks = () => request('/dashboard/pending-links');

export const api = {
  auth: {
    login: (username, password) => {
      const params = new URLSearchParams();
      params.append('username', username);
      params.append('password', password);
      return fetch(API_BASE + '/auth/login', {
        method: 'POST',
        body: params,
        headers: { Accept: 'application/json' },
      }).then(async (r) => {
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          const msg = e.detail || 'Неверный логин или пароль';
          window.dispatchEvent(new CustomEvent('api-error', { detail: msg }));
          throw new Error(msg);
        }
        const data = await r.json();
        setToken(data.access_token);
        setUser(data.user);
        return data;
      });
    },
    logout: () => { setToken(null); setUser(null); },
    updateMe: (data) => request('/auth/me', { method: 'PATCH', body: JSON.stringify(data) }),
  },

  users: {
    list: (includeInactive) => request(`/users?include_inactive=${includeInactive || false}`),
    get: (id) => request(`/users/${id}`),
    create: (data) => request('/users', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    deactivate: (id) => request(`/users/${id}`, { method: 'DELETE' }),
  },

  income: {
    list: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/income?${q}`);
    },
    years: () => request('/income/years'),
    get: (id) => request(`/income/${id}`),
    payments: (id) => request(`/income/${id}/payments`),
    clearManualPayment: (id) => request(`/income/${id}/clear-manual-payment`, { method: 'POST' }),
    create: (data) => request('/income', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/income/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id) => request(`/income/${id}`, { method: 'DELETE' }),
    bulkAssignProject: (data) => request('/income/bulk-assign-project', { method: 'POST', body: JSON.stringify(data) }),
    nextInvoice: (year) => request(`/income/next-invoice-number?year=${year || new Date().getFullYear()}`),
    checkInvoice: (invoiceNumber, year) => request(`/income/check-invoice?invoice_number=${encodeURIComponent(invoiceNumber)}&year=${year || new Date().getFullYear()}`),
    importEfaktura: async (files) => {
      const formData = new FormData();
      files.forEach((file) => formData.append('files', file));
      const t = getToken();
      const headers = t ? { Authorization: `Bearer ${t}` } : {};
      const res = await fetch(API_BASE + '/income/import-efaktura', {
        method: 'POST',
        body: formData,
        headers,
      });
      if (res.status === 401) {
        setToken(null);
        setUser(null);
        window.location.href = '/login';
        throw new Error('Unauthorized');
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = err.detail || `HTTP ${res.status}`;
        window.dispatchEvent(new CustomEvent('api-error', { detail: msg }));
        throw new Error(msg);
      }
      return res.json();
    },
  },

  efaktura: {
    settings: () => request('/efaktura/settings'),
    updateSettings: (data) => request('/efaktura/settings', { method: 'PUT', body: JSON.stringify(data) }),
    history: (limit = 100) => request(`/efaktura/history?limit=${limit}`),
    sync: () => request('/efaktura/sync', { method: 'POST' }),
    importXml: async (files) => {
      const formData = new FormData();
      files.forEach((file) => formData.append('files', file));
      const t = getToken();
      const headers = t ? { Authorization: `Bearer ${t}` } : {};
      const res = await fetch(API_BASE + '/efaktura/import-xml', {
        method: 'POST',
        body: formData,
        headers,
      });
      if (res.status === 401) {
        setToken(null);
        setUser(null);
        window.location.href = '/login';
        throw new Error('Unauthorized');
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = err.detail || `HTTP ${res.status}`;
        window.dispatchEvent(new CustomEvent('api-error', { detail: msg }));
        throw new Error(msg);
      }
      const payload = await res.json();
      broadcastPendingLinksUpdate();
      return payload;
    },
  },

  finance: {
    summary: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/finance/summary?${q}`);
    },
    limits: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/finance/limits${q ? `?${q}` : ''}`);
    },
    pnl: (year) => request(`/finance/pnl?year=${year}`),
    pnlYears: () => request('/finance/pnl/years'),
    ar: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/finance/ar${q ? `?${q}` : ''}`);
    },
    cashflow: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/finance/cashflow?${q}`);
    },
    byProject: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/finance/by-project?${q}`);
    },
    projectMovements: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/finance/project-movements?${q}`);
    },
  },
  projects: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString()
      return request(`/projects?${q}`)
    },
    get: (id) => request(`/projects/${id}`),
    create: (data) => request('/projects', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id) => request(`/projects/${id}`, { method: 'DELETE' }),
  },
  receipts: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString()
      return request(`/receipts${q ? `?${q}` : ''}`)
    },
    get: (id) => request(`/receipts/${id}`),
    importFromQr: (data) => request('/receipts/import-from-qr', { method: 'POST', body: JSON.stringify(data) }),
    expenseCandidates: (id) => request(`/receipts/${id}/expense-candidates`),
    assignProject: (id, data) => request(`/receipts/${id}/assign-project`, { method: 'POST', body: JSON.stringify(data) }),
    linkExpense: (id, data) => request(`/receipts/${id}/link-expense`, { method: 'POST', body: JSON.stringify(data) }),
    createExpense: (id, data) => request(`/receipts/${id}/create-expense`, { method: 'POST', body: JSON.stringify(data) }),
    unlinkExpense: (id) => request(`/receipts/${id}/unlink-expense`, { method: 'POST' }),
    delete: (id) => request(`/receipts/${id}`, { method: 'DELETE' }),
    byProject: (projectId, params = {}) => {
      const q = new URLSearchParams(params).toString()
      return request(`/receipts/by-project/${projectId}${q ? `?${q}` : ''}`)
    },
  },

  categories: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString()
      return request(`/categories?${q}`)
    },
    create: (data) => request('/categories', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/categories/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },

  contracts: {
    list: (params) => {
      const q = new URLSearchParams(params || {}).toString();
      return request(`/contracts?${q}`);
    },
    get: (id) => request(`/contracts/${id}`),
    create: (data) => request('/contracts/create', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/contracts/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id) => request(`/contracts/${id}`, { method: 'DELETE' }),
    nextNumber: (year) => request(`/contracts/next-number/?year=${year ?? new Date().getFullYear()}`),
  },

  clients: {
    list: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/clients?${q}`);
    },
    listBrief: (search) => request(`/clients/brief?search=${encodeURIComponent(search || '')}`),
    get: (id) => request(`/clients/${id}`),
    create: (data) => request('/clients', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/clients/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id) => request(`/clients/${id}`, { method: 'DELETE' }),
  },

  expenses: {
    list: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/expenses?${q}`);
    },
    duplicates: (params) => {
      const q = new URLSearchParams(params || {}).toString();
      return request(`/expenses/duplicates?${q}`);
    },
    years: () => request('/expenses/years'),
    mergeDuplicates: (data) => request('/expenses/merge-duplicates', { method: 'POST', body: JSON.stringify(data) }),
    get: (id) => request(`/expenses/${id}`),
    create: (data) => request('/expenses', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/expenses/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    reverse: (id, data) => request(`/expenses/${id}/reverse`, { method: 'PATCH', body: JSON.stringify(data || {}) }),
    bulkAssignProject: (data) => request('/expenses/bulk-assign-project', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id) => request(`/expenses/${id}`, { method: 'DELETE' }),
  },

  plannedExpenses: {
    list: (params) => {
      const q = new URLSearchParams(params || {}).toString();
      return request(`/planned-expenses?${q}`);
    },
    upcoming: (days = 60) => request(`/planned-expenses/upcoming?days=${days}`),
    markPaid: (data) => request('/planned-expenses/mark-paid', { method: 'POST', body: JSON.stringify(data) }),
    markUnpaid: (data) => request('/planned-expenses/mark-unpaid', { method: 'POST', body: JSON.stringify(data) }),
    get: (id) => request(`/planned-expenses/${id}`),
    create: (data) => request('/planned-expenses', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/planned-expenses/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id) => request(`/planned-expenses/${id}`, { method: 'DELETE' }),
  },

  obligations: {
    types: () => request('/obligations/types'),
    years: () => request('/obligations/years'),
    calendar: (year, paymentType) => {
      let url = `/obligations/calendar?year=${year}`;
      if (paymentType) url += `&payment_type=${paymentType}`;
      return request(url);
    },
    decisions: (year) => request(`/obligations/decisions${year ? `?year=${year}` : ''}`),
    getDecision: (id) => request(`/obligations/decisions/${id}`),
    createDecision: (data) => request('/obligations/decisions', { method: 'POST', body: JSON.stringify(data) }),
    updateDecision: (id, data) => request(`/obligations/decisions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    applyPreset2026: () => request('/obligations/decisions/apply-preset-2026', { method: 'POST' }),
    generate: (year) => request(`/obligations/generate?year=${year}`, { method: 'POST' }),
    markPaid: (id, data) => request(`/obligations/obligations/${id}/mark-paid`, { method: 'PATCH', body: JSON.stringify(data) }),
    markUnpaid: (id) => request(`/obligations/obligations/${id}/mark-unpaid`, { method: 'PATCH' }),
    ipsQr: (id) => request(`/obligations/obligations/${id}/ips-qr`),
    summary: (year) => request(`/obligations/summary${year ? `?year=${year}` : ''}`),
  },

  dashboard: dashboardApi,
  bankImport: {
    parse: async (files) => {
      const formData = new FormData();
      for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
      }
      const t = getToken();
      const headers = t ? { Authorization: `Bearer ${t}` } : {};
      const res = await fetch(API_BASE + '/bank-import/parse', {
        method: 'POST',
        body: formData,
        headers,
      });
      if (res.status === 401) {
        setToken(null);
        setUser(null);
        window.location.href = '/login';
        throw new Error('Unauthorized');
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = err.detail || `HTTP ${res.status}`;
        window.dispatchEvent(new CustomEvent('api-error', { detail: msg }));
        throw new Error(msg);
      }
      return res.json();
    },
    apply: (data) => request('/bank-import/apply', { method: 'POST', body: JSON.stringify(data) }),
    recentFiles: (limit = 10) => request(`/bank-import/files?limit=${limit}`),
  },
  bankTransactions: {
    list: async (params) => {
      const q = new URLSearchParams(params).toString()
      return request(`/bank-transactions?${q}`)
    },
    years: () => request('/bank-transactions/years'),
    update: (id, payload) => request(`/bank-transactions/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
    match: (id, payload) => request(`/bank-transactions/${id}/match`, { method: 'POST', body: JSON.stringify(payload) }),
    classifyOwnerFunds: (id) => request(`/bank-transactions/${id}/owner-funds`, { method: 'POST' }),
    incomeAllocation: (id) => request(`/bank-transactions/${id}/income-allocation`),
    saveIncomeAllocation: (id, payload) => request(`/bank-transactions/${id}/income-allocation`, { method: 'POST', body: JSON.stringify(payload) }),
    createExpense: (id, payload) => request(`/bank-transactions/${id}/create-expense`, { method: 'POST', body: JSON.stringify(payload) }),
    unmatch: (id) => request(`/bank-transactions/${id}/unmatch`, { method: 'POST' }),
    suggest: (id) => request(`/bank-transactions/${id}/suggest`),
    bulkAssignProject: (payload) => request('/bank-transactions/bulk-assign-project', { method: 'POST', body: JSON.stringify(payload) }),
  },
  cash: {
    summary: (params = {}) => {
      const q = new URLSearchParams(params).toString()
      return request(`/cash${q ? `?${q}` : ''}`)
    },
    years: () => request('/cash/years'),
    updateEntry: (id, data) => request(`/cash/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    createWithdrawal: (data) => request('/cash/withdrawals', { method: 'POST', body: JSON.stringify(data) }),
    createExpense: (data) => request('/cash/expenses', { method: 'POST', body: JSON.stringify(data) }),
    createAdjustment: (data) => request('/cash/adjustments', { method: 'POST', body: JSON.stringify(data) }),
  },
  enterprise: {
    get: () => request('/enterprise'),
    branding: () => request('/enterprise/branding'),
    update: (data) => request('/enterprise', { method: 'PUT', body: JSON.stringify(data) }),
  },

  service: {
    backups: () => request('/service/backups'),
    updateSettings: (data) => request('/service/backups/settings', { method: 'PUT', body: JSON.stringify(data) }),
    createBackup: () => request('/service/backups', { method: 'POST' }),
    restoreBackup: (name) => request(`/service/backups/${encodeURIComponent(name)}/restore`, { method: 'POST' }),
    async downloadBackup(name) {
      const res = await fetch(`${API_BASE}/service/backups/${encodeURIComponent(name)}/download`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) {
        window.dispatchEvent(new CustomEvent('api-error', { detail: 'Ошибка загрузки' }));
        throw new Error('Ошибка загрузки');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = name;
      link.click();
      URL.revokeObjectURL(url);
    },
  },

  incomingInvoices: {
    list: (params) => {
      const q = new URLSearchParams(params || {}).toString();
      return request(`/incoming-invoices?${q}`);
    },
      years: () => request('/incoming-invoices/years'),
      get: (id) => request(`/incoming-invoices/${id}`),
      create: (data) => request('/incoming-invoices', { method: 'POST', body: JSON.stringify(data) }),
      update: (id, data) => request(`/incoming-invoices/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
      cancel: (id) => request(`/incoming-invoices/${id}/cancel`, { method: 'POST' }),
      restore: (id) => request(`/incoming-invoices/${id}/restore`, { method: 'POST' }),
      expenseCandidates: (id) => request(`/incoming-invoices/${id}/expense-candidates`),
      advanceCandidates: (id) => request(`/incoming-invoices/${id}/advance-candidates`),
      closingCandidates: (id) => request(`/incoming-invoices/${id}/closing-candidates`),
      attachExpense: (id, data) => request(`/incoming-invoices/${id}/attach-expense`, { method: 'POST', body: JSON.stringify(data) }),
      linkAdvance: (id, data) => request(`/incoming-invoices/${id}/link-advance`, { method: 'POST', body: JSON.stringify(data) }),
      linkClosing: (id, data) => request(`/incoming-invoices/${id}/link-closing`, { method: 'POST', body: JSON.stringify(data) }),
      unlinkAdvance: (id) => request(`/incoming-invoices/${id}/unlink-advance`, { method: 'POST' }),
      settleBank: (id, data) => request(`/incoming-invoices/${id}/settle/bank`, { method: 'POST', body: JSON.stringify(data) }),
      settleCash: (id, data) => request(`/incoming-invoices/${id}/settle/cash`, { method: 'POST', body: JSON.stringify(data) }),
      settleOffset: (id, data) => request(`/incoming-invoices/${id}/settle/offset`, { method: 'POST', body: JSON.stringify(data) }),
    reverseSettlement: (id) => request(`/incoming-invoices/settlements/${id}`, { method: 'DELETE' }),
    counterpartyBalance: (params) => {
      const q = new URLSearchParams(params || {}).toString();
      return request(`/incoming-invoices/counterparty-balance?${q}`);
    },
    openIncomes: (clientId) => request(`/incoming-invoices/open-incomes/${clientId}`),
  },

  reports: {
    kpoCsvUrl: (year, month) => {
      let url = `${API_BASE}/reports/kpo/csv?year=${year}`;
      if (month) url += `&month=${month}`;
      return url;
    },
    kpoPdfUrl: (year, month) => {
      let url = `${API_BASE}/reports/kpo/pdf?year=${year}`;
      if (month) url += `&month=${month}`;
      return url;
    },
    async downloadPdf(year, month) {
      const url = this.kpoPdfUrl(year, month);
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) {
        window.dispatchEvent(new CustomEvent('api-error', { detail: 'Ошибка загрузки' }));
        throw new Error('Ошибка загрузки');
      }
      const blob = await res.blob();
      const u = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = u;
      a.download = `kpo_${year}${month ? `_${month}` : ''}.pdf`;
      a.click();
      URL.revokeObjectURL(u);
    },
    async downloadOwnerFundsPdf(txId) {
      const res = await fetch(`${API_BASE}/reports/bank-transactions/${txId}/owner-funds/pdf`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = err.detail || 'Ошибка загрузки';
        window.dispatchEvent(new CustomEvent('api-error', { detail: msg }));
        throw new Error(msg);
      }
      const blob = await res.blob();
      const disposition = res.headers.get('content-disposition') || '';
      const match = disposition.match(/filename=([^;]+)/i);
      const fileName = match ? match[1].replace(/"/g, '') : `owner_funds_${txId}.pdf`;
      const u = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = u;
      a.download = fileName;
      a.click();
      URL.revokeObjectURL(u);
    },
    async downloadCsv(year, month) {
      const url = this.kpoCsvUrl(year, month);
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) {
        window.dispatchEvent(new CustomEvent('api-error', { detail: 'Ошибка загрузки' }));
        throw new Error('Ошибка загрузки');
      }
      const blob = await res.blob();
      const u = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = u;
      a.download = `kpo_${year}${month ? `_${month}` : ''}.csv`;
      a.click();
      URL.revokeObjectURL(u);
    },
  },
};
