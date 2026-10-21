/* Design-only interactions. No scientific computations or backend calls. */
const $ = id => document.getElementById(id);
const STORAGE = 'pyflash-picture-design-v1';
const MEASURES = {Iba1_VolumeMean:'Iba1 mean volume (µm³)',Iba1_SurfaceMean:'Iba1 mean surface area (µm²)'};
const SHORT_LABELS = {'All pairwise comparisons (default)':'Every pair of groups','Subject summaries (automatic)':'Automatic · subjects','Mixed model using region-level data':'Mixed model · regions','Normalize to 0–1 (default)':'0–1 normalized (default)','Standardize to z-scores':'Z-scores','Automatic (package default)':'Automatic (default)'};
const GROUPS = [
  ['SynWeekTwo','SynmCherry · 2 weeks'],['hAPPWeekTwo','hAPP WT · 2 weeks'],['NLGFWeekTwo','hAPP NLGF · 2 weeks'],
  ['SynWeekFour','SynmCherry · 4 weeks'],['hAPPWeekFour','hAPP WT · 4 weeks'],['NLGFWeekFour','hAPP NLGF · 4 weeks'],
  ['SynWeekEight','SynmCherry · 8 weeks'],['hAPPWeekEight','hAPP WT · 8 weeks'],['NLGFWeekEight','hAPP NLGF · 8 weeks']
];
const EXAMPLES = [
  {id:'mean_bars',title:'Group comparison',subtitle:'Means & subject points',kind:'Plot',picture:'bars',search:'bars compare groups mean_bars',unit:'Each point is one subject summary.',required:['measurement'],defaults:{measurement:'Iba1_VolumeMean',stats_test:'auto',normalize:false,points:true}},
  {id:'regressions',title:'Relationship',subtitle:'Two measurements',kind:'Plot',picture:'scatter',search:'scatter relationship regression regressions',unit:'Each point is one subject with both measurements.',required:['x','y'],defaults:{x:'Iba1_VolumeMean',y:'Iba1_SurfaceMean',test:'pearsonr',normalize_x:true,normalize_y:true,combine:false}},
  {id:'histograms',title:'Distribution',subtitle:'Individual object values',kind:'Plot',picture:'histogram',search:'distribution histogram histograms objects',unit:'Each observation is one segmented object, not one subject.',required:['marker','x_attr'],defaults:{marker:'Iba1',x_attr:'Iba1_Volume',bins:30,stat:'count',combine:false,kde:false}},
  {id:'group_comparison_pipeline',title:'Group comparison',subtitle:'Statistics & several outputs',kind:'Pipeline',picture:'pipeline',search:'pipeline groups effects statistics group_comparison_pipeline',unit:'Tests use subject summaries by default.',required:['measurement'],defaults:{measurement:'Iba1_VolumeMean',engine:'auto',control:'',screen:false,alpha:.05,plot_volcano:true,plot_forest:true,plot_stats_matrix:true,plot_bars:true,plot_superplots:false,n_boot:2000}}
];
const initialDraft = example => ({...example.defaults,groups:GROUPS.map(g=>g[0]),style:{accent:'teal',pointSize:5,legend:true}});
let state = {selected:'mean_bars',drafts:Object.fromEntries(EXAMPLES.map(e=>[e.id,initialDraft(e)])),results:{},history:[],theme:matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'};
try { const stored = JSON.parse(localStorage.getItem(STORAGE)); if(stored?.version===1) state={...state,...stored.state}; } catch {}
let running = null, timer = null, reviewState = 'ready';
const e = () => EXAMPLES.find(x=>x.id===state.selected) || EXAMPLES[0];
const draft = () => state.drafts[e().id];
const escapeHTML = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone = value => JSON.parse(JSON.stringify(value));
const save = () => {try {localStorage.setItem(STORAGE,JSON.stringify({version:1,state}));} catch {}};
const checked = value => value?' checked':'';
const option = (value,label,current) => `<option value="${escapeHTML(value)}"${String(current)===String(value)?' selected':''}>${escapeHTML(label)}</option>`;
function select(name,label,choices,current,help='') {
  const currentLabel=choices.find(([value])=>String(value)===String(current))?.[1]||label;
  return `<label class="field"><span>${label}</span><select name="${name}" title="${escapeHTML(label+': '+currentLabel+(help?' — '+help:''))}">${choices.map(([v,t])=>option(v,SHORT_LABELS[t]||t,current)).join('')}</select>${help?`<small>${help}</small>`:''}</label>`;
}
function measure(name,label,current){return select(name,label,[['','Choose a measurement'],...Object.entries(MEASURES)],current);}
function toggle(name,label,current,help=''){return `<label class="check"><input type="checkbox" name="${name}"${checked(current)} title="${escapeHTML(help||label)}">${label}</label>`;}
function miniature(picture){
  const shapes={bars:'<rect x="15" y="29" width="12" height="17"/><rect x="39" y="15" width="12" height="31"/><rect x="63" y="22" width="12" height="24"/><g fill="white" stroke="currentColor"><circle cx="21" cy="24" r="3"/><circle cx="45" cy="12" r="3"/><circle cx="69" cy="19" r="3"/></g>',scatter:'<path d="M15 44 76 10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="20" cy="40" r="3"/><circle cx="32" cy="30" r="3"/><circle cx="43" cy="34" r="3"/><circle cx="56" cy="19" r="3"/><circle cx="69" cy="13" r="3"/>',histogram:'<rect x="13" y="39" width="10" height="7"/><rect x="24" y="25" width="10" height="21"/><rect x="35" y="10" width="10" height="36"/><rect x="46" y="15" width="10" height="31"/><rect x="57" y="31" width="10" height="15"/><rect x="68" y="41" width="10" height="5"/>',pipeline:'<g fill="none" stroke="currentColor" stroke-width="2"><rect x="8" y="18" width="18" height="21" rx="3"/><path d="M28 28h8m-4-4 4 4-4 4"/><rect x="40" y="18" width="18" height="21" rx="3"/><path d="M60 28h8m-4-4 4 4-4 4"/><rect x="72" y="18" width="12" height="21" rx="3"/></g>'};
  return `<svg viewBox="0 0 90 56" aria-hidden="true" focusable="false" fill="currentColor"><path d="M8 5v44h78" fill="none" stroke="currentColor" stroke-width="1" opacity=".35"/>${shapes[picture]}</svg>`;
}
function gallery(){
  const query=$('search').value.trim().toLowerCase(), matches=EXAMPLES.filter(x=>(x.search+' '+x.title+' '+x.subtitle).toLowerCase().includes(query));
  $('gallery').innerHTML=['Plot','Pipeline'].map(kind=>{const items=matches.filter(x=>x.kind===kind);return items.length?`<section><h2>${kind==='Plot'?'Plots':'Pipelines'}</h2>${items.map(x=>`<button type="button" class="choice" data-example="${x.id}" title="Set up ${x.title.toLowerCase()} ${x.kind.toLowerCase()}" aria-current="${x.id===e().id}">${miniature(x.picture)}<span><strong>${x.title}</strong><small>${x.subtitle}</small></span></button>`).join('')}</section>`:'';}).join('');
  $('empty-search').hidden=matches.length>0;
}
function groupsHTML(d){return `<details class="groups"><summary title="Choose which of the dataset's groups to include">Groups · ${d.groups.length} selected</summary><div class="group-list">${GROUPS.map(([key,label])=>`<label class="check"><input type="checkbox" name="groups" value="${key}"${checked(d.groups.includes(key))} title="Include ${label}">${label}</label>`).join('')}</div></details>`;}
function form(){
  const x=e(),d=draft(); let body='';
  if(x.id==='mean_bars') body=measure('measurement','Measurement',d.measurement)+groupsHTML(d)+select('stats_test','Statistical test',[['auto','Automatic (package default)'],['student_t',"Student’s t-test"],['welch_t',"Welch’s t-test"],['mannwhitney','Mann–Whitney'],['anova','One-way analysis of variance'],['welch_anova','Welch analysis of variance'],['kruskal','Kruskal–Wallis']],d.stats_test,'Automatic checks select the supported test for these inputs.')+`<details class="advanced"><summary title="Change less frequent group comparison settings">Advanced</summary>${toggle('normalize','Normalize values',d.normalize)}${toggle('points','Show subject points',d.points)}</details>`;
  if(x.id==='regressions') body=measure('x','Horizontal measurement',d.x)+measure('y','Vertical measurement',d.y)+groupsHTML(d)+select('test','Association',[['pearsonr','Pearson correlation'],['spearmanr','Spearman correlation'],['kendalltau','Kendall correlation']],d.test)+`<details class="advanced" open><summary title="Inspect normalization and group layout choices">Scale & grouping</summary>${select('normalize_x','Horizontal scale',[[true,'Normalize to 0–1 (default)'],[false,'Original units'],['Z-score','Standardize to z-scores']],d.normalize_x)}${select('normalize_y','Vertical scale',[[true,'Normalize to 0–1 (default)'],[false,'Original units'],['Z-score','Standardize to z-scores']],d.normalize_y)}${toggle('combine','Overlay groups in one figure',d.combine)}</details>`;
  if(x.id==='histograms') body=select('marker','Object marker',[['','Choose a marker'],['Iba1','Iba1']],d.marker)+select('x_attr','Object measurement',[['','Choose an attribute'],['Iba1_Volume','Volume (µm³)']],d.x_attr)+groupsHTML(d)+`<label class="field"><span>Number of bins</span><input name="bins" type="number" min="1" max="200" value="${d.bins}" title="How many intervals to use for the histogram"></label>`+select('stat','Vertical axis',[['count','Object count'],['probability','Probability'],['density','Density']],d.stat)+`<details class="advanced"><summary title="Change histogram overlay and density options">Advanced</summary>${toggle('combine','Overlay groups in one figure',d.combine,'Combined plots share the same bin edges.')}${toggle('kde','Show density curve',d.kde)}</details>`;
  if(x.kind==='Pipeline') body=`<h2 class="section-title"><span>1</span> Data</h2>`+measure('measurement','Measurement',d.measurement)+groupsHTML(d)+select('control','Compare against',[['','All pairwise comparisons (default)'],...GROUPS],d.control)+`<h2 class="section-title"><span>2</span> Analysis</h2>`+select('engine','Method',[['auto','Subject summaries (automatic)'],['mixed','Mixed model using region-level data'],['bootstrap','Hierarchical bootstrap']],d.engine,'Region-level methods can fall back to subject summaries; the run records which was used.')+toggle('screen','Treat measurements as an exploratory screen',d.screen,'Adds false-discovery-rate results across endpoints; raw p-values remain reported.')+`<h2 class="section-title" style="margin-top:.8rem"><span>3</span> Outputs</h2><fieldset class="fieldset"><legend class="muted">Figures to produce</legend>${toggle('plot_volcano','Volcano',d.plot_volcano)}${toggle('plot_forest','Effect-size forest',d.plot_forest)}${toggle('plot_stats_matrix','Statistics matrix',d.plot_stats_matrix)}${toggle('plot_bars','Per-measurement bars',d.plot_bars)}${toggle('plot_superplots','Subject and region points',d.plot_superplots)}</fieldset><details class="advanced"><summary title="Inspect less frequent pipeline settings">Advanced</summary><label class="field"><span>Significance threshold</span><input name="alpha" type="number" min="0.001" max="0.999" step="0.01" value="${d.alpha}" title="Threshold for declaring significance"></label><label class="field"><span>Bootstrap repetitions</span><input name="n_boot" type="number" min="1" step="100" value="${d.n_boot}" title="Repetitions used by the package bootstrap"></label></details>`;
  $('inputs').innerHTML=`<div class="unit">${x.unit}</div>${body}<p class="error" id="input-error" hidden></p><button class="primary" type="submit" title="Simulate this workflow; no scientific analysis is submitted">${x.kind==='Pipeline'?'Preview pipeline run':'Preview plot'}</button><button class="text-button reset-inputs" id="reset-inputs" type="button" title="Restore this example to source-checked package defaults">Reset inputs</button>`;
  validity();
}
function error(){const d=draft();if(e().required.some(key=>!d[key]))return 'Choose the required measurement before continuing.';if(!d.groups.length)return 'Include at least one group.';if(e().id==='regressions'&&d.x===d.y)return 'Choose two different measurements for this relationship example.';if(e().id==='histograms'&&(!Number.isInteger(d.bins)||d.bins<1||d.bins>200))return 'Use a whole number of bins between 1 and 200 in this preview.';if(e().kind==='Pipeline'&&(!(d.alpha>0&&d.alpha<1)||!Number.isInteger(d.n_boot)||d.n_boot<1))return 'Use a threshold between 0 and 1 and a positive whole number of repetitions.';if(d.control&&!d.groups.includes(d.control))return 'Include the reference group or choose all pairwise comparisons.';return '';}
function validity(){const message=error();$('input-error').textContent=message;$('input-error').hidden=!message;$('inputs').querySelector('[type=submit]').disabled=Boolean(message)||Boolean(running);}
function plot(picture,d){
  const colors={teal:['#087b70','#c6843b','#7565ad'],blue:['#326eab','#c6843b','#527757'],purple:['#7953a4','#278577','#b56f37']}[d.style.accent];
  const size=d.style.pointSize; let marks='',xlabel='Group',ylabel='Measurement';
  if(picture==='bars'){
    [170,320,250].forEach((height,i)=>{const cx=175+i*210;marks+=`<rect x="${cx-44}" y="${415-height}" width="88" height="${height}" fill="${colors[i]}" opacity=".24"/><path d="M${cx} ${395-height}v40m-15-40h30m-30 40h30" stroke="${colors[i]}" stroke-width="2"/>`;[-25,10,38,-7,27].forEach((offset,j)=>{marks+=`<circle cx="${cx+(j%3-1)*15}" cy="${415-height+offset}" r="${size}" fill="white" stroke="${colors[i]}" stroke-width="2"/>`;});marks+=`<text x="${cx}" y="445" text-anchor="middle" font-size="14">Example ${i+1}</text>`;});ylabel='Selected subject measurement';
  } else if(picture==='scatter'){
    for(let i=0;i<24;i++){const group=i%3,x=110+(i*29)%580,y=410-(x-85)*.47+((i*43)%87-44);marks+=`<circle cx="${x}" cy="${y}" r="${size}" fill="${colors[group]}" opacity=".8"/>`;}
    marks+=`<path d="M110 390 700 100" stroke="${colors[0]}" stroke-width="2" fill="none"/>`;xlabel=d.normalize_x===true?'Horizontal measurement (0–1 normalized)':d.normalize_x==='Z-score'?'Horizontal measurement (z-score)':'Horizontal measurement (original units)';ylabel=d.normalize_y===true?'Vertical measurement (0–1 normalized)':d.normalize_y==='Z-score'?'Vertical measurement (z-score)':'Vertical measurement (original units)';
  } else {
    [20,40,65,115,185,265,305,265,225,160,95,45,20,10].forEach((height,i)=>{marks+=`<rect x="${110+i*43}" y="${415-height}" width="40" height="${height}" fill="${colors[0]}" opacity=".65"/>`;});xlabel='Object volume (µm³)';ylabel=d.stat==='count'?'Object count':d.stat==='density'?'Density':'Probability';
  }
  const legend=d.style.legend?`<g transform="translate(120,35)">${['Group A','Group B','Group C'].map((label,i)=>`<circle cx="${i*160}" cy="0" r="4" fill="${colors[i]}"/><text x="${i*160+12}" y="5" font-size="13">${label}</text>`).join('')}</g>`:'';
  return `<svg viewBox="0 0 820 515" role="img" aria-label="Schematic ${picture} preview, not computed from the dataset" xmlns="http://www.w3.org/2000/svg"><rect width="820" height="515" fill="white"/><g fill="#20332f" font-family="Segoe UI, sans-serif">${legend}<g stroke="#e4e9e6" stroke-width="1">${[100,200,300,400].map(y=>`<path d="M90 ${y}H770"/>`).join('')}</g><path d="M90 80V415H770" fill="none" stroke="#62786d"/>${marks}<text x="430" y="487" text-anchor="middle" font-size="15">${xlabel}</text><text transform="translate(28 245) rotate(-90)" text-anchor="middle" font-size="14">${ylabel}</text><text x="770" y="60" text-anchor="end" fill="#61766b" font-size="12">ILLUSTRATION</text></g></svg>`;
}
function pipeline(d,progress){
  const stages=['Prepare inputs','Compare groups','Draw outputs','Record run'];
  const current=progress==null?-1:Math.min(3,Math.floor(progress/25));
  return `<div class="pipeline-results"><div class="headline"><strong>${progress==null?'Example output bundle':'Simulated pipeline progress'}</strong><span>${progress==null?'Illustrative layout':Math.round(progress)+'%'}</span></div><ol class="stage-list">${stages.map((label,i)=>`<li class="${i===current?'current':''}">${i+1}. ${label}</li>`).join('')}</ol>${progress==null?'':`<div class="progress-track"><div class="progress-fill" style="width:${progress}%"></div></div>`}<ul class="output-list">${[['plot_volcano','Volcano'],['plot_forest','Effect-size forest'],['plot_stats_matrix','Statistics matrix'],['plot_bars','Measurement bars'],['plot_superplots','Subject / region points']].filter(([key])=>d[key]).map(([,label])=>`<li>${label}</li>`).join('')}<li>Results table</li><li>Run record</li></ul><div class="pipeline-pair"><section><h3>Selected figures</h3>${plot('bars',d)}</section><section><h3>Effect summaries</h3><svg viewBox="0 0 380 250" role="img" aria-label="Schematic effect summaries, not computed results"><rect width="380" height="250" fill="white"/><path d="M180 35V205" stroke="#ccd8d2" stroke-dasharray="4 4"/>${[60,110,160].map((y,i)=>`<text x="12" y="${y+5}" fill="#20332f" font-size="12">Example ${i+1}</text><path d="M${115+i*25} ${y}H${245+i*15}" stroke="#087b70" stroke-width="2"/><circle cx="${190+i*20}" cy="${y}" r="5" fill="#087b70"/>`).join('')}<text x="190" y="235" text-anchor="middle" fill="#20332f" font-size="13">Illustrative effect size</text></svg></section></div><table><caption style="text-align:left;font-size:.8rem;padding:.3rem 0">Example table structure — no calculated values</caption><thead><tr><th>Measurement</th><th>Comparison</th><th>Effect</th><th>p-value</th></tr></thead><tbody><tr><td>Selected measurement</td><td>Selected groups</td><td>—</td><td>—</td></tr></tbody></table></div>`;
}
function args(d){
  const x=e(); const out={};
  if(x.id==='mean_bars')Object.assign(out,{data_cols:d.measurement?[d.measurement]:[],stats_test:d.stats_test,normalize:d.normalize,points:d.points});
  if(x.id==='regressions')Object.assign(out,{x:d.x,y:d.y,test:d.test,normalize_x:d.normalize_x,normalize_y:d.normalize_y,combine:d.combine});
  if(x.id==='histograms')Object.assign(out,{marker:d.marker,x_attr:d.x_attr,bins:d.bins,stat:d.stat,combine:d.combine,kde:d.kde});
  if(x.kind==='Pipeline')Object.assign(out,{data_cols:d.measurement?[d.measurement]:[],engine:d.engine,control:d.control||null,screen:d.screen,alpha:d.alpha,n_boot:d.n_boot,...Object.fromEntries(['plot_volcano','plot_forest','plot_stats_matrix','plot_bars','plot_superplots'].map(k=>[k,d[k]]))});
  return out;
}
function output(){
  const x=e(),d=draft(),result=state.results[x.id],shown=result?.inputs||d,dirty=Boolean(result)&&JSON.stringify(result.inputs)!==JSON.stringify(d),isRunning=running?.id===x.id;
  $('result-title').textContent=x.kind==='Pipeline'?'Pipeline outputs':(result?'Preview result':'Illustrative result');
  $('result-state').className=dirty?'dirty':'';
  $('result-state').textContent=isRunning?'Simulated run · editing remains available':dirty?'Inputs changed · showing the previous preview':result?'Preview created · not a scientific result':'Example layout · choose inputs on the left';
  $('restore').hidden=!dirty;
  if(reviewState==='missing'&&error()&&!result)$('result').innerHTML='<div class="empty-result"><strong>Choose the missing input</strong><span>The result will appear here.</span></div>';
  else $('result').innerHTML=x.kind==='Pipeline'?pipeline(shown,isRunning?running.progress:null):plot(x.picture,shown);
  $('accent').value=d.style.accent;$('point-size').value=d.style.pointSize;$('show-legend').checked=d.style.legend;
  $('details').innerHTML=`<dl><dt>Package action</dt><dd><code>${x.id}</code></dd><dt>Input scope</dt><dd>${shown.groups.length} example groups · ${x.id==='histograms'?'segmented objects':'subject summaries'}</dd><dt>Result status</dt><dd>Design illustration; no computed statistics</dd></dl><details><summary title="Inspect a proposed argument mapping, not an executed replay">Proposed package arguments</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${escapeHTML(JSON.stringify(args(shown),null,2))}</pre></details>`;
  $('global-status').textContent=running?`Simulated run: ${EXAMPLES.find(q=>q.id===running.id).title} · ${Math.round(running.progress)}%`:'No analysis is running';
}
function history(){
  $('history').innerHTML=state.history.length?state.history.slice(-6).reverse().map((item,i)=>`<button class="saved-item" data-history="${state.history.length-1-i}" title="Restore this preview's inputs and layout">${EXAMPLES.find(x=>x.id===item.id).title}<small>${item.inputs.groups.length} groups · design preview</small></button>`).join(''):'<span class="muted">Your preview runs appear here.</span>';
}
function render(){
  document.documentElement.dataset.theme=state.theme;$('theme').textContent=state.theme==='light'?'Dark theme':'Light theme';
  $('work-title').textContent=e().title;$('kind').textContent=e().kind;gallery();form();output();history();save();
}
function change(event){
  const input=event.target,d=draft();if(!input.name)return;
  if(input.name==='groups'){d.groups=[...$('inputs').querySelectorAll('[name=groups]:checked')].map(x=>x.value);$('inputs').querySelector('.groups summary').textContent=`Groups · ${d.groups.length} selected`;}
  else if(input.type==='checkbox')d[input.name]=input.checked;
  else if(input.type==='number')d[input.name]=Number(input.value);
  else d[input.name]=input.value==='true'?true:input.value==='false'?false:input.value;
  validity();output();save();
}
function startRun(manual=false){
  if(!manual&&error()||running)return;
  const snapshot=clone(draft()),id=e().id;running={id,inputs:snapshot,progress:0};reviewState='running';$('review-state').value='running';validity();output();
  timer=setInterval(()=>{running.progress=Math.min(100,running.progress+5);if(running.progress===100){state.results[id]={inputs:snapshot};state.history.push({id,inputs:snapshot});state.history=state.history.slice(-20);running=null;clearInterval(timer);timer=null;reviewState='ready';$('review-state').value='ready';validity();history();save();}output();},250);
}
$('gallery').addEventListener('click',event=>{const button=event.target.closest('[data-example]');if(button){state.selected=button.dataset.example;reviewState='ready';$('review-state').value='ready';$('appearance').hidden=true;$('appearance-button').setAttribute('aria-expanded','false');render();}});
$('search').addEventListener('input',gallery);$('clear-search').addEventListener('click',()=>{$('search').value='';gallery();$('search').focus();});
$('inputs').addEventListener('change',change);
$('inputs').addEventListener('submit',event=>{event.preventDefault();startRun();});
$('inputs').addEventListener('click',event=>{if(event.target.id==='reset-inputs'){state.drafts[e().id]=initialDraft(e());reviewState='ready';render();}});
$('appearance-button').addEventListener('click',()=>{const open=$('appearance').hidden;$('appearance').hidden=!open;$('appearance-button').setAttribute('aria-expanded',String(open));});
for(const id of ['accent','point-size','show-legend'])$(id).addEventListener('input',()=>{const style={accent:$('accent').value,pointSize:Number($('point-size').value),legend:$('show-legend').checked};draft().style=style;if(state.results[e().id])state.results[e().id].inputs.style=clone(style);output();save();});
$('theme').addEventListener('click',()=>{state.theme=state.theme==='light'?'dark':'light';document.documentElement.dataset.theme=state.theme;$('theme').textContent=state.theme==='light'?'Dark theme':'Light theme';save();});
$('restore').addEventListener('click',()=>{state.drafts[e().id]=clone(state.results[e().id].inputs);reviewState='ready';render();});
$('history').addEventListener('click',event=>{const button=event.target.closest('[data-history]');if(button){const item=state.history[Number(button.dataset.history)];state.selected=item.id;state.drafts[item.id]=clone(item.inputs);state.results[item.id]={inputs:clone(item.inputs)};reviewState='ready';$('review-state').value='ready';render();}});
$('review-state').addEventListener('change',()=>{if(timer){clearInterval(timer);timer=null;running=null;}reviewState=$('review-state').value;if(reviewState==='missing'){delete state.results[e().id];draft()[e().required[0]]='';}else if(reviewState==='editing'){state.results[e().id]={inputs:clone(draft())};draft().groups=draft().groups.slice(0,3);}else if(reviewState==='running'){if(error())state.drafts[e().id]=initialDraft(e());startRun(true);return;}else{if(error())state.drafts[e().id]=initialDraft(e());}render();});
$('reset').addEventListener('click',()=>{if(timer)clearInterval(timer);timer=null;running=null;state={selected:'mean_bars',drafts:Object.fromEntries(EXAMPLES.map(x=>[x.id,initialDraft(x)])),results:{},history:[],theme:state.theme};reviewState='ready';$('review-state').value='ready';$('search').value='';render();});
render();
requestAnimationFrame(()=>requestAnimationFrame(()=>{window.previewReady=performance.now();}));
