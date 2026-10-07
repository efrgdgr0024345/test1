'use strict';
const box=document.getElementById('base'),status=document.getElementById('status');
browser.storage.local.get('dashboardBase').then(x=>{box.value=x.dashboardBase||''});
document.getElementById('save').onclick=async()=>{
  try{
    const u=new URL(box.value.trim());
    if(u.protocol!=='https:'||!u.pathname.includes('/s/'))throw new Error('Use the HTTPS dashboard session URL');
    if(!u.pathname.endsWith('/'))u.pathname+='/';
    await browser.storage.local.set({dashboardBase:u.href});
    status.textContent='Saved for this Firefox profile.';
  }catch(e){status.textContent=e.message}
};
