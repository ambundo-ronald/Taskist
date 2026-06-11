"""Fast repository checks that do not require a running Frappe site."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
	errors: list[str] = []
	python_files = list((ROOT / "taskist").rglob("*.py"))
	json_files = list((ROOT / "taskist").rglob("*.json"))

	for path in python_files:
		try:
			ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
		except (SyntaxError, UnicodeDecodeError) as exc:
			errors.append(f"{path.relative_to(ROOT)}: {exc}")

	for path in json_files:
		try:
			json.loads(path.read_text(encoding="utf-8"))
		except (json.JSONDecodeError, UnicodeDecodeError) as exc:
			errors.append(f"{path.relative_to(ROOT)}: {exc}")

	if errors:
		print("Repository validation failed:")
		for error in errors:
			print(f"- {error}")
		return 1

	print(f"Validated {len(python_files)} Python files and {len(json_files)} JSON files.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
