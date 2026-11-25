// Live HA terminal. All attendance decisions and PIN checks run on the server.
class FFStaffTerminal extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this.stage = "pin";
    this.pin = "";
    this.error = "";
    this.generation = 0;
    this.busy = false;
  }
  setConfig(config) {
    if (!config.entry_id) throw new Error("Set the RotaCloud integration entry_id.");
    const length = config.pin_length ?? 4;
    if (!Number.isInteger(length) || length < 1 || length > 12) throw new Error("pin_length must be 1–12.");
    this.config = {...config, pin_length: length};
    this.reset();
  }
  set hass(value) {
    if (this._hass && (this._hass.connection !== value.connection || this._hass.user?.id !== value.user?.id)) this.reset();
    const changed = this._hass?.user?.is_admin !== value.user?.is_admin;
    this._hass = value;
    if (changed || !this.shadowRoot.firstChild) this.render();
  }
  connectedCallback() {
    this.render();
    this.ticker = setInterval(() => {
      const node = this.shadowRoot.querySelector("[data-break]");
      if (node && this.person?.active_break_start) node.textContent = this.duration(Date.now()/1000-this.person.active_break_start);
    }, 1000);
  }
  disconnectedCallback() {
    clearInterval(this.ticker);
    this.reset();
  }
  getCardSize() { return 9; }
  duration(seconds) {
    const m = Math.max(0, Math.floor((seconds || 0)/60));
    return Math.floor(m/60) + "h " + String(m%60).padStart(2,"0") + "m";
  }
  time(seconds) {
    return seconds == null ? "—" : new Intl.DateTimeFormat("en-GB", {
      timeZone: this._hass?.config?.time_zone || "Europe/London", hour:"2-digit", minute:"2-digit", hourCycle:"h23"
    }).format(seconds*1000);
  }
  reset(error = "") {
    clearTimeout(this.timeout);
    this.generation++;
    this.stage = "pin";
    this.pin = "";
    this.person = null;
    this.result = null;
    this.error = error;
    this.busy = false;
    this.render();
  }
  arm(ms) { clearTimeout(this.timeout); this.timeout = setTimeout(() => this.reset(), ms); }
  press(value) {
    if (this.busy || this.stage !== "pin" || !this._hass?.user?.is_admin) return;
    this.error = "";
    if (value === "clear") this.pin = "";
    else if (value === "back") this.pin = this.pin.slice(0,-1);
    else if (/^[0-9]$/.test(value) && this.pin.length < this.config.pin_length) this.pin += value;
    this.arm(20000);
    if (this.pin.length === this.config.pin_length) void this.identify();
    else this.render();
  }
  async request(command, data, mutation = false) {
    let timeout;
    try {
      return await Promise.race([
        this._hass.callWS({type: "rotacloud_attendance/terminal/"+command, entry_id: this.config.entry_id, ...data}),
        new Promise((_,reject) => { timeout = setTimeout(() => reject(new Error("timeout")), 70000); })
      ]);
    } catch (err) {
      if (err?.code === "terminal_error") throw new Error(err.message);
      if (err?.code === "unauthorized") throw new Error("Administrator access is required.");
      if (err?.code === "unknown_command") throw new Error("Update the RotaCloud integration and restart Home Assistant.");
      throw new Error(mutation ? "Outcome unknown. Check RotaCloud before trying again." : "Clocking unavailable. Use the RotaCloud terminal.");
    } finally { clearTimeout(timeout); }
  }
  async identify() {
    if (this.busy) return;
    const generation = this.generation;
    const pin = this.pin;
    this.pin = "";
    this.busy = true;
    clearTimeout(this.timeout);
    this.render();
    try {
      const person = await this.request("identify", {password:pin});
      if (generation !== this.generation || !this.isConnected) return;
      this.person = person;
      this.shift = person.shifts.length === 1 ? person.shifts[0].id : null;
      this.stage = "actions";
      this.busy = false;
      this.arm(20000);
      this.render();
    } catch (err) { if (generation === this.generation) this.reset(err.message); }
  }
  async act(action) {
    if (this.busy || !this.person || !this.person.actions.includes(action)) return;
    if (action === "clock_in" && this.person.shifts.length && this.shift == null) return;
    const generation = this.generation;
    const data = {token: this.person.token, action};
    if (action === "clock_in" && this.shift != null) data.shift_id = this.shift;
    this.busy = true;
    clearTimeout(this.timeout);
    this.render();
    try {
      const result = await this.request("act", data, true);
      if (generation !== this.generation || !this.isConnected) return;
      this.result = result;
      this.person.token = null;
      this.stage = "result";
      this.busy = false;
      this.arm(5000);
      this.render();
    } catch (err) { if (generation === this.generation) this.reset(err.message); }
  }
  render() {
    if (!this.config) return;
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;color:#fff;font-family:Nunito,Arial,sans-serif}*{box-sizing:border-box}
      main{min-height:560px;background:#121212;border:1px solid #333;border-radius:18px;padding:clamp(16px,3vw,40px);display:flex;align-items:center;flex-direction:column;gap:20px}
      header{text-align:center;border-bottom:1px solid #333;width:100%;padding-bottom:20px}h1{font-family:Montserrat,Arial,sans-serif;font-size:clamp(24px,4vw,36px);font-weight:900;font-style:italic;margin:0;letter-spacing:-.04em}h1 span{color:#ff6600}
      .sub{color:#b8b8b8;font-size:13px;letter-spacing:.13em;margin-top:6px;text-transform:uppercase}h2{margin:0;font-size:26px;text-align:center}p{margin:0;color:#bbb;text-align:center}.dots{font-size:24px;letter-spacing:10px;color:#ff6600;min-height:30px}
      .keys{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;width:min(100%,360px)}button,select{font:inherit;min-height:62px;border:1px solid #404040;border-radius:10px;background:#252525;color:white;touch-action:manipulation}button{cursor:pointer}button:focus-visible,select:focus-visible{outline:3px solid #ff6600}button:disabled{opacity:.5;cursor:wait}.keys button{font-size:25px}.keys .small{font-size:15px}
      .actions{width:min(100%,460px);display:grid;gap:12px}.action{font-size:20px;font-weight:800}.green{background:#176b43;border-color:#258f5d}.amber{background:#76520d;border-color:#b58a2c}.red{background:#842e2e;border-color:#b74b4b}.quiet{min-height:42px;background:transparent;border:0;color:#bbb}.stats{display:grid;gap:12px;width:min(100%,460px)}.stat{border-radius:12px;background:#252525;padding:14px;text-align:center}.stat small{display:block;color:#bbb}.stat strong{display:block;font-size:clamp(24px,4vw,36px);font-variant-numeric:tabular-nums;margin-top:5px}.ok{color:#5bd492;font-size:40px}.err{color:#ff9b9b}.foot{font-size:12px;color:#aaa;text-align:center}#body{width:100%;display:flex;align-items:center;flex-direction:column;gap:18px}select{width:100%;padding:10px}
      </style><main><header><h1>STAFF <span>ATTENDANCE</span></h1><div class="sub">Staff clocking terminal</div></header><section id="body" aria-live="polite"></section><div class="foot">RotaCloud attendance</div></main>`;
    const body = this.shadowRoot.querySelector("#body");
    const el = (tag,text,cls,parent=body) => {
      const node = document.createElement(tag);
      if (text != null) node.textContent = text;
      if (cls) node.className = cls;
      parent.append(node); return node;
    };
    const button = (text,cls,fn,parent=body) => {
      const node = el("button",text,cls,parent); node.type="button";
      node.disabled=this.busy; node.addEventListener("click",fn); return node;
    };
    const stats = items => {
      const grid = el("div",null,"stats");
      for (const [label,value,running] of items) {
        const stat = el("div",null,"stat",grid); el("small",label,null,stat);
        const valueNode = el("strong",value,null,stat); if(running) valueNode.dataset.break="";
      }
    };
    if (!this._hass?.user?.is_admin) { el("p","Administrator access is required.","err"); return; }
    if (this.busy) { el("h2","Please wait…"); el("p",this.stage === "actions" ? "Saving attendance…" : "Checking PIN…"); return; }
    if (this.stage === "pin") {
      el("h2","Enter your PIN");
      el("div",Array.from({length:this.config.pin_length},(_,i)=>i<this.pin.length?"●":"○").join(""),"dots");
      if(this.error) el("p",this.error,"err");
      const keys = el("div",null,"keys");
      for(const k of ["1","2","3","4","5","6","7","8","9","clear","0","back"])
        button(k==="clear"?"Clear":k==="back"?"⌫":k,k.length>1?"small":"",()=>this.press(k),keys);
    } else if (this.stage === "actions") {
      const p=this.person;
      el("h2","Hello, "+p.name);
      el("p",p.state==="out"?"Not clocked in":p.state==="break"?"On break":"Clocked in");
      if(p.state==="break") stats([["Current break",this.duration(Date.now()/1000-p.active_break_start),true]]);
      if(p.state!=="out") stats([["Clocked in",this.time(p.clock_in)],["Scheduled finish",this.time(p.scheduled_end)],["Breaks today",this.duration(p.break_seconds_today ?? p.break_seconds)]]);
      const actions=el("div",null,"actions");
      if(p.state==="out" && p.shifts.length) {
        const label=el("label","Scheduled shift",null,actions);
        const select=el("select",null,null,label);
        const empty=el("option","Choose your shift",null,select); empty.value="";
        for(const shift of p.shifts){const o=el("option",this.time(shift.start)+" – "+this.time(shift.end),null,select);o.value=String(shift.id);}
        select.value=this.shift==null?"":String(this.shift);
        select.addEventListener("change",()=>{this.shift=select.value?Number(select.value):null;this.render();});
      } else if (p.state==="out") el("p","No remaining scheduled shift today. Clock in as unscheduled.");
      const choices={clock_in:["CLOCK IN","green"],start_break:["START BREAK","amber"],end_break:["END BREAK","green"],clock_out:["CLOCK OUT","red"]};
      for(const action of p.actions){const c=choices[action];if(!c)continue;const b=button(c[0],"action "+c[1],()=>void this.act(action),actions);if(action==="clock_in"&&p.shifts.length&&this.shift==null)b.disabled=true;}
      button("Cancel","quiet",()=>this.reset(),actions);
    } else if (this.stage === "result") {
      const r=this.result;
      const titles={clock_in:"Clocked in",clock_out:"Clocked out",start_break:"Break started",end_break:"Break ended"};
      el("div","✓","ok"); el("h2",titles[r.action]);
      const greeting={clock_in:"Have a great shift, ",clock_out:"Thanks for today, ",start_break:"Enjoy your break, ",end_break:"Welcome back, "};
      el("p",greeting[r.action]+this.person.name+"!");
      if(r.action==="clock_in") stats([["Clock-in time",this.time(r.clock_in)],["Scheduled finish",this.time(r.scheduled_end)]]);
      if(r.action==="start_break") stats([["Break started",this.time(r.last_break_start)],["Breaks today",this.duration(r.break_seconds_today ?? r.break_seconds)]]);
      if(r.action==="end_break") stats([["This break",this.duration(r.last_break_seconds)],["Breaks today",this.duration(r.break_seconds_today ?? r.break_seconds)]]);
      if(r.action==="clock_out") {stats([["Clock-out time",this.time(r.clock_out)],["Total shift duration",this.duration(r.shift_seconds)],["Breaks today",this.duration(r.break_seconds_today ?? r.break_seconds)]]);if(r.provisional_break_total)el("p","Break total awaiting RotaCloud reconciliation.");}
      button("Done","quiet",()=>this.reset());
    }
  }
}
if(!customElements.get("ff-staff-terminal")) customElements.define("ff-staff-terminal",FFStaffTerminal);
window.customCards=window.customCards||[];
window.customCards.push({type:"ff-staff-terminal",name:"Staff attendance terminal",description:"Live RotaCloud clocking inside Home Assistant"});
