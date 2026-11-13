'use strict';
const $ = id => document.getElementById(id);
const form = $('form'), modal = $('editor');
const statuses = {tested:'Testet',untested:'Ikke testet',issues:'Har problemer'};
const kinds = {block:'Sensorblok',complete:'Komplet opsætning'};
let entries = [], current = null, dirty = false;
function el(tag, text, cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
async function api(path,method='GET',body) {
 const response=await fetch('api/'+path,{method,headers:{'Content-Type':'application/json','X-ESPScripts':'1'},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json(); if(!response.ok)throw new Error(data.error||'Forespørgslen mislykkedes.'); return data;
}
const tokens = s => s.split(',').map(s=>s.trim()).filter(Boolean);
async function refresh(){ entries=await api('entries'); filters(); render(); }
function filters(){
 for(const [key,values,label] of [['board',entries.map(e=>e.board).filter(Boolean),'Alle boards'],['sensor',entries.flatMap(e=>tokens(e.sensors)),'Alle sensorer']]){
  const value=$(key).value; $(key).replaceChildren(new Option(label,''));
  [...new Set(values)].sort((a,b)=>a.localeCompare(b,'da')).forEach(v=>$(key).add(new Option(v,v)));
  $(key).value=[...$(key).options].some(o=>o.value===value)?value:'';
 }
}
function render(){
 const q=$('search').value.trim().toLocaleLowerCase('da');
 const filtered=entries.filter(e=>(!q||JSON.stringify(e).toLocaleLowerCase('da').includes(q))&&(!$('board').value||e.board===$('board').value)&&(!$('sensor').value||tokens(e.sensors).includes($('sensor').value))&&(!$('kind').value||e.kind===$('kind').value)&&(!$('status').value||e.status===$('status').value));
 $('count').textContent=`${filtered.length} af ${entries.length} opsætninger`;
 $('cards').replaceChildren();
 if(!filtered.length){const n=el('div',undefined,'empty');n.append(el('h2',entries.length?'Ingen match':'Dine gode løsninger starter her'),el('p',entries.length?'Prøv at ændre søgning eller filtre.':'Opret en opsætning eller importér en YAML-fil fra ESPHome.'));$('cards').append(n);}
 for(const e of filtered){const n=el('article',undefined,'card'), badges=el('div',undefined,'meta');badges.append(el('span',statuses[e.status],'badge '+e.status),el('span',kinds[e.kind],'badge'));n.append(badges,el('h2',e.name),el('p',[e.board,e.sensors].filter(Boolean).join(' · ')),el('p',e.description));const tags=el('div',undefined,'meta');e.tags.forEach(t=>tags.append(el('span',t,'badge')));n.append(tags,el('p',`Version ${e.version} · ${new Date(e.updated_at).toLocaleDateString('da-DK')}`));const b=el('button','Åbn opsætning →','open');b.onclick=()=>edit(e);n.append(b);$('cards').append(n);}
}
function edit(entry=null){current=entry;form.reset();$('form-error').textContent='';$('revisions').replaceChildren();for(const name of ['name','board','sensors','kind','status','tested_on','esphome_version','description','wiring','yaml','notes','tags']){if(entry)form.elements[name].value=name==='tags'?entry.tags.join(', '):entry[name];}$('editor-title').textContent=entry?entry.name:'Ny opsætning';$('history').hidden=!entry;dirty=false;modal.showModal();}
function values(){const d=Object.fromEntries(new FormData(form));d.tags=tokens(d.tags);if(current)d.version=current.version;return d;}
function close(){if(dirty&&!confirm('Du har ugemte ændringer. Vil du lukke?'))return;modal.close();dirty=false;}
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type}));const a=el('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);}
function error(e){$('message').textContent=e.message;}
async function save(copy=false){$('form-error').textContent='';$('save').disabled=true;try{const d=values();if(copy){d.status='untested';d.tested_on='';d.change_note='Kopi af '+(current?.name||d.name);d.name+=' (kopi)';}await api(copy||!current?'entries':`entries/${current.id}`,copy||!current?'POST':'PUT',d);dirty=false;modal.close();await refresh();}catch(e){$('form-error').textContent=e.message;}finally{$('save').disabled=false;}}
form.oninput=()=>{dirty=true;};form.onsubmit=e=>{e.preventDefault();save();};
$('close').onclick=close;modal.addEventListener('cancel',e=>{e.preventDefault();close();});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
$('new').onclick=()=>edit();
for(const id of ['search','board','sensor','kind','status'])$(id).addEventListener('input',render);
$('copy').onclick=async()=>{try{await navigator.clipboard.writeText(form.elements.yaml.value);$('form-error').textContent='YAML er kopieret.';}catch{$('form-error').textContent='Markér koden i YAML-feltet og kopiér manuelt.';}};
$('download').onclick=()=>download((form.elements.name.value||'espscripts').replace(/[^a-z0-9_-]/gi,'-')+'.yaml',form.elements.yaml.value,'text/yaml;charset=utf-8');
$('duplicate').onclick=()=>{if(form.reportValidity())save(true);};
$('history').onclick=async()=>{try{const history=await api(`entries/${current.id}/history`);const area=$('revisions');area.replaceChildren(el('h3','Versionshistorik'));for(const r of history){const n=el('details',undefined,'revision');n.append(el('summary',`Version ${r.version} · ${new Date(r.updated_at).toLocaleString('da-DK')} · ${statuses[r.status]}`),el('p',r.change_note||'Ingen ændringsnote'),el('pre',JSON.stringify(Object.fromEntries(Object.entries(r).filter(([k])=>!['yaml','id'].includes(k))),null,2)),el('pre',r.yaml));const b=el('button','Indlæs denne version i editoren');b.type='button';b.onclick=()=>{const latest=current;modal.close();edit(r);current=latest;form.elements.change_note.value=`Gendannet fra version ${r.version}`;dirty=true;$('form-error').textContent='Historisk version indlæst. Gem for at oprette en ny version.';};n.append(b);area.append(n);}}catch(e){$('form-error').textContent=e.message;}};
$('backup').onclick=async()=>{try{download('espscripts-backup.json',JSON.stringify(await api('backup'),null,2),'application/json');}catch(e){error(e);}};
$('import-yaml').onclick=()=>$('file-yaml').click();
$('file-yaml').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(f.size>500000)throw new Error('YAML-filen er for stor (maks. 500 kB).');edit();form.elements.name.value=f.name.replace(/\.ya?ml$/i,'');form.elements.yaml.value=await f.text();dirty=true;}catch(e){error(e);}e.target.value='';};
$('import-backup').onclick=()=>$('file-backup').click();
$('file-backup').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(f.size>32*1024*1024)throw new Error('Backup er for stor (maks. 32 MB).');const data=JSON.parse(await f.text());if(!confirm('Importér backup som nye kopier med versionshistorik? Eksisterende opsætninger bevares.'))return;const result=await api('import','POST',data);await refresh();$('message').textContent=`${result.imported} opsætninger importeret.`;}catch(e){error(e);}e.target.value='';};
refresh().catch(error);
