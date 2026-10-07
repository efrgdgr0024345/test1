'use strict';
const prefix=document.body.dataset.prefix;
const endpoint=location.origin+prefix+'/working/dns';
const $=id=>document.getElementById(id);
$('endpoint').textContent=endpoint;

$('copy').addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText(endpoint);$('copy').textContent='Copied';}
  catch{$('copy').textContent='Select and copy the URL above';}
});

function cell(text){const td=document.createElement('td');td.textContent=String(text??'');return td}
function render(data){
  $('result').hidden=false;
  const s=$('status');s.className='status '+data.status;
  s.textContent=data.status==='match'
    ?(data.allowed?'UNANIMOUS / ADDRESS CHECK PASSED':'UNANIMOUS / NO ADDRESS')
    :(data.status==='mismatch'?'BLOCKED / RESOLVERS DISAGREE':'BLOCKED / CHECK INCOMPLETE');
  $('result-name').textContent=data.name||'';
  $('summary').textContent=data.status==='match'
    ?'Every configured resolver returned the same normalized answer for each checked record type.'
    :'No address is released. Review the evidence below before deciding what to do.';
  $('timestamp').textContent='Checked: '+(data.checked_at||'unknown');
  const holder=$('tables');holder.replaceChildren();
  for(const group of data.comparisons||[]){
    const h=document.createElement('h3');
    h.textContent=(group.qtype||'')+' / '+String(group.status||'').toUpperCase();
    holder.append(h);
    const wrap=document.createElement('div');wrap.className='scroll';
    const table=document.createElement('table');
    const head=document.createElement('tr');
    for(const t of ['Resolver','Operator location label','Addresses','DNS result','DNSSEC AD','Latency']){
      const th=document.createElement('th');th.textContent=t;head.append(th);
    }
    table.append(head);
    for(const r of group.rows||[]){
      const tr=document.createElement('tr');
      tr.append(cell(r.provider),cell(r.location),cell((r.ips||[]).join(', ')||r.error||'—'),cell(r.rcode||'ERROR'),cell(r.ad_reported?'yes':'no'),cell((r.milliseconds??'')+' ms'));
      table.append(tr);
    }
    wrap.append(table);holder.append(wrap);
  }
  $('evidence').textContent=JSON.stringify(data,null,2);
  const report=$('report-link');report.replaceChildren();
  if(data.id){
    const a=document.createElement('a');a.href=location.origin+prefix+'/reports/'+encodeURIComponent(data.id);a.textContent='Permanent-for-this-session report link';
    report.append(a);
    history.replaceState(null,'',prefix+'/reports/'+encodeURIComponent(data.id));
  }
}

async function check(name){
  const res=await fetch(prefix+'/api/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
  const data=await res.json();
  if(!res.ok)throw new Error(data.error||'Check failed');
  render(data);return data;
}

$('check').addEventListener('submit',async ev=>{
  ev.preventDefault();$('submit').disabled=true;
  try{await check($('domain').value.trim());}
  catch(err){$('result').hidden=false;$('status').className='status unavailable';$('status').textContent='BLOCKED / CHECK FAILED';$('summary').textContent=String(err.message||err);}
  finally{$('submit').disabled=false;}
});

(async()=>{
  const marker='/reports/';
  if(location.pathname.includes(marker)){
    const rid=location.pathname.split(marker).pop();
    try{
      const res=await fetch(prefix+'/api/reports/'+encodeURIComponent(rid));
      const data=await res.json();
      if(!res.ok)throw new Error(data.error||'Report unavailable');
      render(data);
    }catch(err){$('result').hidden=false;$('status').className='status unavailable';$('status').textContent='REPORT UNAVAILABLE';$('summary').textContent=String(err.message||err);}
  }
})();
