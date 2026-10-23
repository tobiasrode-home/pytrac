"use strict";
/* Nur Darstellung und API-Kommunikation; fachliche Berechnungen im Python-Service. */
const WP = (() => {
  const el = id => document.getElementById(id);
  const state = {loadingSaved:false,field:null, edges:[], selected:{alignment:null,start:[]}, mode:'alignment', map:null, layers:null, marker:null, defaults:null, override:false, guidanceLayers:null};
  async function api(url, options={}) {
    const response = await fetch(url,{...options, headers:{'Content-Type':'application/json',...options.headers}});
    if(!response.ok) {
      let detail; try { detail=(await response.json()).detail; } catch { detail=response.statusText; }
      throw new Error(typeof detail==='string'?detail:JSON.stringify(detail));
    }
    return response.status===204?null:response.json();
  }
  function status(message, error=false) { el('wp-status').textContent=message; el('wp-status').classList.toggle('error',error); }
  function selected(name) { return el('wp-'+name).value; }
  function optionList(id, records) {
    const select=el(id), old=select.value;
    select.replaceChildren(new Option('Bitte auswählen',''));
    for(const record of records) select.add(new Option(record.name,record.id));
    if([...select.options].some(option=>option.value===old)) select.value=old;
  }
  async function load() {
    try {
      const [tractors,implementsList,fields,plans]=await Promise.all([
        api('/api/tractors'),api('/api/implements'),api('/api/fields'),api('/api/work-plannings')]);
      optionList('wp-tractor',tractors); optionList('wp-implement',implementsList); optionList('wp-field',fields);
      const list=el('wp-list'); list.replaceChildren();
      for(const plan of plans) {
        const line=document.createElement('div'); line.className='wp-plan-row';
        const name=document.createElement('span'); name.textContent=`${plan.name} · ${new Date(plan.created_at).toLocaleString('de-DE')} · ID ${plan.id}`;
        const del=document.createElement('button'); del.textContent='Löschen'; del.className='danger';
        del.addEventListener('click',async()=>{if(!confirm('Arbeitsplanung löschen?'))return;try{await api('/api/work-plannings/'+plan.id,{method:'DELETE'});await load();}catch(e){status(e.message,true);}});
        const open=document.createElement('button'); open.type='button'; open.textContent='Laden';
        open.addEventListener('click',async()=>{try{await loadSaved(plan.id);}catch(e){status(e.message,true);}});
        line.append(name,open,del);list.append(line);
      }
      await updateDefaults();
    } catch(e) {status(e.message,true);}
  }
  async function loadSaved(id) {
    // Datensatz frisch laden: nicht auf möglicherweise veraltete Listeneinträge vertrauen.
    const plan=await api('/api/work-plannings/'+encodeURIComponent(id));
    state.loadingSaved=true;
    try {
      // Stammdaten werden durch load() bereits bereitgestellt. Falls die Planung
      // auf inzwischen gelöschte Stammdaten verweist, verständlich abbrechen.
      for(const [field,value] of [['tractor',plan.tractor_id],['implement',plan.implement_id],['field',plan.field_id]]) {
        const control=el('wp-'+field);
        if(![...control.options].some(option=>option.value===String(value))) {
          throw new Error(`Die gespeicherte Planung verweist auf einen nicht mehr vorhandenen Datensatz (${field}: ${value}).`);
        }
      }
      el('wp-name').value=plan.name;
      el('wp-tractor').value=String(plan.tractor_id);
      el('wp-implement').value=String(plan.implement_id);
      el('wp-field').value=String(plan.field_id);
      el('wp-speed').value=plan.speed??'';
      el('wp-turn').value=plan.turn_type;
      el('wp-headland').value=plan.headland_mode;
      el('wp-bed').checked=Boolean(plan.bed_working);
      el('wp-bed').disabled=plan.turn_type!=='u_turn';
      el('wp-widths').value=plan.headland_working_widths;
      el('wp-end-a').value=plan.headland_start_passes??'';
      el('wp-end-b').value=plan.headland_end_passes??'';
      state.override=true;
      await loadField();
      const ids=[plan.alignment_boundary_id,plan.start_boundary_a_id,plan.start_boundary_b_id];
      if(ids.some(edge=>!state.edges.some(item=>item.id===edge))) {
        throw new Error('Die Feldgrenzen wurden seit dem Speichern verändert. Bitte Ausrichtung und Startgrenzen neu auswählen.');
      }
      state.selected={alignment:ids[0],start:[ids[1],ids[2]]};
      updateSelection();
      // Modus und Vorlauf sind bewusst keine gespeicherten Einstellungen.
      // Vorhandene Anzeigeeinstellungen werden daher beibehalten.
      await updateDefaults();
      const previewResult=await preview();
      await guidance(plan.id);
      status(`Arbeitsplanung „${plan.name}“ (ID ${plan.id}) geladen. Die Planung kann erneut berechnet oder als neue Arbeit gespeichert werden.`);
      el('wp-form').scrollIntoView({behavior:'smooth',block:'start'});
      return previewResult;
    } finally {
      state.loadingSaved=false;
    }
  }

  async function updateDefaults() {
    const tractor=selected('tractor'), implement=selected('implement');
    if(!tractor||!implement) {el('wp-default').textContent='–';return;}
    try {
      const defaults=await api('/api/work-plannings/defaults',{method:'POST',body:JSON.stringify({tractor_id:+tractor,implement_id:+implement})});
      state.defaults=defaults;el('wp-default').textContent=defaults.default_headland_working_widths;
      if(!state.override) el('wp-widths').value=defaults.default_headland_working_widths;
    } catch(e) {status(e.message,true);}
  }
  function resetMap() {
    state.field=null;state.edges=[];state.selected={alignment:null,start:[]};
    if(state.layers)state.layers.clearLayers();if(state.guidanceLayers)state.guidanceLayers.clearLayers();if(state.marker){state.map.removeLayer(state.marker);state.marker=null;}
    updateSelection();
  }
  async function loadField() {
    resetMap();if(!selected('field'))return;
    try {
      state.field=await api('/api/fields/'+selected('field'));
      const coordinates=state.field.boundary;
      if(!Array.isArray(coordinates)||coordinates.length<4)throw new Error('Ungültige Feldgeometrie.');
      if(!state.map) {
        state.map=L.map('wp-map').setView([51.3,9.5],13);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(state.map);
        state.layers=L.layerGroup().addTo(state.map);state.guidanceLayers=L.layerGroup().addTo(state.map);
      }
      const vertices=coordinates.slice(0,-1);
      L.polygon(vertices.map(([lon,lat])=>[lat,lon]),{color:'#5b8d5a',weight:2,fillOpacity:0.12,interactive:false}).addTo(state.layers);
      vertices.forEach((point,index)=>{
        const next=vertices[(index+1)%vertices.length];
        const edge=L.polyline([[point[1],point[0]],[next[1],next[0]]],{color:'#17643a',weight:8,opacity:0.75}).addTo(state.layers);
        const id='edge-'+index;
        edge.bindTooltip('Grenze '+(index+1));edge.on('click',()=>chooseEdge(id));
        state.edges.push({id,edge});
      });
      state.map.fitBounds(L.latLngBounds(vertices.map(([lon,lat])=>[lat,lon])),{padding:[25,25]});
      setTimeout(()=>state.map.invalidateSize(),50);
    } catch(e) {status(e.message,true);}
  }
  function chooseEdge(id) {
    if(state.mode==='alignment')state.selected.alignment=id;
    else {
      const start=state.selected.start;
      if(start.includes(id))state.selected.start=start.filter(x=>x!==id);
      else state.selected.start=[...start.slice(-1),id];
    }
    updateSelection();
  }
  function updateSelection() {
    for(const {id,edge} of state.edges) {
      const color=id===state.selected.alignment?'#226cda':state.selected.start.includes(id)?'#e07820':'#17643a';
      edge.setStyle({color});
    }
    el('wp-alignment-label').textContent=state.selected.alignment||'nicht ausgewählt';
    el('wp-start-label').textContent=state.selected.start.join(' + ')||'nicht ausgewählt';
    if(state.marker){state.map.removeLayer(state.marker);state.marker=null;}
    el('wp-start-point').textContent='Noch nicht berechnet';
  }
  function payload() {
    if(!state.selected.alignment||state.selected.start.length!==2)throw new Error('Ausrichtungskante und zwei Startgrenzen auf der Karte auswählen.');
    const speed=selected('speed').trim();const widths=selected('widths').trim();
    return {name:selected('name').trim(),tractor_id:+selected('tractor'),implement_id:+selected('implement'),field_id:+selected('field'),
      speed:speed===''?null:Number(speed),turn_type:selected('turn'),headland_mode:selected('headland'),bed_working:el('wp-bed').checked,
      alignment_boundary_id:state.selected.alignment,start_boundary_a_id:state.selected.start[0],start_boundary_b_id:state.selected.start[1],
      headland_working_widths:widths===''?null:Number(widths),
      headland_start_passes:selected('end-a').trim()===''?null:Number(selected('end-a')),
      headland_end_passes:selected('end-b').trim()===''?null:Number(selected('end-b'))};
  }
  async function preview() {
    const result=await api('/api/work-plannings/preview',{method:'POST',body:JSON.stringify(payload())});
    el('wp-default').textContent=result.default_headland_working_widths;
    const [lon,lat]=result.start_point;
    el('wp-start-point').textContent=`${lat.toFixed(7)}, ${lon.toFixed(7)}`;
    if(state.marker)state.map.removeLayer(state.marker);
    state.marker=L.marker([lat,lon]).addTo(state.map).bindPopup('Startpunkt der regulären Fahrspuren').openPopup();
    return result;
  }
  async function guidance(savedId=null) {
    if(!state.map)throw new Error('Bitte zuerst ein Feld auf der Karte auswählen.');
    const mode=selected('guidance-mode');
    const lead=Number(selected('implement-lead'));
    if(!Number.isFinite(lead)||lead<0||lead>100)throw new Error('Vorlauf muss zwischen 0 und 100 m liegen.');
    const url=savedId?`/api/work-plannings/${savedId}/guidance`:'/api/work-plannings/guidance';
    const body=savedId?{output_mode:mode,implement_lead_m:lead}:{...payload(),output_mode:mode,implement_lead_m:lead};
    const result=await api(url,{method:'POST',body:JSON.stringify(body)});
    if(!state.guidanceLayers)state.guidanceLayers=L.layerGroup().addTo(state.map);
    state.guidanceLayers.clearLayers();
    for(const track of result.tracks) {
      const line=L.polyline(track.coordinates.map(([lon,lat])=>[lat,lon]),{color:'#1466d4',weight:3}).addTo(state.guidanceLayers);
      line.bindTooltip(`Spur ${track.id} · ${track.length_m} m`);
    }
    for(const track of result.headland_tracks||[]) {
      L.polyline(track.coordinates.map(([lon,lat])=>[lat,lon]),
        {color:'#16865b',weight:4,opacity:.8}).addTo(state.guidanceLayers)
        .bindTooltip(`Vorgewende · Feldseite ${track.side_id+1} · Bahn ${track.pass_index} · ${track.length_m} m`);
    }
    for(const transition of result.transitions) {
      const [lon,lat]=transition.target;
      L.circleMarker([lat,lon],{radius:4,color:'#e07820',fillOpacity:0.9}).addTo(state.guidanceLayers)
        .bindTooltip(`Ziel: Spur ${transition.to_track}`);
      for(const segment of transition.segments) {
        L.polyline(segment.coordinates.map(([x,y])=>[y,x]),{
          color:segment.gear==='reverse'?'#b42318':'#e07820',weight:3,
          dashArray:segment.gear==='reverse'?'6,6':null
        }).addTo(state.guidanceLayers);
      }
    }
    const events=el('wp-implement-events');events.replaceChildren();
    const heading=document.createElement('h3');heading.textContent='Arbeitsgerät – geplante Anweisungen';events.append(heading);
    const explanation=document.createElement('p');explanation.className='muted';
    explanation.textContent='Rot/Grün markieren den Fahrzeug-Stopppunkt; der tatsächliche Arbeitsgrenzpunkt wird separat angezeigt. Anhalten und Gerätebedienung bestätigen ist erforderlich. Keine GPS-Live-Auslösung.';
    events.append(explanation);
    for(const event of [...(result.implement_events||[]),...(result.headland_implement_events||[])]) {
      const [lon,lat]=event.coordinate;
      const lower=event.action==='lower';
      L.circleMarker([lat,lon],{radius:6,color:lower?'#17643a':'#b42318',fillOpacity:0.9})
        .addTo(state.guidanceLayers).bindTooltip(`${event.phase==='headland'?'Vorgewende Seite '+(event.side_id+1):'Hauptfeld'} Spur ${event.track_id}: ${event.label}`);
      if(event.advance_warning) {
        const [wx,wy]=event.advance_warning;
        L.circleMarker([wy,wx],{radius:4,color:'#e07820',dashArray:'3,3',fillOpacity:0.6})
          .addTo(state.guidanceLayers).bindTooltip(`Vorlauf ${event.lead_m} m: ${event.label}`);
      }
      const row=document.createElement('p');
      const [workLon,workLat]=event.work_boundary;
      L.circleMarker([workLat,workLon],{radius:3,color:'#555',fillOpacity:0.7})
        .addTo(state.guidanceLayers).bindTooltip('Arbeitsgrenze des Anbaugeräts');
      row.textContent=`${event.phase==='headland'?'Vorgewende Seite '+(event.side_id+1):'Hauptfeld'} · Spur ${event.track_id} · STOPP & bestätigen: ${event.label} · Fahrzeug: ${lat.toFixed(7)}, ${lon.toFixed(7)} · Arbeitsgrenze: ${workLat.toFixed(7)}, ${workLon.toFixed(7)}`;
      events.append(row);
    }
    el('wp-guidance-summary').textContent=`${result.track_count} Fahrspuren · ${result.work_length_m} m Arbeitsweg · `+
      `${result.headland_track_count||0} gerade Vorgewendespuren (grün) · ${result.transitions.length} Hauptfeld-Übergänge. ${result.warnings.join(' ')}`;
    status('Spurplanung vom Python-Backend berechnet.');
    return result;
  }
  async function save() {
    await preview();
    const result=await api('/api/work-plannings',{method:'POST',body:JSON.stringify(payload())});
    status(`Arbeitsplanung ${result.id} gespeichert: ${new Date(result.created_at).toLocaleString('de-DE')}`);
    await load();
  }
  function init() {
    if(!el('wp-form'))return;
    el('wp-tractor').addEventListener('change',()=>{state.override=false;updateDefaults();});
    el('wp-implement').addEventListener('change',()=>{state.override=false;updateDefaults();});
    el('wp-field').addEventListener('change',loadField);
    el('wp-widths').addEventListener('input',()=>{state.override=el('wp-widths').value.trim()!=='';});
    el('wp-reset-widths').addEventListener('click',()=>{state.override=false;updateDefaults();});
    el('wp-turn').addEventListener('change',()=>{const u=selected('turn')==='u_turn';el('wp-bed').disabled=!u;if(!u)el('wp-bed').checked=false;});
    for(const button of document.querySelectorAll('[data-wp-mode]'))button.addEventListener('click',()=>{
      state.mode=button.dataset.wpMode;
      document.querySelectorAll('[data-wp-mode]').forEach(b=>b.classList.toggle('active',b===button));
      status(state.mode==='alignment'?'Ausrichtungskante anklicken.':'Zwei angrenzende Startgrenzen anklicken.');
    });
    el('wp-guidance').addEventListener('click',async()=>{try{await guidance();}catch(e){status(e.message,true);}});
    el('wp-preview').addEventListener('click',async()=>{try{await preview();status('Startpunkt vom Backend berechnet.');}catch(e){status(e.message,true);}});
    el('wp-form').addEventListener('submit',async event=>{event.preventDefault();try{await save();}catch(e){status(e.message,true);}});
  }
  return {init,load,show(){load();setTimeout(()=>{if(state.map)state.map.invalidateSize();},100);}};
})();
document.addEventListener('DOMContentLoaded',WP.init);
