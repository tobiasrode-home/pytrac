"use strict";
const PyTracExport=(()=>{
 const categories={fields:"/api/fields",tractors:"/api/tractors",implements:"/api/implements",work_plannings:"/api/work-plannings"};
 const status=()=>document.getElementById("export-status");
 async function get(path){
   const response=await fetch(path,{cache:"no-store"});
   if(!response.ok)throw new Error(`${path}: HTTP ${response.status}`);
   return response.json();
 }
 async function collect(kind,plans){
   if(kind==="work_history"){
     const items=plans||await get(categories.work_plannings);
     const histories=[];
     for(const plan of items){
       const points=await get(`/api/work-plannings/${encodeURIComponent(plan.id)}/progress`);
       histories.push({planning_id:plan.id,planning_name:plan.name,points});
     }
     return histories;
   }
   return get(categories[kind]);
 }
 function download(payload,kind){
   const stamp=new Date().toISOString().replace(/[:.]/g,"-");
   const file=new Blob([JSON.stringify(payload,null,2)],{type:"application/json;charset=utf-8"});
   const url=URL.createObjectURL(file),link=document.createElement("a");
   link.href=url;link.download=`pytrac_${kind}_${stamp}.json`;
   document.body.appendChild(link);link.click();link.remove();
   setTimeout(()=>URL.revokeObjectURL(url),30000);
 }
 async function run(kind){
   const el=status();el.textContent="Export wird vorbereitet …";
   document.querySelectorAll("[data-export]").forEach(b=>b.disabled=true);
   try{
     const data={format:"pytrac-export",version:1,exported_at:new Date().toISOString()};
     if(kind==="all"){
       const [fields,tractors,implementsList,plans]=await Promise.all([
         collect("fields"),collect("tractors"),collect("implements"),collect("work_plannings")
       ]);
       Object.assign(data,{fields,tractors,implements:implementsList,work_plannings:plans});
       el.textContent=`Arbeitshistorie für ${plans.length} Arbeitspläne wird geladen …`;
       data.work_history=await collect("work_history",plans);
     }else{
       data[kind]=await collect(kind);
     }
     download(data,kind);el.textContent="Exportdatei wurde zum Download bereitgestellt.";
   }catch(error){el.textContent="Export fehlgeschlagen: "+error.message;}
   finally{document.querySelectorAll("[data-export]").forEach(b=>b.disabled=false);}
 }
 document.querySelectorAll("[data-export]").forEach(button=>button.addEventListener("click",()=>run(button.dataset.export)));
 return {run};
})();
