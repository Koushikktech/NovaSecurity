"""Versioned author-labelled cases. Not an independent external benchmark."""

import hashlib
import json
from pathlib import Path

# Each pair supplies a behavioral regression and a clean control. Labels stay out of prompts.
FAMILIES = [
    (
        "mutable-default",
        "py",
        "def collect(item, items=[]):\n    items.append(item)\n    return items\n",
        "def collect(item, items=None):\n    items = [] if items is None else items\n    items.append(item)\n    return items\n",
        "Calls share mutable default state",
        1,
    ),
    (
        "async-batch",
        "js",
        "export async function save(items) { items.forEach(async i => await i.save()); }",
        "export async function save(items) { await Promise.all(items.map(i => i.save())); }",
        "Completion does not await saves",
        1,
    ),
    (
        "argument-contract",
        "ts",
        "export function load(id: number, page: number) { return id; }\nload(1);",
        "export function load(id: number, page = 1) { return id; }\nload(1);",
        "Caller lacks required argument",
        2,
    ),
    (
        "sql-format",
        "py",
        "def search(cursor, name):\n    return cursor.execute(f\"SELECT * FROM users WHERE name='{name}'\")\n",
        "def search(cursor, name):\n    return cursor.execute('SELECT * FROM users WHERE name=?', (name,))\n",
        "Untrusted name changes SQL structure",
        2,
    ),
    (
        "return-contract",
        "ts",
        "export function count(): number { return 'none'; }",
        "export function count(): number { return 0; }",
        "Declared numeric API returns a string",
        1,
    ),
    (
        "shell-format",
        "py",
        "import subprocess\ndef run(name):\n    return subprocess.run(f'echo {name}', shell=True)\n",
        "import subprocess\ndef run(name):\n    return subprocess.run(['echo', name], check=True)\n",
        "Shell interprets untrusted metacharacters",
        3,
    ),
    (
        "empty-list",
        "py",
        "def first(items):\n    return items[0]\n",
        "def first(items):\n    return items[0] if items else None\n",
        "Empty input raises instead of returning None",
        2,
    ),
    (
        "zero-total",
        "ts",
        "export function average(items: number[]): number { return items.reduce((a,b)=>a+b,0) / items.length; }",
        "export function average(items: number[]): number { return items.length ? items.reduce((a,b)=>a+b,0)/items.length : 0; }",
        "Empty input returns NaN instead of zero",
        1,
    ),
    (
        "sort-return",
        "py",
        "def sorted_items(items):\n    return items.sort()\n",
        "def sorted_items(items):\n    return sorted(items)\n",
        "API returns None instead of sorted collection",
        2,
    ),
    (
        "missing-await",
        "js",
        "export async function load(fetcher) { const response = fetcher(); return response.json(); }",
        "export async function load(fetcher) { const response = await fetcher(); return response.json(); }",
        "Attempts json on promise",
        1,
    ),
    (
        "null-input",
        "ts",
        "export function label(value: string | null): string { return value.toUpperCase(); }",
        "export function label(value: string | null): string { return value?.toUpperCase() ?? ''; }",
        "Nullable input dereferenced without guard",
        1,
    ),
    (
        "boolean-string",
        "py",
        "def enabled(value):\n    return bool(value)\n",
        "def enabled(value):\n    return value.lower() in {'true', '1'}\n",
        "String false is interpreted as enabled",
        2,
    ),
    (
        "slice-boundary",
        "js",
        "export function page(items, start, size) { return items.slice(start, size); }",
        "export function page(items, start, size) { return items.slice(start, start + size); }",
        "Nonzero start produces wrong page bounds",
        1,
    ),
    (
        "falsy-default",
        "ts",
        "export function timeout(value: number | undefined): number { return value || 30; }",
        "export function timeout(value: number | undefined): number { return value ?? 30; }",
        "Explicit zero timeout is overwritten",
        1,
    ),
    (
        "dict-delete",
        "py",
        "def prune(values):\n    for key in values:\n        if values[key] is None:\n            del values[key]\n",
        "def prune(values):\n    for key in list(values):\n        if values[key] is None:\n            del values[key]\n",
        "Dictionary changes size during iteration",
        4,
    ),
    (
        "reject-propagation",
        "js",
        "export function save(task) { task().catch(() => {}); }",
        "export function save(task) { return task(); }",
        "Caller cannot observe completion or rejection",
        1,
    ),
    (
        "assignment-contract",
        "ts",
        "export const retries: number = 'three';",
        "export const retries: number = 3;",
        "Configuration value has incompatible type",
        1,
    ),
    (
        "precision-money",
        "py",
        "def cents(value):\n    return int(value * 100)\n",
        "from decimal import Decimal\ndef cents(value):\n    return int(Decimal(str(value)) * 100)\n",
        "Binary floating point truncates monetary cents",
        2,
    ),
]


def build():
    cases = []
    for index, (name, lang, bug, clean, description, line) in enumerate(FAMILIES):
        for positive, code in [(True, bug), (False, clean)]:
            path = "src/module." + lang
            cases.append(
                {
                    "id": name + ("-bug" if positive else "-clean"),
                    "split": "development" if index < 6 else "heldout",
                    "files": {path: code},
                    "base_files": {path: clean},
                    "expected_issues": [{"id": name, "path": path, "line": line, "description": description}]
                    if positive
                    else [],
                    "annotation_status": "author_labelled_requires_independent_review",
                    "requirements": description
                    if positive
                    else "Preserve the documented safe behavior; do not invent issues.",
                }
            )
    corpus = {
        "version": "authored-review-v1",
        "provenance": "Self-authored; family split; not independently annotated. No model tuning on heldout permitted after freezing.",
        "cases": cases,
    }
    payload = json.dumps(corpus, indent=2)
    root = Path(__file__).parent / "corpus"
    root.mkdir(exist_ok=True)
    (root / "authored-v1.json").write_text(payload)
    (root / "authored-v1.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n")


if __name__ == "__main__":
    build()
