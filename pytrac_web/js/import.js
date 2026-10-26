"use strict";
(()=>{
 const file=document.getElementById("import-file"),preview=document.getElementById("import-preview");
 const apply=document.getElementById("import-apply"),summary=document.getElementById("import-summary");
 let approved=null;
 file.addEventListener("change",()=>{approved=null;apply.disabled=true;summary.textContent="";});
 async function call(payload,dry_run){
   const response=await fetch("/api/data-import",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({payload,dry_run})});
   const result=await response.json();
   if(!response.ok)throw new Error(typeof result.detail==="string"?result.detail:JSON.stringify(result.detail));
   return result;
 }
 function describe(result){
   const names={fields:"Felder",tractors:"Traktoren",implements:"Anbaugeräte",work_plannings:"Arbeitspläne",work_history:"GPS-Historienpunkte"};
   return Object.entries(result.counts).map(([key,c])=>`${names[key]}: ${c.new} neu, ${c.existing} bereits vorhanden`).join("\n");
 }
 preview.addEventListener("click",async()=>{
   approved=null;apply.disabled=true;summary.textContent="Prüfe Importdatei …";
   try{
     if(!file.files.length)throw new Error("Bitte eine JSON-Datei auswählen.");
     if(file.files[0].size>30_000_000)throw new Error("Datei zu groß (max. 30 MB).");
     const payload=JSON.parse(await file.files[0].text());
     const result=await call(payload,true);
     approved=payload;apply.disabled=false;
     summary.textContent="Vorschau (noch nichts gespeichert):\n"+describe(result);
   }catch(e){summary.textContent="Importprüfung fehlgeschlagen: "+e.message;}
 });
 apply.addEventListener("click",async()=>{
   if(!approved)return;
   if(!confirm("Geprüfte Daten jetzt importieren? Vorhandene Datensätze werden nicht überschrieben."))return;
   apply.disabled=true;preview.disabled=true;
   try{
     const result=await call(approved,false);
     summary.textContent="Import abgeschlossen:\n"+describe(result);
     approved=null;
     if(typeof loadAll==="function")await loadAll();
   }catch(e){summary.textContent="Import fehlgeschlagen (Transaktion zurückgesetzt): "+e.message;apply.disabled=false;}
   finally{preview.disabled=false;}
 });
})();
