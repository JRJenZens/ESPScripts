'use strict';
const $ = id => document.getElementById(id);
const form = $('form'), modal = $('editor');
const statuses = {tested:'Testet',untested:'Ikke testet',issues:'Har problemer'};
const kinds = {block:'Sensorblok',complete:'Komplet opsætning',standard:'Standardprint'};
let entries = [], current = null, dirty = false, catalog = {boards:[],sensors:[]}, view='library', stage=1, catalogLimit=60, pickerKind='boards', pickerLimit=60, catalogEditing=null,catalogMeta={},importMatch=null;
function el(tag, text, cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
async function api(path,method='GET',body) {
 const response=await fetch('api/'+path,{method,headers:{'Content-Type':'application/json','X-ESPScripts':'1'},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json(); if(!response.ok)throw new Error(data.error||'Forespørgslen mislykkedes.'); return data;
}
const tokens = s => s.split(',').map(s=>s.trim()).filter(Boolean);
async function refresh(){ [entries,catalog]=await Promise.all([api('entries'),api('catalog')]); filters(); render(); stats(); boardOptions(); if(['boards','sensors'].includes(view))catalogRender();if(view==='standards')standardsRender(); }
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
 if(!filtered.length){const n=el('div',undefined,'empty');const img=el('img');img.src='static/workbench.svg';img.alt='';n.append(img,el('h3',entries.length?'Ingen match':'Din næste gode løsning starter her'),el('p',entries.length?'Prøv at ændre søgning eller filtre.':'Vælg et board fra kataloget, eller importér en YAML-fil, du allerede har. Så er den nem at finde næste gang.'));const b=el('button',entries.length?'Nulstil filtre':'＋ Opret første opsætning','primary');b.onclick=()=>{if(!entries.length)return edit();for(const id of ['search','board','sensor','kind','status'])$(id).value='';render();};n.append(b);$('cards').append(n);}
 for(const e of filtered){
  const n=el('article',undefined,'card'),art=hardwareArt('boards',(e.board.match(/ESP32[- ]?(?:C\d+|S\d+|P\d+|H\d+)?/i)||['ESP32'])[0]),body=el('div',undefined,'card-body'),badges=el('div',undefined,'meta');
  badges.append(el('span',(e.status==='tested'?'✓ ':'○ ')+statuses[e.status],'badge '+e.status),el('span',kinds[e.kind],'badge'));
  body.append(badges,el('h3',e.name),el('p',[e.board,e.sensors].filter(Boolean).join(' · ')));if(e.description)body.append(el('p',e.description));
  const tags=el('div',undefined,'meta');e.tags.slice(0,4).forEach(t=>tags.append(el('span',t,'badge')));body.append(tags);
  const bottom=el('div',undefined,'card-bottom'),b=el('button','Åbn opsætning →');b.onclick=()=>edit(e);bottom.append(el('small',`v${e.version} · ${new Date(e.updated_at).toLocaleDateString('da-DK')}`),b);body.append(bottom);n.append(art,body);$('cards').append(n);
 }
}
function edit(entry=null){current=entry;form.reset();$('form-error').textContent='';$('revisions').replaceChildren();for(const name of ['name','board','sensors','kind','status','tested_on','esphome_version','description','wiring','yaml','notes','tags']){if(entry)form.elements[name].value=name==='tags'?entry.tags.join(', '):entry[name];}$('editor-title').textContent=entry?entry.name:'Ny opsætning';$('history').hidden=!entry;dirty=false;setStage(1);syncSensors();modal.showModal();}
function values(){const d=Object.fromEntries(new FormData(form));d.tags=tokens(d.tags);if(current)d.version=current.version;return d;}
function close(){if(dirty&&!confirm('Du har ugemte ændringer. Vil du lukke?'))return;modal.close();dirty=false;}
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type}));const a=el('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);}
function error(e){$('message').textContent=e.message;}
async function save(copy=false){if(!form.elements.name.value.trim()){setStage(1);form.elements.name.reportValidity();return;}if(!form.elements.yaml.value.trim()){setStage(2);form.elements.yaml.reportValidity();return;}$('form-error').textContent='';$('save').disabled=true;try{const d=values();if(copy){d.status='untested';d.tested_on='';d.change_note='Kopi af '+(current?.name||d.name);d.name+=' (kopi)';}await api(copy||!current?'entries':`entries/${current.id}`,copy||!current?'POST':'PUT',d);dirty=false;modal.close();await refresh();switchView('library');}catch(e){if(e.message.startsWith('YAML'))setStage(2);$('form-error').textContent=e.message;}finally{$('save').disabled=false;}}
form.noValidate=true;form.oninput=()=>{dirty=true;syncSensors();$('template-hint').hidden=form.elements.kind.value!=='standard';};form.onsubmit=e=>{e.preventDefault();if(stage<3)setStage(stage+1);else save();};
$('close').onclick=close;modal.addEventListener('cancel',e=>{e.preventDefault();close();});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
$('new').onclick=()=>edit();
for(const id of ['search','board','sensor','kind','status'])$(id).addEventListener('input',render);
$('copy').onclick=async()=>{try{await navigator.clipboard.writeText(form.elements.yaml.value);$('form-error').textContent='YAML er kopieret.';}catch{$('form-error').textContent='Markér koden i YAML-feltet og kopiér manuelt.';}};
$('download').onclick=()=>download((form.elements.name.value||'espscripts').replace(/[^a-z0-9_-]/gi,'-')+'.yaml',form.elements.yaml.value,'text/yaml;charset=utf-8');
$('duplicate').onclick=()=>save(true);
$('history').onclick=async()=>{try{const history=await api(`entries/${current.id}/history`);const area=$('revisions');area.replaceChildren(el('h3','Versionshistorik'));for(const r of history){const n=el('details',undefined,'revision');n.append(el('summary',`Version ${r.version} · ${new Date(r.updated_at).toLocaleString('da-DK')} · ${statuses[r.status]}`),el('p',r.change_note||'Ingen ændringsnote'),el('pre',JSON.stringify(Object.fromEntries(Object.entries(r).filter(([k])=>!['yaml','id'].includes(k))),null,2)),el('pre',r.yaml));const b=el('button','Indlæs denne version i editoren');b.type='button';b.onclick=()=>{const latest=current;modal.close();edit(r);current=latest;form.elements.change_note.value=`Gendannet fra version ${r.version}`;dirty=true;setStage(3);$('form-error').textContent='Historisk version indlæst. Gem for at oprette en ny version.';};n.append(b);area.append(n);}}catch(e){$('form-error').textContent=e.message;}};
$('backup').onclick=async()=>{try{download('espscripts-backup.json',JSON.stringify(await api('backup'),null,2),'application/json');}catch(e){error(e);}};
$('import-yaml').onclick=()=>$('file-yaml').click();
$('file-yaml').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(f.size>500000)throw new Error('YAML-filen er for stor (maks. 500 kB).');edit();form.elements.name.value=f.name.replace(/\.ya?ml$/i,'');form.elements.yaml.value=await f.text();if(/^esphome:/m.test(form.elements.yaml.value))form.elements.kind.value='complete';setStage(2);dirty=true;}catch(e){error(e);}e.target.value='';};
$('import-backup').onclick=()=>$('file-backup').click();
$('file-backup').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(f.size>32*1024*1024)throw new Error('Backup er for stor (maks. 32 MB).');const data=JSON.parse(await f.text());if(!confirm('Importér backup som nye kopier med versionshistorik? Eksisterende opsætninger bevares.'))return;const result=await api('import','POST',data);await refresh();$('message').textContent=`${result.imported} opsætninger importeret.`;}catch(e){error(e);}e.target.value='';};


function stats(){
 $('total-entries').textContent=entries.length;$('tested-count').textContent=entries.filter(e=>e.status==='tested').length+' testede';
 $('total-boards').textContent=catalog.boards.length;$('total-sensors').textContent=catalog.sensors.length;
}
function hardwareArt(kind,family=''){
 const art=el('div',undefined,'card-art'+(kind==='sensors'?' sensor-art':'')),img=el('img');img.src=kind==='boards'?'static/board.svg':'static/sensor.svg';img.alt='';art.append(img);if(family)art.append(el('span',family,'family'));return art;
}
function boardOptions(){const list=$('board-options');list.replaceChildren();for(const b of catalog.boards.filter(b=>b.hardware_type!=='expansion')){list.append(new Option(b.category||'',b.name));}}
function switchView(next){
 view=next;for(const k of ['library','standards','boards','sensors']){const n=$('nav-'+k);n.classList.toggle('active',k===view);if(k===view)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');}
 $('library-view').hidden=view!=='library';$('catalog-view').hidden=!['boards','sensors'].includes(view);$('standards-view').hidden=view!=='standards';if(view==='standards')standardsRender();
 if(['boards','sensors'].includes(view)){
  catalogLimit=60;$('catalog-search').value='';$('catalog-source').value='';$('catalog-title').textContent=view==='boards'?'Find dit næste board':'Sensorer til dine idéer';
  $('catalog-description').textContent=view==='boards'?'Gå på opdagelse i ESP32-familien. Vælg et board til en ny opsætning, eller tilføj din egen model.':'Find en ESPHome-komponent til dit projekt. Vælg flere sensorer, når du opretter en opsætning, eller tilføj dine egne.';
  $('add-catalog').textContent=view==='boards'?'＋ Tilføj eget board':'＋ Tilføj egen sensor';catalogCategories();catalogRender();
 }
}
function catalogCategories(){const select=$('catalog-category'),old=select.value;select.replaceChildren(new Option('Alle kategorier',''));[...new Set(catalog[view].map(x=>x.category).filter(Boolean))].sort().forEach(v=>select.add(new Option(v,v)));select.value=[...select.options].some(x=>x.value===old)?old:'';}
function sensorLabel(item){return item.custom?item.name:item.id.split('.').slice(1).join('.').replaceAll('_',' ').toUpperCase();}
function catalogRender(){
 const query=$('catalog-search').value.toLocaleLowerCase('da').trim(),category=$('catalog-category').value,source=$('catalog-source').value;
 const items=catalog[view].filter(x=>(!query||[x.name,x.category,x.detail].join(' ').toLocaleLowerCase('da').includes(query))&&(!category||x.category===category)&&(!source||x.custom===(source==='custom'))).sort((a,b)=>a.name.localeCompare(b.name,'da'));
 const area=$('catalog-cards');area.replaceChildren();$('catalog-count').textContent=`${items.length} ${view==='boards'?'boards':'sensorkomponenter'} · viser ${Math.min(catalogLimit,items.length)}`;
 if(!items.length){const empty=el('div',undefined,'empty');empty.append(el('h3','Mangler din model?'),el('p','Tilføj den til dit eget katalog. Den er klar til brug med det samme.'));const b=el('button','＋ Tilføj model','primary');b.onclick=()=>catalogEdit();empty.append(b);area.append(empty);}
 for(const item of items.slice(0,catalogLimit)){
  const n=el('article',undefined,'card'),body=el('div',undefined,'card-body'),meta=el('div',undefined,'meta');meta.append(el('span',item.category||'Egen model','badge'));if(item.custom)meta.append(el('span','Egen model','badge custom'));if(item.hardware_type==='expansion')meta.append(el('span','Udvidelsesboard','badge expansion'));
  body.append(meta,el('h3',item.name),el('p',item.detail||'Egen katalogpost'));if(item.description)body.append(el('p',item.description,'card-description'));
  if(item.docs_url){const link=el('a','Dokumentation ↗');link.href=item.docs_url;link.target='_blank';link.rel='noopener noreferrer';body.append(link);}
  const bottom=el('div',undefined,'card-bottom'),use=el('button',item.hardware_type==='expansion'?'Brug som modul →':(view==='boards'?'Brug board →':'Brug sensor →'));use.onclick=()=>{edit();if(view==='boards'&&item.hardware_type!=='expansion')form.elements.board.value=item.name;else form.elements.sensors.value=sensorLabel(item);syncSensors();dirty=true;};bottom.append(use);
  if(item.custom){const b=el('button','Redigér');b.onclick=()=>catalogEdit(item);bottom.append(b);}body.append(bottom);n.append(hardwareArt(item.hardware_type==='expansion'?'sensors':view,item.category),body);area.append(n);
 }
 if(items.length>catalogLimit){const more=el('button','Vis flere modeller ↓');more.onclick=()=>{catalogLimit+=60;catalogRender();};area.append(more);}
}
function setStage(next){$('template-hint').hidden=form.elements.kind.value!=='standard';stage=Math.max(1,Math.min(3,next));for(let i=1;i<=3;i++){$('stage-'+i).hidden=i!==stage;$('step-'+i).classList.toggle('active',i===stage);$('step-'+i).setAttribute('aria-current',i===stage?'step':'false');}$('prev-step').hidden=stage===1;$('next-step').hidden=stage===3;$('save').hidden=stage!==3;$('next-step').textContent=stage===1?'Videre til YAML →':'Videre til test →';$('step-caption').textContent=`Trin ${stage} af 3`;$('save').textContent=current?'Gem ny version':'Gem opsætning';}
function syncSensors(){
 const area=$('selected-sensors');area.replaceChildren();for(const name of tokens(form.elements.sensors.value)){const b=el('button',name+' ×');b.type='button';b.setAttribute('aria-label','Fjern sensor '+name);b.onclick=()=>{form.elements.sensors.value=tokens(form.elements.sensors.value).filter(x=>x!==name).join(', ');dirty=true;syncSensors();};area.append(b);}
}
function openPicker(kind){pickerKind=kind;pickerLimit=60;$('picker-search').value='';$('picker-title').textContent=kind==='boards'?'Vælg dit ESP32-board':'Vælg én eller flere sensorer';pickerRender();$('picker').showModal();}
function pickerRender(){
 const pool=pickerKind==='boards'?catalog.boards.filter(x=>x.hardware_type!=='expansion'):[...catalog.sensors,...catalog.boards.filter(x=>x.hardware_type==='expansion')];
 const q=$('picker-search').value.trim().toLocaleLowerCase('da'),items=pool.filter(x=>[x.name,x.category,x.detail].join(' ').toLocaleLowerCase('da').includes(q)).sort((a,b)=>a.name.localeCompare(b.name,'da'));
 const area=$('picker-items');area.replaceChildren();$('picker-count').textContent=`${items.length} modeller fundet`;
 for(const item of items.slice(0,pickerLimit)){
  const selected=pickerKind==='boards'?form.elements.board.value===item.name:tokens(form.elements.sensors.value).includes(sensorLabel(item));
  const row=el('button',undefined,'picker-row'+(selected?' selected':'')),img=el('img'),label=el('span');img.src=pickerKind==='boards'?'static/board.svg':'static/sensor.svg';img.alt='';label.append(el('strong',item.name),el('small',[item.category,item.detail].filter(Boolean).join(' · ')));row.append(img,label,el('span',selected?'✓':'+','check'));row.setAttribute('aria-pressed',String(selected));
  row.onclick=()=>{if(pickerKind==='boards'){form.elements.board.value=item.name;$('picker').close();}else{const names=tokens(form.elements.sensors.value),name=sensorLabel(item);form.elements.sensors.value=(names.includes(name)?names.filter(x=>x!==name):[...names,name]).join(', ');syncSensors();pickerRender();}dirty=true;};area.append(row);
 }
 if(!items.length)area.append(el('p','Ingen match. Du kan skrive din model direkte i opsætningen eller tilføje den under Boards / Sensorer.','hint'));
 if(items.length>pickerLimit){const b=el('button','Vis flere modeller ↓');b.onclick=()=>{pickerLimit+=60;pickerRender();};area.append(b);}
}
function catalogEdit(item=null,draft=null){
 catalogEditing=item;const data=item||draft,catalogKind=data?.kind||view;catalogMeta=data?.esphome||{};const f=$('catalog-form');f.reset();$('catalog-error').textContent='';$('catalog-editor-title').textContent=draft?'Kontrollér model fra link':(item?'Redigér ':'Tilføj ')+(catalogKind==='boards'?'board':'sensor');
 f.elements.hardware_type.value=data?.hardware_type||(catalogKind==='sensors'?'sensor':'other');
 if(data)for(const k of ['name','category','detail','docs_url','description'])f.elements[k].value=data[k]||'';
 $('catalog-import-notice').hidden=!draft;if(draft)$('catalog-import-notice').textContent='Forslag fra produktsiden. Kontrollér hardwaretype og felter før du gemmer. ESPHome-understøttelse og fysisk test er ikke bekræftet.';
 $('catalog-existing').hidden=!draft||!importMatch;if(draft&&importMatch)$('catalog-existing-text').textContent='Vi fandt en eksisterende model: '+importMatch.name+'. Brug den, eller gem oplysningerne som din egen udgave.';
 $('catalog-editor').showModal();
}
$('catalog-form').onsubmit=async e=>{
 e.preventDefault();const submit=e.submitter;submit.disabled=true;$('catalog-error').textContent='';
 try{const data=Object.fromEntries(new FormData($('catalog-form')));data.kind=data.hardware_type==='sensor'?'sensors':'boards';data.esphome=data.hardware_type==='esp32'?{...catalogMeta}:{};if(data.esphome.board&&data.detail!==data.esphome.board)data.esphome.board=data.detail;if(data.hardware_type==='esp32'){const variant=data.category.toLowerCase().replaceAll('-','').replaceAll(' ','');if(/^esp32(?:c[2356]|c61|s[23]|h2|p4)?$/.test(variant))data.esphome.variant=variant;else delete data.esphome.variant;}if(catalogEditing)data.version=catalogEditing.version;await api('catalog'+(catalogEditing?'/'+catalogEditing.id:''),catalogEditing?'PUT':'POST',data);$('catalog-editor').close();switchView(data.kind);$('catalog-search').value='';$('catalog-source').value='custom';$('catalog-category').value='';await refresh();catalogCategories();catalogRender();}catch(e){$('catalog-error').textContent=e.message;}finally{submit.disabled=false;}
};
for(const k of ['library','boards','sensors']){$('nav-'+k).onclick=()=>switchView(k);$('stat-'+k).onclick=()=>switchView(k);}
for(const id of ['catalog-search','catalog-category','catalog-source'])$(id).addEventListener('input',()=>{catalogLimit=60;catalogRender();});
for(let i=1;i<=3;i++)$('step-'+i).onclick=()=>setStage(i);
$('next-step').onclick=()=>{if(stage===1&&!form.elements.name.value.trim()){form.elements.name.reportValidity();return;}setStage(stage+1);};$('prev-step').onclick=()=>setStage(stage-1);
$('pick-board').onclick=()=>openPicker('boards');$('pick-sensors').onclick=()=>openPicker('sensors');$('picker-close').onclick=()=>$('picker').close();$('picker-search').oninput=()=>{pickerLimit=60;pickerRender();};
$('add-catalog').onclick=()=>catalogEdit();$('catalog-close').onclick=()=>$('catalog-editor').close();
refresh().catch(error);

let defaultStandard='', generatorTemplate='', generatorInEditor=false;
async function loadStandard(){if(!defaultStandard){const r=await fetch('static/standardprint.yaml');if(!r.ok)throw new Error('Standardprint kunne ikke hentes.');defaultStandard=await r.text();}return defaultStandard;}
function standardsRender(){
 const area=$('standard-cards');area.replaceChildren();
 const templates=[{name:'Standardprint · COMMON + WireGuard',description:'Enhedsnavn, secrets, fælles base, WireGuard og ESP-IDF. Klar som udgangspunkt for dit næste ESP32-print.',builtin:true},...entries.filter(e=>e.kind==='standard')];
 for(const t of templates){const n=el('article',undefined,'card'),body=el('div',undefined,'card-body');body.append(el('span',t.builtin?'Indbygget standardprint':'Eget standardprint · v'+t.version,'badge'),el('h3',t.name),el('p',t.description||'Din egen grundskabelon til nye print.'));const bottom=el('div',undefined,'card-bottom'),use=el('button','Brug standardprint →');use.onclick=()=>openStandard(t.builtin?null:t,false);const editButton=el('button',t.builtin?'Tilpas som egen':'Redigér');editButton.onclick=async()=>{try{edit(t.builtin?null:t);if(t.builtin){form.elements.name.value='Mit standardprint';form.elements.kind.value='standard';form.elements.yaml.value=await loadStandard();form.elements.description.value=t.description;dirty=true;}setStage(2);}catch(e){error(e);}};bottom.append(use,editButton);body.append(bottom);n.append(hardwareArt('boards','COMMON / HARDWARE'),body);area.append(n);}
}
async function openStandard(template=null,inEditor=false){
 try{generatorTemplate=template?template.yaml:await loadStandard();generatorInEditor=inEditor;if(!generatorTemplate.includes('{{device_name}}'))throw new Error('Standardprintet mangler {{device_name}}. Tilpas skabelonen først, så en ny enhed får sit eget navn.');const f=$('standard-form');f.reset();$('standard-error').textContent='';if(inEditor){const selected=catalog.boards.find(b=>b.name===form.elements.board.value),variant=selected?.esphome?.variant;if(variant&&[...f.elements.variant.options].some(o=>o.value===variant))f.elements.variant.value=variant;}$('standard-generator').showModal();}catch(e){error(e);}
}
$('standard-form').elements.device_name.oninput=e=>{const f=$('standard-form');f.elements.friendly_name.placeholder=e.target.value.toUpperCase()||'ESP32-019';f.elements.secret_prefix.placeholder=e.target.value.replaceAll('-','_')||'esp32_019';};
$('standard-form').onsubmit=e=>{
 e.preventDefault();const f=$('standard-form'),d=Object.fromEntries(new FormData(f));d.friendly_name=d.friendly_name||d.device_name.toUpperCase();d.secret_prefix=d.secret_prefix||d.device_name.replaceAll('-','_');
 if(generatorInEditor&&form.elements.yaml.value.trim()&&!confirm('Erstat YAML i editoren med standardprintet? Du kan stadig lukke uden at gemme.'))return;
 // Placeholder values are escaped for YAML double-quoted strings. No YAML is executed.
 const yaml=generatorTemplate.replace(/\{\{(device_name|friendly_name|secret_prefix|variant|flash_size)\}\}/g,(_,key)=>JSON.stringify(d[key]).slice(1,-1));
 if(/\{\{[^{}]+\}\}/.test(yaml)){$('standard-error').textContent='Skabelonen indeholder ukendte pladsholdere. Brug device_name, friendly_name, secret_prefix, variant eller flash_size.';return;}
 $('standard-generator').close();if(!generatorInEditor)edit();form.elements.yaml.value=yaml;form.elements.kind.value='complete';if(!form.elements.name.value.trim())form.elements.name.value=d.friendly_name;if(!form.elements.board.value.trim())form.elements.board.value=d.variant.toUpperCase().replace('ESP32','ESP32-').replace(/-$/,'');form.elements.status.value='untested';form.elements.tested_on.value='';form.elements.change_note.value='Oprettet fra standardprint';dirty=true;setStage(2);
};
$('nav-standards').onclick=()=>switchView('standards');$('standard-close').onclick=()=>$('standard-generator').close();$('insert-standard').onclick=()=>openStandard(null,true);$('new-standard').onclick=async()=>{try{edit();form.elements.name.value='Mit standardprint';form.elements.kind.value='standard';form.elements.yaml.value=await loadStandard();dirty=true;setStage(2);}catch(e){error(e);}};

function openLinkImport(){
 $('link-form').reset();$('link-error').textContent='';$('link-progress').hidden=true;$('link-fetch').disabled=false;$('link-importer').showModal();
}
$('import-link').onclick=openLinkImport;$('import-link-catalog').onclick=openLinkImport;$('link-close').onclick=()=>$('link-importer').close();
$('example-mmwave').onclick=()=>{$('link-form').elements.url.value='https://wiki.seeedstudio.com/mmwave_for_xiao/';};
$('example-xiao').onclick=()=>{$('link-form').elements.url.value='https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/';};
let linkRequest=0;
$('link-form').onsubmit=async e=>{
 e.preventDefault();const requestNumber=++linkRequest;$('link-fetch').disabled=true;$('link-progress').hidden=false;$('link-error').textContent='';
 try{const result=await api('catalog/preview-link','POST',{url:$('link-form').elements.url.value.trim()});if(requestNumber!==linkRequest||!$('link-importer').open)return;importMatch=result.existing;const draft=result.draft;if(importMatch&&importMatch.name.toLocaleLowerCase('da')===draft.name.toLocaleLowerCase('da'))draft.name+=' (egen udgave)';$('link-importer').close();catalogEdit(null,draft);}catch(e){if(requestNumber===linkRequest)$('link-error').textContent=e.message;}finally{if(requestNumber===linkRequest){$('link-fetch').disabled=false;$('link-progress').hidden=true;}}
};
$('link-importer').addEventListener('close',()=>{linkRequest++;});
$('use-existing').onclick=()=>{if(!importMatch)return;const match=importMatch;$('catalog-editor').close();switchView(match.kind);$('catalog-search').value=match.name;catalogRender();};
