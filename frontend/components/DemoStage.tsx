"use client";

import { useState, useRef } from "react";
import { ArrowRight, Check, ChevronLeft, ChevronRight, Expand, GitBranch, Layers, ScanLine, ShieldCheck, Wrench, X } from "lucide-react";

type Location = {path: string; start_line: number};
type Issue = {id: string; title: string; category: string; severity: string; disposition: string; evidence_status?: string; user_impact: string; primary_location: Location; related_locations: {path: string; relationship: string}[]; verification_assessment?: {citations?: {path: string; start_line: number; quote: string}[]}; evidence_items: {kind: string; tool_or_profile: string}[]};
type Change = {symbol: {id: string; name: string; path: string; start: number}; callers: {path: string; line: number; relationship: string}[]; test_hints: string[]};
type Props = {
  run: {status: string; base_sha?: string; head_sha?: string; stage_statuses: Record<string,string>; coverage: {source_files?: string[]; changed_files?: string[]; diff?: string; impact?: {changes: Change[]}; investigation?: {tool_calls: number}; verification_coverage?: {requested: number; assessed: number}; model_activity?: {attempts: number; failures: number; tokens: number}}};
  source: {path: string; content: string} | null;
  findings: Issue[];
  patch: {status: string; checks: {check_name: string; status: string}[]} | null;
  onInspect: (id: string) => void;
  onSource: (path: string) => void;
};
const chapters = ["Mission control", "Change impact", "Evidence lens", "Repair lab"];
const icons = [ScanLine, GitBranch, ShieldCheck, Wrench];
const short = (p: string) => p.split("/").slice(-2).join("/");

export default function DemoStage({run, findings, patch, source, onInspect, onSource}: Props) {
  const stageRef = useRef<HTMLElement>(null);
  const [sourcePath, setSourcePath] = useState<string | null>(null);
  const openSource = (path: string) => { setSourcePath(path); onSource(path); };
  const [chapter, setChapter] = useState(0);
  const [presenting, setPresenting] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const [changeIndex, setChangeIndex] = useState(0);
  const active = findings.filter(f => !["dismissed", "resolved"].includes(f.disposition));
  const issue = findings.find(f => f.id === focus) || active[0] || findings[0];
  const changes = run.coverage.impact?.changes || [];
  const change = changes[changeIndex] || changes[0];
  const coverage = run.coverage.verification_coverage;
  const activity = run.coverage.model_activity;
  const steps = Object.entries(run.stage_statuses);
  const assessed = coverage?.assessed || 0;
  const requested = coverage?.requested || 0;
  const citations = issue?.verification_assessment?.citations || [];
  const rejected = findings.filter(f => f.disposition === "dismissed").length;
  const running = ["queued", "running"].includes(run.status);
  return <section ref={stageRef} className={`demo-stage ${presenting ? "demo-presenting" : ""}`} aria-label="Visual review presentation" onKeyDown={e => {
    if ((e.target as HTMLElement).closest("input,select,textarea")) return;
    if(e.key === "Escape") { if(sourcePath) setSourcePath(null); else setPresenting(false); }
    if(e.key === "ArrowRight") setChapter(c => Math.min(3,c+1));
    if(e.key === "ArrowLeft") setChapter(c => Math.max(0,c-1));
  }} tabIndex={-1}>
    <header className="demo-top"><span className="demo-wordmark">p<span>·</span> / THE REVIEW, REVEALED</span><div><span className={`demo-status ${running ? "is-live" : ""}`}>{running ? "LIVE ANALYSIS" : `REVIEW ${run.status.toUpperCase()}`}</span><button onClick={() => {setPresenting(!presenting); stageRef.current?.focus();}} aria-label={presenting ? "Exit presentation" : "Enter presentation"}>{presenting ? <X size={17}/> : <Expand size={17}/>} {presenting ? "Exit" : "Present"}</button></div></header>
    <nav className="demo-chapters" aria-label="Presentation chapters">{chapters.map((name,i) => { const Icon=icons[i]; return <button key={name} aria-pressed={chapter===i} onClick={()=>setChapter(i)}><Icon size={17}/><span>0{i+1} / {name}</span></button>;})}</nav>
    <div className="demo-canvas" key={chapter}>
    {chapter === 0 && <>
      <div className="demo-heading"><p>FROM SOURCE TO SIGNAL</p><h2>Small change.<br/><em>See the consequences.</em></h2><span>{run.base_sha?.slice(0,8) || "Snapshot"} <ArrowRight size={14}/> {run.head_sha?.slice(0,8) || "Local source"}</span></div>
      <div className="demo-scoreboard"><div><strong>{active.length}</strong><span>Open findings</span></div><div><strong>{run.coverage.source_files?.length ?? "—"}</strong><span>Source files in scope</span></div><div><strong>{assessed}<small>/{requested}</small></strong><span>Candidates assessed</span></div><div><strong>{run.coverage.investigation?.tool_calls || 0}</strong><span>Investigation tool calls</span></div></div>
      <div className="demo-pipeline">{steps.map(([name,status],i)=><div className="demo-pipeline-node" key={name} data-state={status}><span className="demo-node-number">{status==="succeeded" ? <Check size={17}/> : String(i+1).padStart(2,"0")}</span><strong>{name === "gemini_review" ? "AI review" : name.replaceAll("_"," ")}</strong><small>{status}</small></div>)}</div>
      <div className="demo-bottom-stats"><span><Layers size={16}/>{changes.length} changed symbols indexed</span><span>{activity?.attempts || 0} model invocations</span><span>{activity?.failures || 0} failed attempts</span></div>
    </>}
    {chapter === 1 && <>
      <div className="demo-heading"><p>FOLLOW THE CHANGE</p><h2>The ripple effect.</h2></div>
      {changes.length > 0 ? <><div className="demo-symbol-picker">{changes.map((c,i)=><button key={c.symbol.id} aria-pressed={changeIndex===i} onClick={()=>setChangeIndex(i)}>{c.symbol.name}</button>)}</div><div className="demo-graph">
        <svg viewBox="0 0 1000 340" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="impact-line"><stop stopColor="#e0b876"/><stop offset="1" stopColor="#95bea2"/></linearGradient></defs>{change?.callers.slice(0,4).map((_,i,a)=><path key={i} d={`M 280 170 C 470 170, 500 ${(i+1)*340/(a.length+1)}, 690 ${(i+1)*340/(a.length+1)}`} fill="none" stroke="url(#impact-line)" strokeWidth="2"/>)}</svg>
        <button className="demo-graph-origin" onClick={()=>openSource(change.symbol.path)}><GitBranch size={25}/><small>CHANGED SYMBOL</small><strong>{change.symbol.name}</strong><code>{short(change.symbol.path)}:{change.symbol.start}</code></button>
        <div className="demo-graph-targets">{change.callers.length ? change.callers.slice(0,4).map((c,i)=><button key={i} onClick={()=>openSource(c.path)}><small>{c.relationship.replaceAll("_"," ")}</small><strong>{short(c.path)}</strong><code>line {c.line}</code></button>) : <div className="demo-graph-empty">No resolved callers in supported analysis</div>}</div>
      </div><div className="demo-bottom-stats"><span>{change.callers.length} caller relationships</span><span>{change.test_hints.length} lexical test hints</span><span>Edges reflect indexed relationships</span></div></> : <div className="demo-empty"><GitBranch size={48}/><h3>No changed-symbol graph available</h3><p>Use a commit, pull request or comparison with supported symbols.</p></div>}
    </>}
    {chapter === 2 && <>
      <div className="demo-heading"><p>EVERY CLAIM NEEDS A SOURCE</p><h2>Look behind the finding.</h2></div>
      <div className="demo-evidence-grid"><div className="demo-issue-picker">{findings.map(f=><button key={f.id} aria-pressed={issue?.id===f.id} onClick={()=>setFocus(f.id)}><small>{f.category} · {f.severity}</small><strong>{f.title}</strong><span>{f.disposition}</span></button>)}{!findings.length && <p>No findings recorded yet.</p>}</div><div className="demo-evidence-detail">{issue && <><span className="demo-proof-label">{(issue.evidence_status || "unassessed").replaceAll("_"," ")}</span><h3>{issue.user_impact || issue.title}</h3><button className="demo-source-link" onClick={()=>openSource(issue.primary_location.path)}>{short(issue.primary_location.path)}:{issue.primary_location.start_line} ↗</button>{citations.slice(0,2).map((c,i)=><button className="demo-citation" key={i} onClick={()=>openSource(c.path)}><small>{short(c.path)}:{c.start_line}</small><pre>{c.quote}</pre></button>)}{!citations.length && <div className="demo-evidence-tags">{issue.evidence_items.map((e,i)=><span key={i}>{e.tool_or_profile}</span>)}<p>No model source quotations recorded for this finding.</p></div>}<button className="demo-cta" onClick={()=>{setPresenting(false);onInspect(issue.id);}}>Inspect finding & source <ArrowRight size={16}/></button></>}</div></div>
      <div className="demo-bottom-stats"><span>{assessed}/{requested} requested candidates assessed</span><span>{rejected} dismissed findings</span><span>Source support ≠ execution proof</span></div>
    </>}
    {chapter === 3 && <>
      <div className="demo-heading"><p>CLOSE THE LOOP</p><h2>Find it. Fix it.<br/><em>Check the outcome.</em></h2></div>
      <div className="demo-repair-flow">{[{icon:ScanLine,title:"Review",value:`${active.length} open findings`},{icon:ShieldCheck,title:"Assess",value:`${assessed} candidates assessed`},{icon:Wrench,title:"Repair",value:patch ? patch.status.replaceAll("_"," ") : "Select a finding to propose"},{icon:Check,title:"Check",value:patch ? `${patch.checks.filter(c=>["passed","pass","succeeded"].includes(c.status)).length}/${patch.checks.length} checks passed` : "No patch checks recorded"}].map((s,i)=><div key={s.title}><s.icon size={28}/><small>0{i+1}</small><h3>{s.title}</h3><span>{s.value}</span></div>)}</div>
      {patch?.checks.length ? <div className="demo-check-results">{patch.checks.map((c,i)=><div key={i} data-state={c.status}><span>{c.check_name.replaceAll("_"," ")}</span><strong>{c.status}</strong></div>)}</div> : <div className="demo-next-action"><span>Patch inspection and approved execution live in the finding workspace.</span>{issue && <button className="demo-cta" onClick={()=>{setPresenting(false);onInspect(issue.id);}}>Open repair workspace <ArrowRight size={16}/></button>}</div>}
      <div className="demo-bottom-stats"><span>Python · JavaScript · TypeScript</span><span>Execution requires an approved project profile</span></div>
    </>}
    </div>
    {sourcePath && <div className="demo-source-overlay" role="dialog" aria-modal="false" aria-label="Source evidence"><header><div><small>SOURCE EVIDENCE</small><strong>{sourcePath}</strong></div><button aria-label="Close source evidence" onClick={()=>setSourcePath(null)}><X size={20}/></button></header>{source?.path === sourcePath ? <pre>{source.content.split("\n").map((line,i)=><span key={i} className={citations.some(c=>c.path===sourcePath && i+1>=c.start_line && i+1<c.start_line+c.quote.split("\n").length) ? "is-cited" : ""}><b>{i+1}</b>{line || " "}{"\n"}</span>)}</pre> : <p>Loading source…</p>}</div>}
    <footer className="demo-footer"><span>PROOFLINE / EVIDENCE FIRST</span><div><button aria-label="Previous chapter" disabled={chapter===0} onClick={()=>setChapter(c=>c-1)}><ChevronLeft size={18}/></button><span>{chapter+1} / 4</span><button aria-label="Next chapter" disabled={chapter===3} onClick={()=>setChapter(c=>c+1)}><ChevronRight size={18}/></button></div></footer>
  </section>;
}
