'use strict';
const DNSISH=/UNKNOWN_HOST|DNS|TRR|NAME_NOT_RESOLVED/i;

async function getBase(){
  const x=await browser.storage.local.get('dashboardBase');
  if(!x.dashboardBase)return null;
  try{
    const u=new URL(x.dashboardBase);
    if(u.protocol!=='https:')return null;
    if(!u.pathname.endsWith('/'))u.pathname+='/';
    return u;
  }catch{return null}
}

browser.webRequest.onErrorOccurred.addListener(async details=>{
  if(details.tabId<0 || details.type!=='main_frame' || !DNSISH.test(details.error||''))return;
  let failed;
  try{failed=new URL(details.url)}catch{return}
  if(!['http:','https:'].includes(failed.protocol))return;
  const base=await getBase();
  if(!base || failed.hostname===base.hostname)return;
  try{
    const check=new URL('api/check',base);
    const response=await fetch(check.href,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:failed.hostname}),
      cache:'no-store',
      credentials:'omit'
    });
    if(!response.ok)return;
    const report=await response.json();
    if((report.status==='mismatch'||report.status==='unavailable') && report.id){
      const target=new URL('reports/'+encodeURIComponent(report.id),base);
      await browser.tabs.update(details.tabId,{url:target.href});
    }
  }catch{}
},{urls:['<all_urls>'],types:['main_frame']});
