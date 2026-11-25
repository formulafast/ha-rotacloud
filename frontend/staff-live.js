/* Read-only Lovelace attendance view. No RotaCloud calls, no writes. */
class FFStaffLive extends HTMLElement {
 constructor(){super();this.attachShadow({mode:"open"});this.filter="all";}
 setConfig(config){this.config=config;this.render();}
 set hass(value){this._hass=value;this.render();}
 connectedCallback(){this.ticker=setInterval(()=>this.render(),15000);}
 disconnectedCallback(){clearInterval(this.ticker);}
 getCardSize(){return 8;}
 render(){
  const root=this.shadowRoot;
  root.innerHTML=`<style>
:host{display:block;color:var(--primary-text-color);font-family:Nunito,Arial,sans-serif}*{box-sizing:border-box}main{padding:clamp(12px,2vw,28px)}h2{font-size:25px;margin:0 0 8px;font-family:Montserrat,Arial,sans-serif;font-style:italic;text-transform:uppercase}.sub{color:var(--secondary-text-color);font-size:13px;margin-bottom:18px}.counts{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:9px;margin:12px 0 22px}button{font:inherit;color:inherit;background:var(--card-background-color,#252525);border:1px solid var(--divider-color,#444);border-radius:10px;padding:13px 6px;cursor:pointer}button.selected{border:2px solid #ff6600;padding:12px 5px}button strong{display:block;font-size:27px;font-variant-numeric:tabular-nums}button small{font-size:12px}.scroll{overflow:auto;border:1px solid var(--divider-color,#444);border-radius:12px;background:var(--card-background-color,#252525)}table{border-collapse:collapse;width:100%;min-width:760px;font-variant-numeric:tabular-nums}th,td{padding:14px 12px;text-align:left;border-bottom:1px solid var(--divider-color,#444);white-space:nowrap}th{font-size:12px;color:var(--secondary-text-color);text-transform:uppercase}td{font-size:14px}tr:last-child td{border-bottom:0}.msg{padding:20px;background:var(--card-background-color,#252525);border:1px solid var(--divider-color,#444);border-radius:12px}.delta{font-size:12px;color:var(--secondary-text-color)}.warn{color:#ff9900}
</style><main></main>`;
  const body=root.querySelector("main"), add=(tag,value,parent=body,cls)=>{const e=document.createElement(tag);if(value!==null)e.textContent=value;if(cls)e.className=cls;parent.append(e);return e;};
  add("h2","Live attendance");
  const all=Object.values(this._hass?.states||{}),counts=all.filter(x=>x.attributes.rotacloud_kind==="count"),staff=all.filter(x=>x.attributes.rotacloud_kind==="staff");
  if(!counts.length){add("div","Awaiting RotaCloud integration setup. No live data is available yet.",body,"msg");return;}
  const present=counts.find(x=>x.attributes.rotacloud_status==="present");
  const stamp=present?.attributes.last_api_refresh;
  const valid=present&&!["unavailable","unknown"].includes(present.state)&&Number.isFinite(stamp);
  if(!valid){add("div","Attendance unavailable. Check the RotaCloud integration. No current status can be confirmed.",body,"msg");return;}
  const time=t=>Number.isFinite(t)?new Intl.DateTimeFormat("en-GB",{timeZone:"Europe/London",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(t*1000):"—";
  const date=t=>new Intl.DateTimeFormat("en-GB",{timeZone:"Europe/London",day:"numeric",month:"short",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(t*1000);
  const dur=s=>Number.isFinite(s)?Math.floor(Math.max(0,s)/3600)+"h "+String(Math.floor(Math.max(0,s)%3600/60)).padStart(2,"0")+"m":"—";
  const delta=s=>Number.isFinite(s)?" ("+(s>0?"+":"")+Math.round(s/60)+"m)":"";
  const now=Date.now()/1000,age=Math.max(0,now-stamp);
  add("div","Last API refresh: "+date(stamp)+" · "+dur(age)+" ago. Status and timers use cached data.",body,age>3600?"sub warn":"sub");
  const meta={here:["Here","#22c55e"],break:["On break","#eab308"],leaving:["Leaving","#a78bfa"],due:["Due","#60a5fa"],late:["Late","#ef4444"],gone:["Gone","#9ca3af"]};
  const grid=add("div",null,body,"counts");
  for(const [key,[label,color]] of Object.entries({all:["Clocked in","#ff6600"],...meta})){
   const val=key==="all"?present:counts.find(x=>x.attributes.rotacloud_status===key);
   const b=add("button",null,grid,this.filter===key?"selected":"");b.type="button";b.setAttribute("aria-pressed",String(this.filter===key));
   const num=add("strong",val?.state??"—",b);num.style.color=color;
   add("small",key==="all"?"Clocked in / show all":label,b);b.onclick=()=>{this.filter=key;this.render();};
  }
  const rows=staff.filter(x=>meta[x.state]&&(this.filter==="all"||x.state===this.filter)).sort((a,b)=>["late","break","leaving","here","due","gone"].indexOf(a.state)-["late","break","leaving","here","due","gone"].indexOf(b.state)||String(a.attributes.staff_name).localeCompare(String(b.attributes.staff_name)));
  if(!rows.length){add("div","No staff in this view.",body,"msg");return;}
  const scroll=add("div",null,body,"scroll"),table=add("table",null,scroll),head=add("tr",null,add("thead",null,table));
  for(const h of ["Staff","Status","Scheduled","Clock-in","Clock-out","Breaks today","Shift duration"])add("th",h,head);
  const tbody=add("tbody",null,table);
  for(const x of rows){const a=x.attributes,tr=add("tr",null,tbody),[label,color]=meta[x.state];add("td",a.staff_name||a.friendly_name,tr);const status=add("td","● "+label,tr);status.style.color=color;
   add("td",Number.isFinite(a.scheduled_start)?time(a.scheduled_start)+" – "+time(a.scheduled_end):"—",tr);
   add("td",time(a.clock_in)+delta(a.clock_in_delta_seconds),tr);add("td",time(a.clock_out)+delta(a.clock_out_delta_seconds),tr);
   const running=Number.isFinite(a.active_break_start)?Math.max(0,now-a.active_break_start):null;
   add("td",dur(a.completed_break_seconds)+(running!==null?" + "+dur(running)+" active":""),tr);
   const elapsed=Number.isFinite(a.clock_out)?a.shift_duration_seconds:Number.isFinite(a.clock_in)?now-a.clock_in:null;
   add("td",dur(elapsed),tr);
  }
 }
}
if(!customElements.get("ff-staff-live"))customElements.define("ff-staff-live",FFStaffLive);
