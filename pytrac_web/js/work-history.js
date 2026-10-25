"use strict";
const WH=(()=>{
  let map=null, layers=null;
  const $=id=>document.getElementById(id);
  async function api(url,options={}){
    const response=await fetch(url,options);
    if(!response.ok)throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    return response.status===204?null:response.json();
  }
  function lineCoords(points){
    return points.map(p=>[Number(p[1]),Number(p[0])]).filter(p=>p.every(Number.isFinite));
  }
  function addLine(coords,options){
    if(coords.length>=2)L.polyline(coords,options).addTo(layers);
  }
  function init(){
    if(map)return;
    map=L.map("wh-map");
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {attribution:"© OpenStreetMap"}).addTo(map);
    layers=L.featureGroup().addTo(map);
    $("wh-refresh").addEventListener("click",load);
    $("wh-plan").addEventListener("change",load);
    $("wh-delete-progress").addEventListener("click",deleteProgress);
    $("wh-delete-progress").disabled=true;
  }
  async function show(){
    init();
    try{
      const plans=await api("/api/work-plannings");
      const old=$("wh-plan").value;
      $("wh-plan").replaceChildren(new Option("Arbeitsauftrag auswählen",""));
      for(const plan of plans)$("wh-plan").add(new Option(`${plan.name} (#${plan.id})`,plan.id));
      if(plans.some(p=>String(p.id)===old))$("wh-plan").value=old;
      $("wh-delete-progress").disabled=!$("wh-plan").value;
      setTimeout(()=>map.invalidateSize(),80);
      if($("wh-plan").value)await load();
      else layers.clearLayers();
    }catch(e){$("wh-status").textContent=e.message;}
  }
  async function load(){
    const id=$("wh-plan").value;
    $("wh-delete-progress").disabled=!id;
    if(!id){layers.clearLayers();$("wh-status").textContent="Arbeitsauftrag auswählen";return;}
    $("wh-status").textContent="Lade Planung und GPS-Fahrten …";
    try{
      const [plan,guidance,progress,implementsList]=await Promise.all([
        api(`/api/work-plannings/${id}`),
        api(`/api/work-plannings/${id}/guidance`,{method:"POST",
          headers:{"Content-Type":"application/json"},body:JSON.stringify({output_mode:"targets"})}),
        api(`/api/work-plannings/${id}/progress`),api("/api/implements")]);
      if($("wh-plan").value!==id)return;
      layers.clearLayers();
      for(const track of [...(guidance.tracks||[]),...(guidance.headland_tracks||[])])
        addLine(lineCoords(track.coordinates||[]),{color:"#2478e4",weight:2,opacity:.8});
      const implement=implementsList.find(i=>Number(i.id)===Number(plan.implement_id));
      const width=Number(implement?.working_width_m||0);
      let segment=[],key=null,previous=null;
      const flush=()=>{
        if(segment.length>=2){
          if(width>0){
            const lat=segment[0][0],lng=segment[0][1];
            const pxPerMeter=Math.abs(map.latLngToLayerPoint([lat+0.00001,lng]).y-
                                         map.latLngToLayerPoint([lat,lng]).y)/1.1132;
            addLine(segment,{color:"#29964a",weight:Math.max(1,width*pxPerMeter),opacity:.3});
          }
          addLine(segment,{color:"#e69c16",weight:3,opacity:1});
        }
        segment=[];
      };
      for(const p of progress.points){
        const nextKey=`${p.phase}/${p.track_id}`;
        const time=Date.parse(p.recorded_at);
        const gap=previous!==null && Number.isFinite(time) && time-previous>30000;
        if(key!==null && (nextKey!==key || gap))flush();
        key=nextKey;previous=time;
        segment.push([p.latitude,p.longitude]);
      }
      flush();
      if(layers.getLayers().length)map.fitBounds(layers.getBounds().pad(.15));
      $("wh-status").textContent=`${plan.name}: ${progress.count} GPS-Punkte · Blau geplant, Orange gefahren. Grün ist nur eine schematische Breitenanzeige, keine vermessene Fläche.`;
      setTimeout(()=>map.invalidateSize(),80);
    }catch(e){$("wh-status").textContent="Laden fehlgeschlagen: "+e.message;}
  }
  async function deleteProgress(){
    const id=$("wh-plan").value;
    if(!id)return;
    const name=$("wh-plan").selectedOptions[0]?.textContent||`#${id}`;
    if(!confirm(`Alle aufgezeichneten GPS-Fahrdaten für "${name}" dauerhaft löschen?\n\nDer Arbeitsauftrag und die geplanten Spuren bleiben erhalten.`))return;
    const button=$("wh-delete-progress");
    button.disabled=true;
    try{
      await api(`/api/work-plannings/${id}/progress`,{method:"DELETE"});
      await load();
      $("wh-status").textContent=`GPS-Fahrhistorie für ${name} gelöscht. Der Arbeitsauftrag und die geplanten Spuren bleiben erhalten.`;
    }catch(e){$("wh-status").textContent="Löschen fehlgeschlagen: "+e.message;}
    finally{button.disabled=!$("wh-plan").value;}
  }
  return {show};
})();
