"""Create an offline blinded review packet; expected labels are not embedded."""

import hashlib
import html
import json
import random
from pathlib import Path


def build():
    root = Path(__file__).parent
    raw = (root / "corpus/authored-v1.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    cases = json.loads(raw)["cases"]
    random.Random(digest).shuffle(cases)
    mapping = {}
    cards = []
    for index, case in enumerate(cases, 1):
        blind = f"case-{index:03d}"
        mapping[blind] = case["id"]
        panels = []
        for label, key in [("Base snapshot", "base_files"), ("Changed snapshot", "files")]:
            blocks = "".join(
                "<h4>"
                + html.escape(path)
                + "</h4><pre>"
                + html.escape("\n".join(f"{i + 1:3} {line}" for i, line in enumerate(code.splitlines())))
                + "</pre>"
                for path, code in case[key].items()
            )
            panels.append("<section><h3>" + label + "</h3>" + blocks + "</section>")
        cards.append(
            '<article data-id="'
            + blind
            + '"><h2>'
            + blind
            + '</h2><div class="snapshots">'
            + "".join(panels)
            + '</div><label>Your assessment<select><option value="">Not reviewed</option><option value="issue">Demonstrable issue</option><option value="clean">No demonstrable issue found</option><option value="uncertain">Insufficient requirements or context</option></select></label><label>Evidence and assumptions<textarea placeholder="Describe the trigger, consequence, affected path/line, and any assumptions. Do not infer missing requirements."></textarea></label></article>'
        )
    script = """const hash=CORPUS_HASH;const key='proofline-annotations-'+hash;
function collect(){return {corpus_hash:hash,reviewer:document.querySelector('#reviewer').value,annotations:[...document.querySelectorAll('article')].map(a=>({blind_id:a.dataset.id,verdict:a.querySelector('select').value,notes:a.querySelector('textarea').value}))}}
function save(){localStorage.setItem(key,JSON.stringify(collect()));document.querySelector('#progress').textContent=collect().annotations.filter(a=>a.verdict).length+' / 36 reviewed'}
try{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved){document.querySelector('#reviewer').value=saved.reviewer||'';for(const item of saved.annotations){const a=document.querySelector('[data-id="'+item.blind_id+'"]');if(a){a.querySelector('select').value=item.verdict;a.querySelector('textarea').value=item.notes}}}}catch(e){}
document.addEventListener('input',save);document.addEventListener('change',save);save();
document.querySelector('#export').onclick=()=>{const data=collect();if(!data.reviewer.trim()){alert('Enter the reviewer name before export.');return}const link=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));link.href=url;link.download='independent-labels.json';link.click();URL.revokeObjectURL(url)};
""".replace("CORPUS_HASH", json.dumps(digest))
    document = (
        """<!doctype html><html><meta charset="utf-8"><title>Proofline independent label review</title><style>body{font:15px/1.6 system-ui;background:#f5f3ed;color:#262720;max-width:1400px;margin:auto;padding:30px}header{position:sticky;top:0;background:#f5f3ed;padding:15px;border-bottom:1px solid #ccc}article{padding:25px;background:#fffef9;margin:25px 0;border:1px solid #ddd;border-radius:8px}.snapshots{display:grid;grid-template-columns:1fr 1fr;gap:25px;min-width:0}section{min-width:0}pre{overflow:auto;background:#272920;color:#eee;padding:15px}label{display:grid;margin-top:15px}textarea{min-height:110px}input,textarea,select,button{font:inherit;padding:8px}button{margin-left:15px}@media(max-width:800px){.snapshots{grid-template-columns:1fr}}</style><header><h1>Independent code-review labels</h1><p>Expected labels and original case IDs are hidden. Report only demonstrable issues; mark ambiguous cases uncertain. This is offline and sends no data to a server. Progress is stored in this browser.</p><label>Reviewer name<input id="reviewer" autocomplete="off"></label><span id="progress"></span><button id="export">Export annotations</button></header>"""
        + "".join(cards)
        + "<script>"
        + script
        + "</script></html>"
    )
    out = root / "annotation"
    out.mkdir(exist_ok=True)
    (out / "review.html").write_text(document)
    (out / "blind-map.json").write_text(json.dumps({"corpus_hash": digest, "mapping": mapping}, indent=2))


if __name__ == "__main__":
    build()
