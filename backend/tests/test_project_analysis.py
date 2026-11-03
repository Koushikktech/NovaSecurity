from analysis.languages import javascript_analysis


def test_compiler_resolves_alias_reexport_and_signature_error():
    files = [
        {"relative_path": p, "content": c}
        for p, c in {
            "tsconfig.json": '{"compilerOptions":{"baseUrl":".","paths":{"@app/*":["src/*"]}}}',
            "src/value.ts": "export function total(items: number[], tax: number): number { return tax; }",
            "src/index.ts": "export { total as calculate } from './value';",
            "consumer.ts": "import { calculate } from '@app/index'; export const value = calculate([1]);",
        }.items()
    ]
    findings, index, coverage = javascript_analysis(files, "test")
    assert coverage["status"] == "executed", coverage
    assert any(f.rule_id == "js:type-2554" and f.primary_location.path == "consumer.ts" for f in findings)
    refs = index["consumer.ts"]["resolved_references"]
    assert any(r["target_path"] == "src/value.ts" and r["relationship"] == "compiler_resolved_call" for r in refs)


def test_compiler_does_not_invent_missing_dependency_type_errors():
    files = [
        {
            "relative_path": "app.ts",
            "content": "import { unknown } from 'not-installed'; export const result = unknown();",
        }
    ]
    findings, _, coverage = javascript_analysis(files, "test")
    assert coverage["status"] == "executed"
    assert not any(f.rule_id == "js:type-2307" for f in findings)


def test_compiler_resolves_default_and_namespace_imports():
    files = [
        {
            "relative_path": "service.ts",
            "content": "export default function parse(value: string) { return value; } export function count(items: number[]) { return items.length; }",
        },
        {
            "relative_path": "caller.ts",
            "content": "import parse from './service'; import * as service from './service'; export const first = parse('ok'); export const second = service.count([1]);",
        },
    ]
    _, index, coverage = javascript_analysis(files, "test")
    assert coverage["status"] == "executed"
    refs = index["caller.ts"]["resolved_references"]
    assert any(r["name"] == "parse" and r["target_path"] == "service.ts" for r in refs)
    assert any(r["name"] == "count" and r["target_path"] == "service.ts" for r in refs)


def test_snapshot_supplied_external_declarations_support_type_checks():
    files = [
        {
            "relative_path": "types/framework.d.ts",
            "content": "declare module 'framework' { export function route(path: string, retries: number): void; }",
        },
        {"relative_path": "app.ts", "content": "import { route } from 'framework'; route('/checkout');"},
    ]
    findings, index, coverage = javascript_analysis(files, "test")
    assert coverage["status"] == "executed"
    assert any(f.rule_id == "js:type-2554" and f.primary_location.path == "app.ts" for f in findings)
