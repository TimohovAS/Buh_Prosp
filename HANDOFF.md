# Handoff

## Repo
- Project: `Buh_Prosp`
- Branch: `feature/erp-project-cfo`
- Production server: `http://192.168.10.20:5173`

## Current Focus
- ERP flow built around:
  - projects as CFO centers
  - internal projects
  - expense categories
  - bank transaction matching to income/expense
  - linking expenses to projects and contracts

## Important Rules
- Do not add new frontend routes or pages.
- Use only existing pages from `frontend/src/App.jsx`.
- New UI should live inside existing pages or existing modal patterns.
- Production deploy uses `!update_prod.cmd`.
- One-time DB migrations are not run from `!update_prod.cmd`.
- Manual migrations live in `manual_migrations/`.

## Recent Key Changes
- `dc69102` `chore(ui): reorder projects and contracts menu`
- `fac7f4a` `feat(contracts): add project selection to contract form`
- `01d5a65` `fix(contracts): support legacy contract linking in expenses`
- `c13ed3b` `fix(ui): remove dashboard expenses link`
- `d88a563` `fix(ui): keep finance menu state exact`
- `603597a` `fix(obligations): use actual years in year filter`
- `c7c1474` `fix(ui): clean obligations payment placeholders`

## What Is Already Implemented
- Internal projects and default `INT-UNASSIGNED`
- Transaction categories for expenses
- Category selection in expenses and planned expenses
- Project selection required in income/expense/planned expense flows
- Searchable project picker in main forms/modals
- Bank outgoing flow creates expense linked to project and optional contract
- Legacy contracts without `project_id` can now be selected from expense/bank flows
- If such a legacy contract is chosen, backend assigns it to the selected project
- Contracts page now supports explicit project selection/editing
- Dashboard has:
  - all-time bank balance as main value
  - financial result in parentheses
  - improved top layout
- Finance menu active-state fixed
- Bank/Expenses/Income year filters were moved toward real-year lists instead of hardcoded ranges
- Obligations year filter now uses actual years from API

## Deploy Notes
- Standard deploy:

```powershell
git switch feature/erp-project-cfo
git pull
.\!update_prod.cmd
```

- Manual migrations, when needed:

```powershell
.\manual_migrations\v3_drop_project_contract_id.cmd
.\manual_migrations\v4_erp.cmd
.\manual_migrations\v5_expense_contracts.cmd
.\manual_migrations\v6_client_maticni_broj.cmd
.\manual_migrations\v7_enterprise_emblem.cmd
```

## Useful Pages To Check After Changes
- `/bank`
- `/income`
- `/expenses`
- `/contracts`
- `/projects`
- `/payments`
- `/settings`

## Known Context
- Some legacy records still have incomplete links from earlier data states.
- Contract/project consistency has been improved in UI and API, but older records may still need manual cleanup.
- There is an untracked local folder `Pictures/`; it is unrelated to the app and should not be committed blindly.

## Suggested Prompt For Cursor
```text
Read HANDOFF.md, inspect the current branch state, and continue from there.
Do not add new frontend routes/pages.
Preserve existing ERP architecture and production deploy flow.
Be careful with legacy data and project/contract links.
```
