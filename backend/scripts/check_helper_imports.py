from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"

WATCHED_IMPORTS: dict[str, set[str]] = {
    "backend.decimal_utils": {
        "MONEY_PLACES",
        "ZERO_DECIMAL",
        "money_abs",
        "money_eq",
        "to_decimal",
        "format_decimal",
    },
    "backend.date_utils": {
        "coerce_date",
        "days_between",
    },
    "backend.db_utils": {
        "get_category_or_none",
        "get_category_or_404",
        "get_contract_or_404",
        "get_project_or_404",
        "get_unassigned_project_id",
        "resolve_category_expense_links",
    },
}

WATCHED_NAMES = set().union(*WATCHED_IMPORTS.values())


def scan_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    imported_names: set[str] = set()
    loaded_names: set[str] = set()
    defined_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            watched = WATCHED_IMPORTS.get(node.module)
            if watched:
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined_names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined_names.add(node.target.id)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loaded_names.add(node.id)

    available_names = imported_names | defined_names
    return sorted((loaded_names - available_names) & WATCHED_NAMES)


def main() -> int:
    failures: list[str] = []

    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        missing = scan_file(path)
        if missing:
            rel = path.relative_to(ROOT).as_posix()
            failures.append(f"{rel}: missing imports for {', '.join(missing)}")

    if failures:
        print("[ERROR] Helper import guard failed:")
        for line in failures:
            print(f"  - {line}")
        return 1

    print("[OK] Helper import guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
