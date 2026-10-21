"""Quality gate: no Python file over 300 lines, no function over 50 lines (src, app/api)."""

import ast
import sys
from pathlib import Path

MAX_FILE, MAX_FUNC = 300, 50
ROOTS = (Path("src"), Path("app/api"))


def main() -> int:
    problems = []
    for root in ROOTS:
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            lines = text.count("\n") + 1
            if lines > MAX_FILE:
                problems.append(f"{path}: {lines} lines (max {MAX_FILE})")
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    length = (node.end_lineno or node.lineno) - node.lineno + 1
                    if length > MAX_FUNC:
                        problems.append(f"{path}:{node.lineno} {node.name}() is {length} lines")
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
