import os

path = r"d:\Work\Programming\Buh_Prosp\frontend\src\pages\BankTransactions.jsx"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# ADD SORT STATE
state_old = """  const [suggestLoading, setSuggestLoading] = useState(false)
    const [matchError, setMatchError] = useState('')"""
state_new = """  const [suggestLoading, setSuggestLoading] = useState(false)
    const [matchError, setMatchError] = useState('')

    // Sort State
    const [sortCol, setSortCol] = useState('date')
    const [sortAsc, setSortAsc] = useState(false)"""
text = text.replace(state_old, state_new)

# ADD SORT LOGIC
filter_old = """                                {data.map(tx => ("""
filter_new = """                                {data.sort((a, b) => {
                                    let valA = a[sortCol]
                                    let valB = b[sortCol]

                                    if (sortCol === 'project_id') {
                                        valA = projects.find(p => p.id === a.project_id)?.name || ''
                                        valB = projects.find(p => p.id === b.project_id)?.name || ''
                                    }

                                    if (valA < valB) return sortAsc ? -1 : 1
                                    if (valA > valB) return sortAsc ? 1 : -1
                                    return 0
                                }).map(tx => ("""
text = text.replace(filter_old, filter_new)

# ADD TOGGLE SORT FUNCTIONS
toggle_old = """    const handleUnmatch = async (id) => {"""
toggle_new = """    const toggleSort = (col) => {
        if (sortCol === col) setSortAsc(!sortAsc)
        else { setSortCol(col); setSortAsc(true) }
    }

    const SortIcon = ({ col }) => {
        if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 4 }}>↕</span>
        return <span style={{ marginLeft: 4 }}>{sortAsc ? '↑' : '↓'}</span>
    }

    const handleUnmatch = async (id) => {"""
text = text.replace(toggle_old, toggle_new)


# UPDATE TABLE HEADERS
thead_old = """                                    <th>{tr('date')}</th>
                                    <th>{tr('bankTxCounterparty')}</th>
                                    <th>{tr('bankTxPurpose')} / {tr('bankTxReference')}</th>
                                    <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
                                    <th>{tr('filterStatus')}</th>"""
thead_new = """                                    <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIcon col="date" /></th>
                                    <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('counterparty_name')}>{tr('bankTxCounterparty')} <SortIcon col="counterparty_name" /></th>
                                    <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('purpose')}>{tr('bankTxPurpose')} / {tr('bankTxReference')} <SortIcon col="purpose" /></th>
                                    <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')} <SortIcon col="amount" /></th>
                                    <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('status')}>{tr('filterStatus')} <SortIcon col="status" /></th>"""
text = text.replace(thead_old, thead_new)

with open(path, "w", encoding="utf-8") as f:
    f.write(text)
print("Updated BankTransactions.jsx with sorting")
