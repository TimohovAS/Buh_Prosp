import { useCallback, useState } from 'react'

export default function useListPageState({
  initialSearch = '',
  initialSortCol = '',
  initialSortAsc = true,
} = {}) {
  const [search, setSearch] = useState(initialSearch)
  const [sortCol, setSortCol] = useState(initialSortCol)
  const [sortAsc, setSortAsc] = useState(initialSortAsc)

  const toggleSort = useCallback((column) => {
    setSortCol((current) => {
      if (current === column) {
        setSortAsc((value) => !value)
        return current
      }
      setSortAsc(true)
      return column
    })
  }, [])

  return {
    search,
    setSearch,
    sortCol,
    sortAsc,
    setSortCol,
    setSortAsc,
    toggleSort,
  }
}
