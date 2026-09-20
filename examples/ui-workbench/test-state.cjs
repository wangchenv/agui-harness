// Runs the page's original state functions with a stub DOM.
// This checks state transitions only, not layout, browser behavior or accessibility.
// No external packages. Run: node test-state.cjs
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(),timers=[];
function el(id){if(!elements.has(id))elements.set(id,{id,open:false,textContent:'',innerHTML:'',dataset:{},addEventListener(){},setAttribute(){},focus(){},showModal(){this.open=true},close(){this.open=false}});return elements.get(id)}
const context={console,Intl,Date,Map,Number,String,Array,assert,document:{getElementById:el,querySelectorAll:()=>[],querySelector:()=>el('generic')},window:{matchMedia:()=>({matches:false}),setTimeout:fn=>timers.push(fn)}};
context.flush=()=>{while(timers.length)timers.shift()()};vm.createContext(context);
const source=fs.readFileSync(path.join(__dirname,'index.html'),'utf8').split('<script>')[1].split('</script>')[0];
vm.runInContext(source+`
const outcomes=[];
function check(name,fn){fn();outcomes.push(name);}
check('normal: complete preview and receipt required',()=>{const t=getTicket('T-2048'),d=draftFor(t.id);makeDraft(t.id);assert.equal(d.phase,'partial');assert.equal(t.priority,3);reviewDraft();assert.equal($('approval-dialog').open,false);flush();assert.equal(d.phase,'draft');assert.equal(t.priority,3);reviewDraft();assert.equal($('approval-dialog').open,true);approveDraft();assert.equal(t.priority,3);assert.equal(d.phase,'applying');flush();assert.equal(d.phase,'committed');assert.equal(t.priority,2);assert.equal(t.version,2);assert.equal(simulationLedger.size,1);const n=t.activity.length;commitReceipt(t.id,d.receipt);assert.equal(t.activity.length,n)});
check('disconnect: partial is not approvable or committed',()=>{selectedId='T-2051';const t=getTicket(selectedId),d=draftFor(t.id);d.scenario='disconnect';makeDraft(t.id);assert.equal(d.phase,'partial');reviewDraft();assert.equal($('approval-dialog').open,false);flush();assert.equal(d.phase,'interrupted');reviewDraft();assert.equal($('approval-dialog').open,false);assert.equal(t.priority,3);assert.equal(t.version,1);assert.equal(d.receipt,undefined);makeDraft(t.id,true);flush();assert.equal(d.phase,'draft')});
check('unknown: stable operation, no repeat, reconcile receipt',()=>{selectedId='T-2039';const t=getTicket(selectedId),d=draftFor(t.id);d.scenario='unknown';makeDraft(t.id);flush();reviewDraft();approveDraft();flush();assert.equal(d.phase,'unknown');assert.equal(t.priority,2);assert.equal(t.version,1);const op=d.operationId,size=simulationLedger.size;makeDraft(t.id);approveDraft();assert.equal(d.operationId,op);assert.equal(simulationLedger.size,size);assert.equal(d.phase,'unknown');reconcile();assert.equal(d.phase,'reconciling');flush();assert.equal(d.phase,'committed');assert.equal(d.operationId,op);assert.equal(simulationLedger.size,size);assert.equal(t.priority,1);assert.equal(t.version,2)});
check('user: cannot approve or expose other requests',()=>{switchView('user');assert.equal(visibleTickets().length,2);selectedId='T-2048';const d=draftFor(selectedId),t=getTicket(selectedId);d.phase='idle';d.desired=3;makeDraft(t.id);flush();reviewDraft();assert.equal(d.phase,'awaiting_review');assert.equal($('approval-dialog').open,false);approvalTicketId=t.id;approveDraft();assert.equal(d.phase,'awaiting_review');assert.equal(t.priority,2)});
check('stale preview: regenerate before approving',()=>{switchView('operator');selectedId='T-2051';const t=getTicket(selectedId),d=draftFor(t.id);assert.equal(d.phase,'draft');reviewDraft();t.version++;approveDraft();assert.equal(d.phase,'idle');assert.equal(t.priority,3)});
console.log(JSON.stringify({passed:outcomes.length,cases:outcomes},null,2));
`,context);
