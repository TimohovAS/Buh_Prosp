import { useCallback, useState } from 'react'

export default function useListPageState({
  initialSearch = '',
  initialSortCol = '',
  initialSortAsc = true,
} = {}) {
  const [search, setSearch] = useState(initialSearch)
  const [sortCol, setSortCol] = useState(initialSortCol)
  const [sortAsc, setSortAsc] = useState(initialSortAsc)

  const toggleSort = useCallback(
    (column) => {
      if (sortCol === column) {
        setSortAsc((value) => !value)
      } else {
        setSortCol(column)
        setSortAsc(true)
      }
    },
    [sortCol]
  )

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
