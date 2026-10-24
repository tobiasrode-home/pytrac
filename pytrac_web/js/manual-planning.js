"use strict";
/* PyTrac V41: Manuelle Arbeitsplanung mit echten GPS-Koordinaten. */
const MP=(()=>{
 const $=id=>document.getElementById(id);
 const st={map:null,field:null,implements:[],tracks:[],selected:-1,mode:'select',drawing:[],history:[],id:null,dirty:false,layers:null,markers:null,bands:null,arrows:null};
 async function api(url,opt={}){const r=await fetch(url,{...opt,headers:{'Content-Type':'application/json',...opt.headers}});if(!r.ok){let d;try{d=await r.json()}catch{}throw Error(typeof d?.detail==='string'?d.detail:JSON.stringify(d?.detail||r.statusText))}return r.status===204?null:r.json()}
 const msg=(text,error=false)=>{const n=$('mp-status');n.textContent=text;n.style.color=error?'#b42318':''};
 function choices(id,items){let old=$(id).value;$(id).replaceChildren(new Option('Bitte auswählen',''));items.forEach(x=>$(id).add(new Option(x.name,x.id)));if([...$(id).options].some(x=>x.value===old))$(id).value=old}
 async function load(){try{const [fields,tractors,implements_,plans]=await Promise.all(['/api/fields','/api/tractors','/api/implements','/api/work-plannings'].map(x=>api(x)));st.implements=implements_;choices('mp-field',fields);choices('mp-tractor',tractors);choices('mp-implement',implements_);const list=$('mp-saved');list.replaceChildren();plans.forEach(plan=>{const row=document.createElement('div');row.className='mp-saved-row';const name=document.createElement('span');name.textContent=plan.name+' · '+new Date(plan.created_at).toLocaleString('de-DE');const open=document.createElement('button');open.textContent='Laden';open.onclick=()=>openPlan(plan).catch(e=>msg(e.message,true));row.append(name,open);list.append(row)});if(!st.field&&$('mp-field').value)await loadField();msg('Daten geladen. Feld wählen und Spuren zeichnen.')}catch(e){msg(e.message,true)}}
 function show(){if(!st.map)initMap();load().then(()=>setTimeout(()=>st.map.invalidateSize(),100));}
 function initMap(){st.map=L.map('mp-map',{preferCanvas:true}).setView([51.0,9.6],15);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'© OpenStreetMap contributors'}).addTo(st.map);st.bands=L.layerGroup().addTo(st.map);st.layers=L.layerGroup().addTo(st.map);st.markers=L.layerGroup().addTo(st.map);st.arrows=L.layerGroup().addTo(st.map);st.map.on('zoomend',renderArrows);st.map.on('click',e=>{if(st.mode!=='draw')return;st.drawing.push([e.latlng.lng,e.latlng.lat]);render()})}
 const latlng=p=>[p[1],p[0]];
 const width=()=>{const imp=st.implements.find(x=>String(x.id)===$('mp-implement').value);return Number(imp?.working_width_m)||10};
 function project(p){const c=st.field?.boundary?.[0]||[9,51],lat=c[1]*Math.PI/180;return [(p[0]-c[0])*111319.490793*Math.cos(lat),(p[1]-c[1])*111132.92]}
 function unproject(p){const c=st.field.boundary[0],lat=c[1]*Math.PI/180;return [c[0]+p[0]/(111319.490793*Math.cos(lat)),c[1]+p[1]/111132.92]}
 function offset(track,m){const a=track.map(project),norm=[];for(let i=0;i<a.length-1;i++){const dx=a[i+1][0]-a[i][0],dy=a[i+1][1]-a[i][1],l=Math.hypot(dx,dy);if(l<.001)throw Error('Doppelte Stützpunkte entfernen.');norm.push([-dy/l,dx/l])}return a.map((p,i)=>{let n=i===0?norm[0]:i===a.length-1?norm[norm.length-1]:[norm[i-1][0]+norm[i][0],norm[i-1][1]+norm[i][1]];let l=Math.hypot(...n);if(l<.05)throw Error('Zu scharfer Knick für einen sicheren Parallelversatz.');return unproject([p[0]+m*n[0]/l,p[1]+m*n[1]/l])})}
 // Geodätische Längen in Metern (WGS84, Haversine für kurze Feldstrecken).
 function meters(a,b){const rad=Math.PI/180,la=a[1]*rad,lb=b[1]*rad,dlat=(b[1]-a[1])*rad,dlon=(b[0]-a[0])*rad;const h=Math.sin(dlat/2)**2+Math.cos(la)*Math.cos(lb)*Math.sin(dlon/2)**2;return 6371008.8*2*Math.asin(Math.min(1,Math.sqrt(h)))}
 function trackLength(track){return track.slice(1).reduce((sum,p,i)=>sum+meters(track[i],p),0)}
 function setLength(track,target){
   if(track.length<2||!Number.isFinite(target)||target<1)throw Error('Bitte eine gültige Spurlänge ab 1 m eingeben.');
   const fixed=trackLength(track.slice(0,-1));const remain=target-fixed;
   if(remain<=0.01)throw Error(`Die festen Abschnitte sind bereits ${fixed.toFixed(2)} m lang. Bitte Zwischenpunkte entfernen oder eine größere Länge wählen.`);
   const a=project(track[track.length-2]),b=project(track[track.length-1]);const dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy);
   if(len<0.001)throw Error('Der letzte Abschnitt hat keine Richtung. Endpunkt zuerst verschieben.');
   // Projektion für die Richtung; Länge per geodätischer Distanz iterativ justieren.
   let d=remain;for(let i=0;i<5;i++){const p=unproject([a[0]+dx/len*d,a[1]+dy/len*d]);const actual=meters(track[track.length-2],p);if(actual>0)d*=remain/actual}
   return [...track.slice(0,-1),unproject([a[0]+dx/len*d,a[1]+dy/len*d])];
 }

 // Entfernt eine gewünschte Länge entlang der gesamten Polylinie, nicht nur
 // entlang des ersten bzw. letzten Teilstücks.
 function trimTrack(track,amount,fromStart){
   if(!Number.isFinite(amount)||amount<0)throw Error('Bitte eine Kürzung ab 0 m eingeben.');
   if(amount===0)return track.map(p=>[...p]);
   const total=trackLength(track);
   if(amount>=total-0.05)throw Error(`Die Kürzung muss kleiner als die Spurlänge (${total.toFixed(2)} m) sein.`);
   const seq=(fromStart?track:[...track].reverse()).map(p=>[...p]);
   let remaining=amount;
   while(seq.length>1){
     const d=meters(seq[0],seq[1]);
     if(d<0.001){seq.shift();continue;}
     if(remaining>=d-0.001){remaining-=d;seq.shift();continue;}
     if(remaining>0){
       const a=project(seq[0]),b=project(seq[1]),ratio=remaining/d;
       // Meterbasierte Projektion mit kleiner geodätischer Nachkorrektur.
       let t=ratio;
       for(let k=0;k<5;k++){
         const q=unproject([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]);
         const actual=meters(seq[0],q);
         if(actual>0)t*=remaining/actual;
       }
       seq[0]=unproject([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]);
     }
     break;
   }
   if(seq.length<2)throw Error('Die Spur wäre nach dem Kürzen zu kurz.');
   return fromStart?seq:seq.reverse();
 }
 function cross2(a,b){return a[0]*b[1]-a[1]*b[0]}
 function boundaryIntersections(origin,direction){
   const ring=st.field.boundary.map(project);
   const hits=[];
   const n=ring.length>2&&Math.hypot(ring[0][0]-ring[ring.length-1][0],ring[0][1]-ring[ring.length-1][1])<.01?ring.length-1:ring.length;
   for(let i=0;i<n;i++){
     const a=ring[i],b=ring[(i+1)%n],edge=[b[0]-a[0],b[1]-a[1]];
     const den=cross2(direction,edge);
     if(Math.abs(den)<1e-10)continue;
     const delta=[a[0]-origin[0],a[1]-origin[1]];
     const t=cross2(delta,edge)/den;
     const u=cross2(delta,direction)/den;
     if(u>=-1e-8&&u<=1+1e-8)hits.push({t,edge:i});
   }
   return hits;
 }
 function snapEndToBoundary(track,atStart,inset){
   if(!st.field)throw Error('Zuerst ein Feld auswählen.');
   if(!Number.isFinite(inset)||inset<0)throw Error('Abstand muss mindestens 0 m sein.');
   const idx=atStart?0:track.length-1,neighbor=atStart?1:track.length-2;
   const p=project(track[idx]),q=project(track[neighbor]);
   const dx=p[0]-q[0],dy=p[1]-q[1],length=Math.hypot(dx,dy);
   if(length<.001)throw Error('Der Endabschnitt benötigt zwei unterschiedliche Punkte.');
   const outward=[dx/length,dy/length];
   const hits=boundaryIntersections(p,outward).filter(h=>h.t>=-0.05).sort((a,b)=>a.t-b.t);
   if(!hits.length)throw Error('In Verlängerung dieses Spurendes wurde keine Feldgrenze gefunden. Bitte Endrichtung anpassen.');
   // Ziel ist der erste Schnittpunkt mit der Feldgrenze, abzüglich des
   // gewünschten Abstands ins Feld hinein.
   const target=hits[0].t-inset;
   const candidate=unproject([p[0]+outward[0]*target,p[1]+outward[1]*target]);
   const updated=track.map(x=>[...x]);updated[idx]=candidate;
   if(meters(updated[idx],updated[neighbor])<.05)throw Error('Abstand zu groß: Der letzte Spurabschnitt würde verschwinden oder umkehren.');
   const before=[p[0]-q[0],p[1]-q[1]];
   const after=[project(candidate)[0]-q[0],project(candidate)[1]-q[1]];
   if(before[0]*after[0]+before[1]*after[1]<=0)throw Error('Abstand zu groß: Spur würde über den nächsten Stützpunkt hinauslaufen. Bitte zuerst kürzen oder Punkte anpassen.');
   return {track:updated,edge:hits[0].edge};
 }
 function showBoundaryLengths(){
   if(st.edgeLabels){st.edgeLabels.clearLayers()}else{st.edgeLabels=L.layerGroup().addTo(st.map)}
   if(!st.field)return;
   const ring=st.field.boundary;const n=ring.length>2&&meters(ring[0],ring[ring.length-1])<0.05?ring.length-1:ring.length;
   for(let i=0;i<n;i++){
     const a=ring[i],b=ring[(i+1)%n],middle=[(a[1]+b[1])/2,(a[0]+b[0])/2];
     L.marker(middle,{interactive:false,icon:L.divIcon({className:'mp-edge-label',html:`<span>${meters(a,b).toLocaleString('de-DE',{minimumFractionDigits:1,maximumFractionDigits:1})} m</span>`,iconSize:[88,24],iconAnchor:[44,12]})}).addTo(st.edgeLabels);
   }
 }

 function referenceItems(){
   if(!st.field)return [];
   const ring=st.field.boundary;
   const n=ring.length>2&&meters(ring[0],ring[ring.length-1])<.05?ring.length-1:ring.length;
   const items=[];
   for(let i=0;i<n;i++)items.push({key:`edge:${i}`,label:`Feldgrenze ${i+1} (${meters(ring[i],ring[(i+1)%n]).toFixed(1)} m)`,points:[ring[i],ring[(i+1)%n]]});
   st.tracks.forEach((track,i)=>items.push({key:`track:${i}`,label:`Spur ${i+1} (${trackLength(track).toFixed(1)} m)`,points:track}));
   return items;
 }
 function refreshReferences(){
   const items=referenceItems();
   for(const id of ['mp-end-reference','mp-ref-back','mp-ref-side','mp-ref-front']){
     const el=$(id);if(!el)continue;const old=el.value;
     el.replaceChildren(new Option('Bezugslinie auswählen',''));
     items.forEach(item=>el.add(new Option(item.label,item.key)));
     if(items.some(x=>x.key===old))el.value=old;
   }
 }
 function selectedReference(id){const item=referenceItems().find(x=>x.key===$(id).value);if(!item)throw Error('Bitte bei '+id+' eine Feldgrenze oder Spur auswählen.');return item}
 function inputMeter(id,signed=false){const raw=$(id).value.trim().replace(',','.');const val=Number(raw);if(!raw||!Number.isFinite(val)||(!signed&&val<0))throw Error('Ungültiger Meterwert bei '+id);return val}
 function lineHits(a,d,reference){
   const pts=reference.map(project),hits=[];
   for(let i=0;i<pts.length-1;i++){
     const p=pts[i],q=pts[i+1],v=[q[0]-p[0],q[1]-p[1]];
     const den=cross2(d,v);if(Math.abs(den)<1e-9)continue;
     const delta=[p[0]-a[0],p[1]-a[1]];
     const t=cross2(delta,v)/den,u=cross2(delta,d)/den;
     if(u>=-1e-7&&u<=1+1e-7)hits.push({t,point:[a[0]+t*d[0],a[1]+t*d[1]]});
   }
   return hits;
 }
 function intersectEndpoint(track,ref,inset,atStart){
   const seq=(atStart?track:[...track].reverse()).map(project);
   // Vom Ende nach außen verlängern und den nächsten gültigen Schnitt wählen.
   const a=seq[0],b=seq[1],v=[a[0]-b[0],a[1]-b[1]],len=Math.hypot(...v);
   if(len<.001)throw Error('Endabschnitt hat keine Richtung.');
   const d=[v[0]/len,v[1]/len];
   const hits=lineHits(a,d,ref.points).filter(h=>h.t>=-0.05).sort((x,y)=>x.t-y.t);
   if(!hits.length)throw Error('Keine Schnittstelle zur ausgewählten '+(atStart?'hinteren':'vorderen')+' Bezugslinie in Verlängerung der Spur.');
   const move=hits[0].t-inset;
   if(move<=-len+0.05)throw Error('Der Innenabstand überschreitet den ersten Spurabschnitt.');
   const point=unproject([a[0]+move*d[0],a[1]+move*d[1]]);
   const out=track.map(p=>[...p]);out[atStart?0:out.length-1]=point;
   return out;
 }
 function constructThree(){
   if(!st.field)throw Error('Bitte zuerst ein Feld wählen.');
   const back=selectedReference('mp-ref-back'),side=selectedReference('mp-ref-side'),front=selectedReference('mp-ref-front');
   const backD=inputMeter('mp-ref-back-distance'),sideD=inputMeter('mp-ref-side-distance',true),frontD=inputMeter('mp-ref-front-distance');
   if(side.key.startsWith('track:')&&Number(side.key.split(':')[1])===st.selected)throw Error('Bitte nicht die gerade ausgewählte Spur als eigene seitliche Referenz verwenden.');
   // Kantenfolge der Seitenreferenz bleibt erhalten. Eine ausreichend lange
   // Tangentenverlängerung erlaubt Schnitte mit Stirngrenzen auch jenseits der Eckpunkte.
   let path=sideD===0?side.points.map(p=>[...p]):offset(side.points,sideD);
   if(path.length<2)throw Error('Die seitliche Bezugslinie ist zu kurz.');
   const p=path.map(project),start=p[0],next=p[1],end=p[p.length-1],prev=p[p.length-2];
   const extend=(a,b)=>{const dx=a[0]-b[0],dy=a[1]-b[1],len=Math.hypot(dx,dy);if(len<.01)throw Error('Doppelte Stützpunkte in der Bezugslinie.');return unproject([a[0]+dx/len*10000,a[1]+dy/len*10000])};
   path=[extend(start,next),...path,extend(end,prev)];
   // Schnittpunkte mit Querlinien auf allen Segmenten suchen; nach der
   // Reihenfolge entlang der Spur zuschneiden.
   const metric=path.map(project),cum=[0];for(let i=1;i<metric.length;i++)cum.push(cum[i-1]+Math.hypot(metric[i][0]-metric[i-1][0],metric[i][1]-metric[i-1][1]));
   const crossings=ref=>{const result=[];for(let i=0;i<metric.length-1;i++){
     const a=metric[i],b=metric[i+1],d=[b[0]-a[0],b[1]-a[1]];
     for(const hit of lineHits(a,d,ref.points))if(hit.t>=-1e-7&&hit.t<=1+1e-7)result.push({s:cum[i]+Math.max(0,hit.t)*Math.hypot(...d),point:hit.point});
   }return result};
   const backs=crossings(back),fronts=crossings(front);
   if(!backs.length||!fronts.length)throw Error('Die seitliche Spur schneidet nicht beide gewählten Querlinien. Bitte Referenzen oder Seitenabstand ändern.');
   // Die kürzeste positive Strecke zwischen hinten und vorne wählen.
   let pair=null;
   for(const b of backs)for(const f of fronts){const dist=f.s-b.s;if(dist>Math.max(0.2,backD+frontD+0.1)&&(!pair||dist<pair.dist))pair={b,f,dist,reverse:false};}
   if(!pair)for(const b of backs)for(const f of fronts){const dist=b.s-f.s;if(dist>Math.max(0.2,backD+frontD+0.1)&&(!pair||dist<pair.dist))pair={b:f,f:b,dist,reverse:true};}
   if(!pair)throw Error('Querlinien sind zu dicht beieinander oder in ungeeigneter Reihenfolge.');
   const at=(s)=>{for(let i=0;i<cum.length-1;i++)if(s<=cum[i+1]+1e-7){const t=Math.max(0,Math.min(1,(s-cum[i])/(cum[i+1]-cum[i]||1)));return unproject([metric[i][0]+(metric[i+1][0]-metric[i][0])*t,metric[i][1]+(metric[i+1][1]-metric[i][1])*t])}return path[path.length-1]};
   const from=pair.b.s+backD,to=pair.f.s-frontD;
   if(to-from<0.5)throw Error('Nach Abzug des Vorgewendes bleibt keine ausreichende Spurlänge.');
   const newTrack=[at(from)];for(let i=1;i<cum.length-1;i++)if(cum[i]>from+1e-6&&cum[i]<to-1e-6)newTrack.push(path[i]);newTrack.push(at(to));
   if(pair.reverse)newTrack.reverse();
   if(newTrack.length<2||trackLength(newTrack)<1)throw Error('Spur wäre zu kurz.');
   history();st.tracks.push(newTrack);st.selected=st.tracks.length-1;render();msg(`Spur ${st.selected+1} aus drei Bezugslinien erstellt (${trackLength(newTrack).toFixed(2)} m). Bitte Grenzabstand und Arbeitsbreite prüfen.`);
 }

 function history(){st.history.push(JSON.stringify(st.tracks));if(st.history.length>50)st.history.shift();st.dirty=true}
 function pointInside(p){const poly=st.field.boundary;let inside=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const a=poly[i],b=poly[j];if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])inside=!inside}return inside}
 function distanceSegment(p,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy||1)));return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)}
 function warnings(){
   // V47: Keine Prüfung oder Warnung mehr für Spurmitten außerhalb
   // der Feldgrenze. Die optionale Arbeitsbreiten-Warnung bleibt erhalten.
   if(!st.field)return '';
   const boundary=st.field.boundary.map(project);
   let band=0;
   for(const t of st.tracks){
     for(let j=0;j<t.length-1;j++){
       const a=project(t[j]),b=project(t[j+1]);
       const steps=Math.max(2,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/2));
       for(let k=0;k<=steps;k++){
         const p=[a[0]+(b[0]-a[0])*k/steps,a[1]+(b[1]-a[1])*k/steps];
         let d=Infinity;
         for(let h=0;h<boundary.length-1;h++)d=Math.min(d,distanceSegment(p,boundary[h],boundary[h+1]));
         if(d<width()/2)band++;
       }
     }
   }
   return band?`⚠ Arbeitsbreite kann an der Feldgrenze überstehen (${band} Prüfpunkte).`:'Keine Überlappung mit dem Feldrand in den Stichproben erkannt.';
 }
 // Pfeile entlang der gespeicherten Reihenfolge der Stützpunkte.
 // Der erste Punkt ist der Fahrtbeginn, der letzte das Fahrtende.
 function renderArrows(){
   if(!st.map||!st.arrows)return;
   st.arrows.clearLayers();
   st.tracks.forEach((track,i)=>{
     if(track.length<2)return;
     const segments=[];let total=0;
     for(let j=0;j<track.length-1;j++){
       const length=meters(track[j],track[j+1]);
       if(length<.05)continue;
       segments.push({a:track[j],b:track[j+1],start:total,length});total+=length;
     }
     if(total<.1)return;
     // Lange Spuren erhalten mehrere Pfeile, kurze mindestens einen.
     const count=Math.min(5,Math.max(1,Math.ceil(total/65)));
     for(let k=0;k<count;k++){
       const distance=total*(k+1)/(count+1);
       const segment=segments.find(x=>distance<=x.start+x.length)||segments[segments.length-1];
       const fraction=Math.max(0,Math.min(1,(distance-segment.start)/segment.length));
       const a=st.map.latLngToLayerPoint(latlng(segment.a));
       const b=st.map.latLngToLayerPoint(latlng(segment.b));
       const angle=Math.atan2(b.y-a.y,b.x-a.x)*180/Math.PI;
       const position=st.map.layerPointToLatLng(L.point(a.x+(b.x-a.x)*fraction,a.y+(b.y-a.y)*fraction));
       const color=i===st.selected?'#d36a00':'#135bb8';
       const icon=L.divIcon({className:'mp-direction-icon',html:`<svg viewBox="0 0 30 30" width="30" height="30" aria-hidden="true" style="transform:rotate(${angle}deg)"><path d="M3 15 H23 M16 8 L23 15 L16 22" fill="none" stroke="white" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 15 H23 M16 8 L23 15 L16 22" fill="none" stroke="${color}" stroke-width="3.3" stroke-linecap="round" stroke-linejoin="round"/></svg>`,iconSize:[30,30],iconAnchor:[15,15]});
       L.marker(position,{icon,interactive:false,keyboard:false,zIndexOffset:500}).addTo(st.arrows);
     }
   });
 }
 function render(){if(!st.map)return;st.layers.clearLayers();st.markers.clearLayers();st.bands.clearLayers();const w=width();st.tracks.forEach((t,i)=>{const path=t.map(latlng);if($('mp-bands').checked){for(let k=0;k<t.length-1;k++){const a=project(t[k]),b=project(t[k+1]),dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy);if(len<.001)continue;const nx=-dy/len*w/2,ny=dx/len*w/2;L.polygon([[a[0]+nx,a[1]+ny],[b[0]+nx,b[1]+ny],[b[0]-nx,b[1]-ny],[a[0]-nx,a[1]-ny]].map(v=>latlng(unproject(v))),{stroke:false,fillColor:'#418fe4',fillOpacity:.18,interactive:false}).addTo(st.bands)}}const line=L.polyline(path,{color:i===st.selected?'#ed8a20':'#2478e4',weight:i===st.selected?5:3}).addTo(st.layers);line.on('click',e=>{if(st.mode==='draw')return;L.DomEvent.stopPropagation(e);st.selected=i;render()});if(i===st.selected&&st.mode==='select')t.forEach((p,j)=>{const m=L.marker(latlng(p),{draggable:true}).addTo(st.markers);m.on('dragstart',history);m.on('dragend',()=>{const q=m.getLatLng();st.tracks[i][j]=[q.lng,q.lat];render()});m.on('contextmenu',()=>{if(t.length>2){history();t.splice(j,1);render()}})})});if(st.drawing.length)L.polyline(st.drawing.map(latlng),{color:'#ec8d22',weight:4,dashArray:'5 5'}).addTo(st.layers);const list=$('mp-list');list.replaceChildren();st.tracks.forEach((t,i)=>{const b=document.createElement('button');b.type='button';b.textContent=`Spur ${i+1} · ${trackLength(t).toFixed(2).replace(".",",")} m`;if(i===st.selected)b.classList.add('active');b.onclick=()=>{st.selected=i;st.mode='select';render()};list.append(b)});$('mp-selection').textContent=st.selected<0?'Keine Spur ausgewählt':`Spur ${st.selected+1} · ${st.tracks[st.selected].length} Stützpunkte · ${trackLength(st.tracks[st.selected]).toFixed(2).replace('.',',')} m`;refreshReferences();$('mp-coverage').textContent='';$('mp-coverage').style.color='';}
 async function loadField(){if(st.dirty&&!confirm('Ungespeicherte Spuren verwerfen?'))return;st.field=null;st.tracks=[];st.selected=-1;st.id=null;st.dirty=false;st.drawing=[];if(st.layers)st.layers.clearLayers();if(st.markers)st.markers.clearLayers();if(st.bands)st.bands.clearLayers();if(st.arrows)st.arrows.clearLayers();if(st.fieldLayer)st.map.removeLayer(st.fieldLayer);if(st.edgeLabels)st.edgeLabels.clearLayers();if(!$('mp-field').value)return;st.field=await api('/api/fields/'+$('mp-field').value);st.fieldLayer=L.polygon(st.field.boundary.map(latlng),{color:'#2e8755',weight:3,fillOpacity:.08}).addTo(st.map);st.map.fitBounds(st.fieldLayer.getBounds(),{padding:[30,30]});showBoundaryLengths();render()}
 function finish(){if(st.drawing.length>=2){history();st.tracks.push(st.drawing);st.selected=st.tracks.length-1;msg('Spur angelegt. Jetzt präzise bearbeiten oder speichern.')}else if(st.drawing.length)msg('Mindestens zwei Punkte setzen.',true);st.drawing=[];st.mode='select';render()}
 async function save(){if(st.mode==='draw')finish();if(!st.field||!$('mp-name').value.trim()||!$('mp-tractor').value||!$('mp-implement').value)throw Error('Name, Feld, Traktor und Anbaugerät auswählen.');if(!st.tracks.length)throw Error('Mindestens eine Spur zeichnen.');const body={name:$('mp-name').value.trim(),field_id:+$('mp-field').value,tractor_id:+$('mp-tractor').value,implement_id:+$('mp-implement').value,tracks:st.tracks};let result;if(st.id){result=await api(`/api/work-plannings/${st.id}/manual-tracks`,{method:'PUT',body:JSON.stringify({tracks:st.tracks})})}else{result=await api('/api/work-plannings/manual',{method:'POST',body:JSON.stringify(body)});st.id=result.id}st.dirty=false;msg(`${st.tracks.length} Fahrspuren gespeichert (Arbeitsauftrag ${st.id}). GPS-Führung verwendet diese Spuren.`);await load()}
 async function openPlan(plan){if(st.dirty&&!confirm('Ungespeicherte Spuren verwerfen?'))return;const manual=await api(`/api/work-plannings/${plan.id}/manual-tracks`);if(!manual.tracks.length){msg('Dieser ältere Auftrag hat keine manuell gespeicherten Spuren.',true);return}$('mp-name').value=plan.name;$('mp-tractor').value=plan.tractor_id;$('mp-implement').value=plan.implement_id;$('mp-field').value=plan.field_id;st.dirty=false;await loadField();st.tracks=manual.tracks;st.id=plan.id;st.selected=0;st.dirty=false;render();msg(`Arbeitsauftrag ${plan.id} mit ${st.tracks.length} manuellen Spuren geladen.`)}
 function init(){const bind=(id,fn)=>$(id).addEventListener('click',()=>{try{const r=fn();if(r?.catch)r.catch(e=>msg(e.message,true))}catch(e){msg(e.message,true)}});bind('mp-refresh',load);bind('mp-select',()=>{st.mode='select';st.drawing=[];render()});bind('mp-draw',()=>{st.mode='draw';st.drawing=[];msg('Auf die Karte klicken; mit „Zeichnung abschließen“ beenden.')});bind('mp-finish',finish);bind('mp-undo',()=>{if(st.history.length){st.tracks=JSON.parse(st.history.pop());st.selected=-1;st.dirty=true;render()}});bind('mp-delete',()=>{if(st.selected>=0){history();st.tracks.splice(st.selected,1);st.selected=-1;render()}});bind('mp-apply-shift',()=>{if(st.selected<0)throw Error('Spur auswählen.');const m=Number($('mp-value').value);if(!Number.isFinite(m))throw Error('Ungültiger Meterwert.');const t=offset(st.tracks[st.selected],m);history();st.tracks[st.selected]=t;render()});bind('mp-add-parallel',()=>{if(st.selected<0)throw Error('Spur auswählen.');const m=Number($('mp-value').value);if(!Number.isFinite(m)||m===0)throw Error('Abstand muss ungleich null sein.');const t=offset(st.tracks[st.selected],m);history();st.tracks.push(t);st.selected=st.tracks.length-1;render()});bind('mp-apply-length',()=>{if(st.selected<0)throw Error('Bitte zuerst eine Spur auswählen.');const raw=$('mp-value').value;const target=Number(raw);if(!raw.trim()||!Number.isFinite(target))throw Error('Bitte eine Länge in Metern eingeben.');const updated=setLength(st.tracks[st.selected],target);history();st.tracks[st.selected]=updated;render();msg(`Spurlänge auf ${trackLength(updated).toFixed(2)} m angepasst. Bitte Feldgrenze prüfen.`)});bind('mp-apply-trim-start',()=>{if(st.selected<0)throw Error('Spur auswählen.');const v=Number($('mp-value').value);const t=trimTrack(st.tracks[st.selected],v,true);history();st.tracks[st.selected]=t;render();msg(`Spuranfang um ${v.toFixed(2)} m gekürzt.`)});
 bind('mp-apply-trim-end',()=>{if(st.selected<0)throw Error('Spur auswählen.');const v=Number($('mp-value').value);const t=trimTrack(st.tracks[st.selected],v,false);history();st.tracks[st.selected]=t;render();msg(`Spurende um ${v.toFixed(2)} m gekürzt.`)});
 const snap=(atStart)=>{if(st.selected<0)throw Error('Spur auswählen.');const d=inputMeter('mp-value');const ref=selectedReference('mp-end-reference');const updated=intersectEndpoint(st.tracks[st.selected],ref,d,atStart);history();st.tracks[st.selected]=updated;render();msg(`${atStart?'Spuranfang':'Spurende'} an ${ref.label} ausgerichtet (${d.toFixed(2)} m Innenabstand).`);};
 bind('mp-snap-start',()=>snap(true));bind('mp-snap-end',()=>snap(false));
 bind('mp-construct',constructThree);bind('mp-save',save);$('mp-field').onchange=()=>loadField().catch(e=>msg(e.message,true));$('mp-implement').onchange=render;$('mp-bands').onchange=render;}
 document.addEventListener('DOMContentLoaded',init);return {show,load};
})();
