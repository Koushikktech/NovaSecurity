"""Offline, variant-blinded finding adjudication. Exports human decisions; never fills judgments."""

import argparse
import hashlib
import html
import json
import random
from pathlib import Path


def build(corpus, results, output):
    raw = Path(corpus).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    cases = {c["id"]: c for c in json.loads(raw)["cases"]}
    records = []
    for path in results:
        report = json.loads(Path(path).read_text())
        if report["corpus_hash"] != digest:
            raise ValueError("Corpus mismatch")
        for row in report["results"]:
            for finding in row["findings"]:
                if finding["disposition"] != "dismissed":
                    records.append((row["case_id"], finding))
    if len({f["id"] for _, f in records}) != len(records):
        raise ValueError("Duplicate finding IDs across input reports")
    random.Random(digest).shuffle(records)
    esc = html.escape
    cards = []
    for index, (case_id, f) in enumerate(records, 1):
        case = cases[case_id]
        options = (
            '<option value="">Choose judgment</option><option value="none">Unsupported or incorrect comment</option>'
        )
        for issue in case["expected_issues"]:
            options += '<option value="' + esc(issue["id"], quote=True) + '">' + esc(issue["id"]) + "</option>"
        sources = "".join(
            "<h4>"
            + esc(label)
            + "</h4>"
            + "".join("<h5>" + esc(p) + "</h5><pre>" + esc(code) + "</pre>" for p, code in case[key].items())
            for label, key in [("Base", "base_files"), ("Changed", "files")]
        )
        cards.append(
            '<article data-id="'
            + esc(f["id"], quote=True)
            + '"><h2>Comment '
            + str(index)
            + "</h2><h3>"
            + esc(f["title"])
            + "</h3><p>"
            + esc(f["explanation"])
            + "</p><p>"
            + esc(f["primary_location"]["path"])
            + ":"
            + str(f["primary_location"]["start_line"])
            + "</p><details><summary>Original source snapshots</summary>"
            + sources
            + "</details><p>Match an established issue ID or mark unsupported. If this is a new real bug, stop and resolve the corpus disagreement before scoring. Matching a valid issue already reported elsewhere is still the same issue; the scorer counts duplicate noise.</p><select>"
            + options
            + '</select><textarea placeholder="Evidence supporting this judgment; trigger, consequence and source location"></textarea></article>'
        )
    ids_hash = hashlib.sha256(json.dumps(sorted(f["id"] for _, f in records)).encode()).hexdigest()
    script = """const key='proofline-finding-decisions-'+PACKET;function collect(){return [...document.querySelectorAll('article')].map(a=>({finding_id:a.dataset.id,issue_id:a.querySelector('select').value==='none'?null:a.querySelector('select').value,reviewer:document.querySelector('#reviewer').value,reason:a.querySelector('textarea').value}))}function save(){localStorage.setItem(key,JSON.stringify(collect()))}try{for(const r of JSON.parse(localStorage.getItem(key)||'[]')){const a=[...document.querySelectorAll('article')].find(a=>a.dataset.id===r.finding_id);if(a){a.querySelector('select').value=r.issue_id===null?'none':r.issue_id;a.querySelector('textarea').value=r.reason;document.querySelector('#reviewer').value=r.reviewer}}}catch(e){}document.addEventListener('input',save);document.addEventListener('change',save);document.querySelector('#export').onclick=()=>{if(collect().some(r=>!r.reviewer.trim()||!r.reason.trim()||r.issue_id==='')){alert('Every comment requires a named reviewer, judgment and written evidence.');return}const a=document.createElement('a'),u=URL.createObjectURL(new Blob([JSON.stringify(collect(),null,2)],{type:'application/json'}));a.href=u;a.download='finding-adjudications.json';a.click();URL.revokeObjectURL(u)};""".replace(
        "PACKET", json.dumps(ids_hash)
    )
    document = (
        '<!doctype html><meta charset="utf-8"><title>Finding adjudication</title><style>body{max-width:1000px;margin:auto;padding:25px;background:#f5f3ed;font:15px/1.6 system-ui}article{padding:25px;margin:25px 0;background:#fffef9;border:1px solid #ddd}pre{white-space:pre-wrap;background:#20251f;color:#eee;padding:15px}select,textarea,input,button{font:inherit;padding:10px}textarea{display:block;width:95%;min-height:100px;margin-top:15px}header{position:sticky;top:0;background:#f5f3ed;padding:15px}</style><header><h1>Finding adjudication</h1><p>Variant names are hidden. Human decisions are required; this packet supplies no accuracy score.</p><label>Reviewer <input id="reviewer"></label><button id="export">Export judgments</button></header>'
        + "".join(cards)
        + "<script>"
        + script
        + "</script>"
    )
    Path(output).write_text(document)
    print(json.dumps({"comments": len(records), "packet": str(output), "corpus_hash": digest}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", default=str(Path(__file__).parent / "corpus/authored-v1.json"))
    p.add_argument("--results", nargs="+", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    build(a.corpus, a.results, a.output)
