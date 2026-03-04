import os

path = r"d:\Work\Programming\Buh_Prosp\frontend\src\pages\Expenses.jsx"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# ADD SORT STATE
state_old = """  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)"""
state_new = """  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [sortCol, setSortCol] = useState('date')
  const [sortAsc, setSortAsc] = useState(false)"""
text = text.replace(state_old, state_new)

# ADD SORT LOGIC
filter_old = """  const filtered = items.filter((i) => {
    if (!search) return true
    const s = search.toLowerCase()
    return (i.description || '').toLowerCase().includes(s)
  })"""
filter_new = """  const filtered = items.filter((i) => {
    if (!search) return true
    const s = search.toLowerCase()
    return (
      (i.description || '').toLowerCase().includes(s) ||
      (projects.find(p => p.id === i.project_id)?.name || '').toLowerCase().includes(s)
    )
  }).sort((a, b) => {
    let valA = a[sortCol]
    let valB = b[sortCol]
    
    // Project sort
    if (sortCol === 'project_id') {
      valA = projects.find(p => p.id === a.project_id)?.name || ''
      valB = projects.find(p => p.id === b.project_id)?.name || ''
    }

    if (valA < valB) return sortAsc ? -1 : 1
    if (valA > valB) return sortAsc ? 1 : -1
    return 0
  })

  const toggleSort = (col) => {
    if (sortCol === col) setSortAsc(!sortAsc)
    else { setSortCol(col); setSortAsc(true) }
  }

  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 4 }}>↕</span>
    return <span style={{ marginLeft: 4 }}>{sortAsc ? '↑' : '↓'}</span>
  }"""
text = text.replace(filter_old, filter_new)


# UPDATE TABLE HEADERS
thead_old = """                  <th>{tr('date')}</th>
                  <th>{tr('description')}</th>
                  <th>{tr('project')}</th>
                  <th>{tr('category')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
                  <th>{tr('status')}</th>"""
thead_new = """                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIcon col="date" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('description')}>{tr('description')} <SortIcon col="description" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('project_id')}>{tr('project')} <SortIcon col="project_id" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('category')}>{tr('category')} <SortIcon col="category" /></th>
                  <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')} <SortIcon col="amount" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('status')}>{tr('status')} <SortIcon col="status" /></th>"""
text = text.replace(thead_old, thead_new)

with open(path, "w", encoding="utf-8") as f:
    f.write(text)
print("Updated Expenses.jsx with sorting")
