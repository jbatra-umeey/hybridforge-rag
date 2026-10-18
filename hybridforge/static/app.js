const $ = id => document.getElementById(id);
function element(tag, text, cls) { const e=document.createElement(tag); if(text)e.textContent=text; if(cls)e.className=cls; return e; }
async function api(path, body) {
  const response=await fetch(path,{method:body?'POST':'GET',headers:{'Authorization':'Bearer '+$('token').value,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
  const data=await response.json(); if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'Request rejected. Check the input and your access.'); return data;
}
fetch('/health/live').then(r=>r.json()).then(d=>{$('mode').textContent=d.mode==='demo'?'Offline demo mode':'Model API mode';}).catch(()=>{$('mode').textContent='Unavailable';});
$('connect').addEventListener('click',async()=>{try{const d=await api('/v1/documents'); $('documents').replaceChildren();for(const doc of d.documents){const row=element('div',null,'doc');row.append(element('strong',doc.title),element('span',doc.document_id+' / v'+doc.version));$('documents').append(row);}$('collection').textContent=d.documents.length+' accessible documents';$('notice').textContent='Collection loaded. All queries use this token’s tenant and permissions.';}catch(e){$('notice').textContent=e.message;}});
document.querySelectorAll('[data-q]').forEach(b=>b.addEventListener('click',()=>{$('question').value=b.dataset.q;}));
$('ask').addEventListener('click',async()=>{
  $('ask').disabled=true;$('notice').textContent='Retrieving evidence and preparing an answer…';
  try{const d=await api('/v1/query',{question:$('question').value,mode:$('retrieval').value,top_k:Number($('topk').value)});
    $('answer-title').textContent=d.status==='answered'?'Evidence-backed response':'Insufficient evidence';
    $('answer').textContent=d.answer||'No supported answer was produced. Try a more specific question or add relevant documents.';
    $('latency').textContent=d.diagnostics.retrieval_ms+' ms';$('candidates').textContent=d.diagnostics.lexical_candidates+' / '+d.diagnostics.dense_candidates;$('selected').textContent=d.diagnostics.selected_chunks;
    $('citations').replaceChildren();for(const c of d.citations){const card=element('div',null,'citation');card.append(element('strong','['+c.number+'] '+c.title),element('blockquote',c.quote),element('small',c.document_id+' · v'+c.version+' · characters '+c.start_char+'–'+c.end_char));$('citations').append(card);}
    $('evidence').replaceChildren();for(const h of d.evidence){const card=element('details');card.append(element('summary',h.title),element('div','Lexical #'+(h.ranks.lexical||'—')+' / Dense #'+(h.ranks.dense||'—')+' / RRF '+h.score.toFixed(4),'rank'),element('pre',h.text));$('evidence').append(card);}
    $('notice').textContent=(d.generation_mode==='evidence_only_demo'?'Demo: deterministic evidence extracts; hash vectors are not semantic embeddings. ':'Model-generated answer. ')+'Request '+d.request_id;
  }catch(e){$('notice').textContent=e.message;}finally{$('ask').disabled=false;}
});
