import ast
from pathlib import Path
for p in Path(".").glob("*.py"):
    ast.parse(p.read_text(encoding="utf-8"))
    print("OK", p)
print("All Python files parse successfully.")
