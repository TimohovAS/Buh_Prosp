import { useCallback } from 'react'
import { contractMatchesProject } from '../utils/entityLabels'

export default function useProjectContractForm({
  contracts,
  setForm,
  projectField = 'project_id',
  contractField = 'contract_id',
}) {
  const updateProject = useCallback((projectId) => {
    setForm((previous) => {
      const selectedContract = previous[contractField]
        ? contracts.find((contract) => String(contract.id) === String(previous[contractField]))
        : null
      const keepContract = contractMatchesProject(selectedContract, projectId)
      return {
        ...previous,
        [projectField]: projectId,
        [contractField]: keepContract ? previous[contractField] : '',
      }
    })
  }, [contractField, contracts, projectField, setForm])

  const updateContract = useCallback((contractId) => {
    setForm((previous) => {
      if (!contractId) {
        return { ...previous, [contractField]: '' }
      }
      const selectedContract = contracts.find((contract) => String(contract.id) === String(contractId))
      return {
        ...previous,
        [contractField]: contractId,
        [projectField]: selectedContract?.project_id ? String(selectedContract.project_id) : previous[projectField],
      }
    })
  }, [contractField, contracts, projectField, setForm])

  return { updateProject, updateContract }
}
