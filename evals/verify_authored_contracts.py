"""Execute only the fixed, operator-authored audit corpus against explicit baseline contracts.

Not part of source review; never point this script at external repositories.
"""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evals/corpus/authored-v1.json"
EXPECTED_HASH = "b9d4be93d28266423cf3fd3ce11b0283a8d95a90976b39fc382811d8a46c7f33"


def python_contract(family, source):
    namespace = {}
    exec(compile(source, "<fixed authored fixture>", "exec"), namespace)
    if family == "empty-list":
        return namespace["first"]([]) is None
    if family == "sort-return":
        items = [2, 1]
        return namespace["sorted_items"](items) == [1, 2] and items == [2, 1]
    if family == "boolean-string":
        return namespace["enabled"]("false") is False
    if family == "dict-delete":
        items = {"a": None, "b": 1}
        namespace["prune"](items)
        return items == {"b": 1}
    if family == "precision-money":
        return namespace["cents"](0.29) == 29
    raise ValueError(family)


NODE = r"""
const ts=require(process.argv[1]); const data=JSON.parse(require('fs').readFileSync(0,'utf8'));
(async()=>{const out=[];for(const row of data){try{let m={exports:{}};
const code=ts.transpileModule(row.source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
new Function('exports','module',code)(m.exports,m);const api=m.exports;let pass=false;
switch(row.family){
case 'zero-total':pass=api.average([])===0;break;
case 'missing-await':pass=await api.load(async()=>({json:async()=>42}))===42;break;
case 'null-input':pass=api.label(null)==='';break;
case 'slice-boundary':pass=JSON.stringify(api.page([0,1,2,3],2,2))==='[2,3]';break;
case 'falsy-default':pass=api.timeout(0)===0;break;
case 'reject-propagation':{const marker=new Error('task rejected');try{await api.save(()=>Promise.reject(marker));}catch(e){pass=e===marker;}break;}
case 'assignment-contract':pass=typeof api.retries==='number'&&api.retries===3;break;
default:throw Error('Unknown fixed contract');}
out.push({...row,source:undefined,passed:pass});}catch(e){out.push({...row,source:undefined,passed:false,error:e.name+': '+e.message});}} console.log(JSON.stringify(out));})();
"""


def main():
    raw = CORPUS.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_HASH:
        raise ValueError("Only the inspected, fixed authored corpus may execute")
    rows, javascript = [], []
    for case in json.loads(raw)["cases"]:
        if case["split"] != "heldout":
            continue
        for side, key in [("base", "base_files"), ("changed", "files")]:
            path, source = next(iter(case[key].items()))
            family = case["id"].rsplit("-", 1)[0]
            row = {"case": case["id"], "side": side, "family": family}
            if path.endswith(".py"):
                try:
                    row["passed"] = python_contract(family, source)
                except Exception as error:
                    row.update(passed=False, error=type(error).__name__ + ": " + str(error))
                rows.append(row)
            else:
                javascript.append({**row, "source": source})
    process = subprocess.run(
        ["node", "-e", NODE, str(ROOT / "frontend/node_modules/typescript")],
        input=json.dumps(javascript),
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    rows.extend(json.loads(process.stdout))
    for row in rows:
        row["expected_pass"] = row["side"] == "base" or row["case"].endswith("-clean")
    result = {
        "purpose": "Explicit baseline-contract checks on inspected authored snippets, not independent human labels or production accuracy",
        "corpus_hash": EXPECTED_HASH,
        "checks": rows,
        "all_expected_outcomes": all(r["passed"] == r["expected_pass"] for r in rows),
    }
    (ROOT / "evals/results/audit-authored-contracts.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"checks": len(rows), "all_expected_outcomes": result["all_expected_outcomes"]}))
    return 0 if result["all_expected_outcomes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
