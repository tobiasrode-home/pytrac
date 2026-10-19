/* Arbeitsgang planen, Kartenlinien bearbeiten und speichern. */
"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const s = { fields: [], tractors: [], implements: [], map: null, layers: null };
  const msg = (text, error=false) => {
    $("plan-message").textContent = text;
    $("plan-message").classList.toggle("error", error);
  };
  async function loadOptions() {
    [s.fields, s.tractors, s.implements] = await Promise.all([
      request("/api/fields"), request("/api/tractors"), request("/api/implements")
    ]);
    for (const [id, rows] of [["plan-field",s.fields],["plan-tractor",s.tractors],["plan-implement",s.implements]]) {
      const select=$(id), previous=select.value;
      select.replaceChildren(new Option("Bitte auswählen",""));
      rows.forEach(r=>select.add(new Option(r.name,String(r.id))));
      if(rows.some(r=>String(r.id)===previous)) select.value=previous;
    }
  }
  const selected=(rows,id)=>rows.find(r=>String(r.id)===$(id).value);
  function initMap() {
    if(s.map) { setTimeout(()=>s.map.invalidateSize(),100); return; }
    s.map=L.map("work-plan-map").setView([51.3,9.5],14);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(s.map);
    s.layers=new L.FeatureGroup().addTo(s.map);
    s.map.addControl(new L.Control.Draw({draw:{polyline:{shapeOptions:{color:"#17643a",weight:4}},
      polygon:false,rectangle:false,circle:false,circlemarker:false,marker:false},
      edit:{featureGroup:s.layers,edit:true,remove:true}}));
  }
  const ll=coords=>coords.map(([lon,lat])=>[lat,lon]);
  function render(field, positions=[]) {
    initMap(); s.layers.clearLayers();
    if(field?.boundary?.length>=4) s.layers.addLayer(L.polygon(ll(field.boundary),
      {color:"#536471",fillOpacity:.06,weight:2}));
    positions.forEach(p=>{
      if(p.geometry?.type==="LineString") s.layers.addLayer(L.polyline(ll(p.geometry.coordinates),
        {color:p.kind==="turn"?"#d97706":"#17643a",weight:4}));
      else if(p.geometry?.type==="MultiLineString") p.geometry.coordinates.forEach(line=>
        s.layers.addLayer(L.polyline(ll(line),{color:"#17643a",weight:4})));
    });
    if(s.layers.getLayers().length) s.map.fitBounds(s.layers.getBounds(),{padding:[20,20]});
    setTimeout(()=>s.map.invalidateSize(),100);
  }
  // Parallele Linien aus Schnittpunkten der Feldgrenze; Winkel 0° verläuft Ost-West.
  function makeTracks(field, spacing, angle) {
    if(!field?.boundary || field.boundary.length<4) throw Error("Das Feld hat keine gültige Feldgrenze.");
    const ring=field.boundary.slice(0,-1), lon0=ring.reduce((a,p)=>a+p[0],0)/ring.length,
      lat0=ring.reduce((a,p)=>a+p[1],0)/ring.length, c=Math.cos(lat0*Math.PI/180);
    const xy=([lon,lat])=>({x:(lon-lon0)*111320*c,y:(lat-lat0)*110540});
    const llout=p=>[lon0+p.x/(111320*c),lat0+p.y/110540];
    const t=angle*Math.PI/180, pts=ring.map(xy).map(p=>({u:p.x*Math.cos(t)+p.y*Math.sin(t),v:-p.x*Math.sin(t)+p.y*Math.cos(t)}));
    const back=(u,v)=>({x:u*Math.cos(t)-v*Math.sin(t),y:u*Math.sin(t)+v*Math.cos(t)});
    const min=Math.min(...pts.map(p=>p.v)), max=Math.max(...pts.map(p=>p.v)), out=[];
    let no=0;
    for(let v=min+spacing/2;v<=max;v+=spacing){
      const xs=[];
      for(let i=0;i<pts.length;i++){
        const a=pts[i],b=pts[(i+1)%pts.length];
        if((a.v<=v&&b.v>v)||(b.v<=v&&a.v>v)){
          const f=(v-a.v)/(b.v-a.v); xs.push(a.u+f*(b.u-a.u));
        }
      }
      xs.sort((a,b)=>a-b);
      for(let i=0;i+1<xs.length;i+=2) out.push({position_no:no++,kind:"track",
        geometry:{type:"LineString",coordinates:[llout(back(xs[i],v)),llout(back(xs[i+1],v))]},
        properties:{generated:true,spacing_m:spacing,angle_deg:angle}});
    }
    return out;
  }
  function collect() {
    const out=[]; let no=0;
    s.layers.eachLayer(layer=>{
      if(layer instanceof L.Polygon || !(layer instanceof L.Polyline)) return;
      const pts=layer.getLatLngs();
      if(!pts.length || Array.isArray(pts[0]) || pts.length<2) return;
      out.push({position_no:no++,kind:"track",
        geometry:{type:"LineString",coordinates:pts.map(p=>[p.lng,p.lat])},
        properties:{manually_editable:true}});
    });
    return out;
  }
  async function plan() {
    const field=selected(s.fields,"plan-field"), tractor=selected(s.tractors,"plan-tractor"),
      implement=selected(s.implements,"plan-implement");
    if(!field||!tractor||!implement) throw Error("Bitte Feld, Traktor und Anbaugerät auswählen.");
    const spacing=Number($("plan-spacing").value), angle=Number($("plan-angle").value),
      headland=Number($("plan-headland").value), speed=Number($("plan-speed").value);
    if(!(spacing>0&&headland>0&&speed>0&&Number.isFinite(angle))) throw Error("Bitte Planungswerte prüfen.");
    await request("/api/work-planning/preview",{method:"POST",body:JSON.stringify({
      field_id:field.id,tractor_id:tractor.id,implement_id:implement.id,
      maneuver_mode:$("plan-maneuver").value,headland_depth_override_m:headland,target_speed_kmh:speed})});
    const positions=makeTracks(field,spacing,angle);
    render(field,positions);
    msg(`${positions.length} Fahrspuren erzeugt. Auf der Karte bearbeiten und anschließend speichern.`);
  }
  async function loadSaved() {
    const f=selected(s.fields,"plan-field"),t=selected(s.tractors,"plan-tractor"),i=selected(s.implements,"plan-implement");
    if(!f||!t||!i) throw Error("Bitte Feld, Traktor und Anbaugerät auswählen.");
    const p=await request(`/api/work-plans/${f.id}/${t.id}/${i.id}`);
    $("plan-name").value=p.name; $("plan-maneuver").value=p.maneuver_mode;
    $("plan-headland").value=p.headland_depth_m; $("plan-speed").value=p.target_speed_kmh;
    render(f,p.positions); msg(`Plan „${p.name}“ geladen.`);
  }
  async function save() {
    const f=selected(s.fields,"plan-field"),t=selected(s.tractors,"plan-tractor"),i=selected(s.implements,"plan-implement");
    if(!f||!t||!i) throw Error("Bitte Feld, Traktor und Anbaugerät auswählen.");
    const positions=collect(); if(!positions.length) throw Error("Keine Fahrspuren zum Speichern vorhanden.");
    const p=await request("/api/work-plans",{method:"PUT",body:JSON.stringify({
      field_id:f.id,tractor_id:t.id,implement_id:i.id,name:$("plan-name").value.trim()||"Arbeitsgang",
      maneuver_mode:$("plan-maneuver").value,headland_depth_m:Number($("plan-headland").value),
      target_speed_kmh:Number($("plan-speed").value),positions})});
    msg(`Plan gespeichert: ${p.positions.length} Positionen.`);
  }
  const safe=fn=>async()=>{try{await fn();}catch(e){msg(e.message,true);}};
  document.addEventListener("DOMContentLoaded",async()=>{
    if(!$("work-plan-map")) return;
    $("plan-generate").addEventListener("click",safe(plan));
    $("plan-load").addEventListener("click",safe(loadSaved));
    $("plan-save").addEventListener("click",safe(save));
    $("plan-refresh").addEventListener("click",safe(loadOptions));
    $("plan-field").addEventListener("change",()=>{const f=selected(s.fields,"plan-field");if(f)render(f);});
    try{await loadOptions();}catch(e){msg(e.message,true);}
  });
})();
