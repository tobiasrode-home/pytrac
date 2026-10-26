"use strict";
/* Feldgrenze: konservative Geradenerkennung ab 5 m, nur im Web-Editor. */
(()=>{
 let previous=null;
 const $id=id=>document.getElementById(id);
 const distance=(a,b)=>{
   const y=(a[1]+b[1])*Math.PI/360;
   return Math.hypot((a[0]-b[0])*111320*Math.cos(y),(a[1]-b[1])*110540);
 };
 function perpendicular(p,a,b){
   const lat=(a[1]+b[1])*Math.PI/360;
   const x=(p[0]-a[0])*111320*Math.cos(lat),y=(p[1]-a[1])*110540;
   const vx=(b[0]-a[0])*111320*Math.cos(lat),vy=(b[1]-a[1])*110540;
   const t=Math.max(0,Math.min(1,(x*vx+y*vy)/(vx*vx+vy*vy||1)));
   return Math.hypot(x-t*vx,y-t*vy);
 }
 function chainSimplify(chain,tolerance){
   const result=[chain[0]];let i=0;
   while(i<chain.length-1){
     let best=i+1;
     for(let j=i+2;j<chain.length;j++){
       if(distance(chain[i],chain[j])<5)continue;
       let ok=true;
       for(let k=i+1;k<j;k++){
         if(perpendicular(chain[k],chain[i],chain[j])>tolerance){ok=false;break;}
       }
       if(ok)best=j;
     }
     result.push(chain[best]);i=best;
   }
   return result;
 }
 function intersect(a,b,c,d){
   const orient=(p,q,r)=>(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]);
   const ab1=orient(a,b,c),ab2=orient(a,b,d),cd1=orient(c,d,a),cd2=orient(c,d,b);
   return ab1*ab2<0&&cd1*cd2<0;
 }
 function valid(ring){
   if(ring.length<4)return false;
   const n=ring.length-1;
   for(let i=0;i<n;i++)for(let j=i+2;j<n;j++){
     if(i===0&&j===n-1)continue;
     if(intersect(ring[i],ring[i+1],ring[j],ring[j+1]))return false;
   }
   return true;
 }
 function simplify(ring,tolerance){
   const open=ring.slice();
   if(open.length>1&&distance(open[0],open[open.length-1])<0.001)open.pop();
   if(open.length<4)return ring;
   // Zwei weit auseinanderliegende Ankerpunkte verhindern das Abflachen des geschlossenen Rings.
   let far=1;
   for(let i=2;i<open.length;i++)if(distance(open[0],open[i])>distance(open[0],open[far]))far=i;
   const first=chainSimplify(open.slice(0,far+1),tolerance);
   const second=chainSimplify([...open.slice(far),open[0]],tolerance);
   const merged=[...first,...second.slice(1)];
   return valid(merged)?merged:ring;
 }
 function currentPolygon(){
   let polygon=null;
   if(typeof fieldLayers==="undefined"||!fieldLayers)return null;
   fieldLayers.eachLayer(layer=>{if(layer instanceof L.Polygon)polygon=layer;});
   return polygon;
 }
 function getRing(layer){
   const points=layer.getLatLngs()[0].map(p=>[p.lng,p.lat]);
   if(points.length&&distance(points[0],points[points.length-1])>0.001)points.push([...points[0]]);
   return points;
 }
 function setRing(layer,ring){
   layer.setLatLngs([ring.slice(0,-1).map(([lon,lat])=>[lat,lon])]);
   if(typeof syncMapToForm==="function")syncMapToForm();
 }
 $id("field-straighten").addEventListener("click",()=>{
   const layer=currentPolygon(),status=$id("field-edit-status");
   if(!layer){status.textContent="Bitte zuerst eine Feldgrenze auswählen.";return;}
   const tolerance=Number($id("field-tolerance").value);
   if(!Number.isFinite(tolerance)||tolerance<0.05||tolerance>2){status.textContent="Toleranz muss zwischen 0,05 und 2 m liegen.";return;}
   const original=getRing(layer),reduced=simplify(original,tolerance);
   if(reduced.length===original.length){status.textContent="Keine geeigneten geraden Abschnitte ab 5 m gefunden.";return;}
   previous={ring:original,layer};
   setRing(layer,reduced);
   status.textContent=`Vorschau: ${original.length-1} → ${reduced.length-1} Eckpunkte. Erst „Speichern“ übernimmt die Grenze.`;
 });
 $id("field-restore").addEventListener("click",()=>{
   if(previous&&fieldLayers.hasLayer(previous.layer)){
     setRing(previous.layer,previous.ring);
     $id("field-edit-status").textContent="Vorherige Grenze wiederhergestellt.";
     previous=null;
   }else $id("field-edit-status").textContent="Keine vorherige Vereinfachung vorhanden.";
 });
})();
