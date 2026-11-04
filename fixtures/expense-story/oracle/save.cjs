const assert=require('node:assert/strict');
const {saveAll}=require(process.argv[2]);
(async()=>{
let releases=[], persisted=0, reported=false;
const items=[1,2,3].map(()=>({save:()=>new Promise(resolve=>releases.push(()=>{persisted++;resolve();}))}));
const result=saveAll(items).then(()=>{reported=true;});
await Promise.resolve(); await Promise.resolve();
const early=reported; const before=persisted;
releases.forEach(resolve=>resolve()); await result; await Promise.resolve();
console.log(JSON.stringify({reported_before_persistence:early,persisted_before_release:before,persisted_after: persisted}));
assert.equal(early,false,'Saved was reported while writes were pending'); assert.equal(persisted,3);
})().catch(e=>{console.error(e.message);process.exitCode=1;});
