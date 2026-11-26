const {test, before, after} = require("node:test");
const assert = require("node:assert/strict");
const {chromium} = require("playwright");
const path = require("node:path");
let browser;
before(async () => { browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH || undefined}); });
after(async () => { await browser?.close(); });

async function loadCard(page,name) {
 await page.route('http://fixture.local/',route=>route.fulfill({contentType:'text/html',body:'<body style="margin:0;background:#121212"></body>'}));
 if(page.url()!=='http://fixture.local/')await page.goto('http://fixture.local/');
 await page.route('http://fixture.local/cards/**',route=>route.fulfill({contentType:'text/javascript',path:path.join(__dirname,'../custom_components/rotacloud_attendance/frontend/',new URL(route.request().url()).pathname.split('/').at(-1))}));
 await page.addScriptTag({type:'module',url:'http://fixture.local/cards/'+name});
}

async function fixture(t, width=1024) {
  const page=await browser.newPage({viewport:{width,height:900}});
  t.after(()=>page.close());
  const errors=[]; page.on("pageerror", e=>errors.push(e.message));
  t.after(()=>assert.deepEqual(errors,[]));
  await page.setContent('<body style="margin:0;background:#252525"></body>');
  await loadCard(page,"staff-terminal.js");
  await page.evaluate(()=>{
    window.calls=[]; window.status="out"; window.mode="normal";
    window.card=document.createElement("ff-staff-terminal");
    card.setConfig({entry_id:"fictional-entry"});
    card.hass={user:{id:"admin",is_admin:true},config:{time_zone:"Europe/London"},connection:{},callWS:async msg=>{
      calls.push(msg);
      const now=Math.floor(Date.now()/1000);
      if(msg.type.endsWith("identify")) {
        const result={token:"a".repeat(43),name:"Alex",state:status,
          actions:status==="out"?["clock_in"]:status==="break"?["end_break","clock_out"]:["start_break","clock_out"],
          clock_in:now-3600,scheduled_end:now+3600,break_seconds:600,break_seconds_today:780,active_break_start:now-60,
          shifts:status==="out"?[{id:7,start:now-600,end:now+3600}]:[]};
        if(mode==="multiple") result.shifts.push({id:8,start:now,end:now+7200});
        if(mode==="defer") return await new Promise(resolve=>{window.resolveIdentify=()=>resolve(result);});
        return result;
      }
      if(mode==="uncertain") throw new Error("connection lost");
      status=msg.action==="clock_out"?"out":msg.action==="start_break"?"break":"here";
      return {action:msg.action,state:status,clock_in:now,clock_out:now,scheduled_end:now+3600,
        shift_seconds:3600,break_seconds:600,last_break_seconds:60,last_break_start:now};
    }};
    document.body.append(card);
  });
  return page;
}
async function pin(page){for(const n of ["1","2","3","4"]) await page.getByRole("button",{name:n,exact:true}).click();}

test("live clock in, breaks and clock out; responsive card",async t=>{
  const page=await fixture(t,390);
  for(const [button,title] of [["CLOCK IN","Clocked in"],["START BREAK","Break started"],["END BREAK","Break ended"],["CLOCK OUT","Clocked out"]]){
    await pin(page);
    await page.getByRole("heading",{name:"Hello, Alex"}).waitFor();
    if(button === "START BREAK") assert.equal(await page.locator(".stat").filter({hasText:"Total Break Time"}).locator("strong").textContent(),"0h 13m");
    assert.equal(await page.evaluate(()=>card.pin),"");
    await page.getByRole("button",{name:button,exact:true}).click();
    await page.getByRole("heading",{name:title,exact:true}).waitFor();
    await page.getByRole("button",{name:"Done",exact:true}).click();
  }
  const calls=await page.evaluate(()=>calls);
  assert.equal(calls.length,8);
  assert.deepEqual(calls.filter(x=>x.type.endsWith("act")).map(x=>x.action),["clock_in","start_break","end_break","clock_out"]);
  assert.equal(calls[1].shift_id,7);
  assert.equal(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),true);
  if(process.env.FF_SCREENSHOT_DIR) await page.screenshot({path:path.join(process.env.FF_SCREENSHOT_DIR,"terminal-mobile.png"),fullPage:true});
});
test("multiple shifts require explicit selection",async t=>{
  const page=await fixture(t); await page.evaluate(()=>{mode="multiple";});
  await pin(page);
  const clock=page.getByRole("button",{name:"CLOCK IN",exact:true});
  await clock.waitFor(); assert.equal(await clock.isDisabled(),true);
  await page.getByRole("combobox").selectOption("8");
  await clock.click();
  await page.getByRole("heading",{name:"Clocked in",exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>calls.at(-1).shift_id),8);
});
test("late PIN response cannot reveal a cancelled employee session",async t=>{
  const page=await fixture(t); await page.evaluate(()=>{mode="defer";});
  await pin(page); await page.waitForFunction(()=>window.resolveIdentify);
  await page.evaluate(()=>{card.reset();resolveIdentify();});
  await page.getByRole("heading",{name:"Enter your PIN"}).waitFor();
  assert.equal(await page.evaluate(()=>card.person),null);
  assert.equal(await page.getByRole("heading",{name:"Hello, Alex"}).count(),0);
});
test("duplicate taps send one mutation; uncertain failure invites reconciliation",async t=>{
  const page=await fixture(t); await pin(page);
  await page.getByRole("heading",{name:"Hello, Alex"}).waitFor();
  await page.evaluate(()=>{mode="uncertain";card.act("clock_in");card.act("clock_in");});
  await page.getByText("Outcome unknown. Check RotaCloud before trying again.",{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>calls.filter(x=>x.type.endsWith("act")).length),1);
  assert.equal(await page.evaluate(()=>card.person),null);
});
test("non-administrators cannot enter a PIN",async t=>{
  const page=await fixture(t);
  await page.evaluate(()=>{card.hass={...card._hass,user:{id:"staff",is_admin:false}};});
  await page.getByText("Administrator access is required.",{exact:true}).waitFor();
  assert.equal(await page.getByRole("button").count(),0);
  assert.equal(await page.evaluate(()=>calls.length),0);
});

async function liveFixture(t,width=1440){
  const page=await browser.newPage({viewport:{width,height:850}});t.after(()=>page.close());
  const errors=[];page.on("pageerror",e=>errors.push(e.message));t.after(()=>assert.deepEqual(errors,[]));
  await page.route("**/rotacloud_attendance/static/logo.png*",route=>route.fulfill({contentType:"image/png",path:path.join(__dirname,"../custom_components/rotacloud_attendance/frontend/logo.png")}));
  await page.setContent('<base href="http://fixture.local/"><body style="margin:0;background:#121212"></body>');
  await loadCard(page,"staff-live.js");
  await page.evaluate(()=>{
    const now=Math.floor(Date.now()/1000);window.states={};
    for(const status of ["present","here","break","leaving","due","late","gone"])states['sensor.count_'+status]={entity_id:'sensor.count_'+status,state:"1",attributes:{rotacloud_kind:"count",rotacloud_status:status,last_api_refresh:now}};
    for(const [name,status,deltaIn,deltaOut] of [["Alex","late",300,null],["Morgan","gone",-240,600],["Taylor","here",-60,null],["Casey","gone",120,-300]])states['sensor.'+name]={entity_id:'sensor.'+name,state:status,attributes:{rotacloud_kind:"staff",staff_name:name,scheduled_start:now-3600,scheduled_end:now+3600,clock_in:now-3600+deltaIn,clock_out:deltaOut===null?null:now+3600+deltaOut,clock_in_delta_seconds:deltaIn,clock_out_delta_seconds:deltaOut,completed_break_seconds:180,shift_duration_seconds:7200}};
    window.card=document.createElement("ff-staff-live");card.setConfig({});card.hass={states,config:{time_zone:"Europe/London"}};document.body.append(card);
  });return page;
}
test("live filter accepts one click across HA updates between pointer down and up",async t=>{
  const page=await liveFixture(t);const button=page.getByRole("button",{name:"Filter: Gone",exact:true});
  const box=await button.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
  await page.evaluate(()=>{window.buttonBefore=card.shadowRoot.querySelector('[data-filter="gone"]');for(let i=0;i<5;i++){states["sensor.count_present"].attributes.last_api_refresh++;card.hass={states};}});
  await page.mouse.up();assert.equal(await button.getAttribute("aria-pressed"),"true");
  assert.equal(await page.evaluate(()=>buttonBefore===card.shadowRoot.querySelector('[data-filter="gone"]')),true);
  assert.equal(await page.locator("tbody tr").count(),2);
  await page.getByRole("button",{name:"Filter: Clocked in",exact:true}).focus();await page.keyboard.press("Enter");
  assert.equal(await page.locator("tbody tr").count(),4);
});
test("live status/timing pills, colours, centred columns, icons and completion flags",async t=>{
  const page=await liveFixture(t);
  assert.equal(await page.locator(".pill.status").count(),4);assert.equal(await page.locator(".counts svg").count(),9);
  assert.equal(await page.getByRole("img",{name:"Shift completed",exact:true}).count(),2);
  const late=page.locator(".timing").filter({hasText:"5m late"}).first();assert.equal(await late.evaluate(n=>getComputedStyle(n).color),"rgb(239, 68, 68)");
  const early=page.locator(".timing").filter({hasText:"4m early"});assert.equal(await early.evaluate(n=>getComputedStyle(n).color),"rgb(234, 179, 8)");
  for(const column of [2,3,6,7])assert.equal(await page.locator(`tbody tr:first-child td:nth-child(${column})`).evaluate(n=>getComputedStyle(n).textAlign),"center");
  assert.equal(await page.locator(".finish").first().evaluate(n=>getComputedStyle(n).right),"12px");
  assert.equal(await page.locator("tbody tr:first-child td:first-child").evaluate(n=>getComputedStyle(n).color),"rgb(255, 255, 255)");
  await page.waitForFunction(()=>card.shadowRoot.querySelector('h2').textContent==='Dashboard');
  if(process.env.FF_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.FF_SCREENSHOT_DIR,"live-attendance-desktop.png"),fullPage:true});
});
test("live applies integration thresholds/colours independently and has mobile scrolling",async t=>{
  const page=await liveFixture(t,390);
  await page.evaluate(()=>{states["sensor.count_present"].attributes.display_options={clock_in_late:{minutes:5,color:[0,255,255]},clock_out_late:{minutes:0,color:[128,0,128]},clock_in_early:{minutes:3,color:[0,255,0]},clock_out_early:{minutes:6,color:[255,0,255]}};card.hass={states};});
  const pills=await page.locator(".timing").allTextContents();assert.deepEqual(pills.sort(),["10m late","4m early"].sort());
  assert.equal(await page.locator(".timing").filter({hasText:"10m late"}).evaluate(n=>getComputedStyle(n).color),"rgb(128, 0, 128)");
  assert.equal(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),true);
  assert.equal(await page.locator(".scroll").evaluate(n=>n.scrollWidth>n.clientWidth),true);
  if(process.env.FF_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.FF_SCREENSHOT_DIR,"live-attendance-mobile.png"),fullPage:true});
});

test("dashboard has no logo, has timestamp footer and only selected counters are coloured",async t=>{
 const page=await liveFixture(t);
 assert.equal(await page.getByRole('heading',{name:'Dashboard',exact:true}).count(),1);
 assert.equal(await page.locator('.logo').count(),0);
 assert.equal(await page.locator('tfoot').count(),1);
 assert.equal((await page.locator('tfoot').textContent()).includes('cached'),false);
 const neutral=await page.locator('[data-filter="here"] strong').evaluate(n=>getComputedStyle(n).color);
 assert.equal(neutral,'rgb(255, 255, 255)');
 assert.equal(await page.locator('[data-filter="here"] svg').evaluate(n=>getComputedStyle(n).color),'rgb(34, 197, 94)');
 await page.getByRole('button',{name:'Filter: Here',exact:true}).click();
 assert.equal(await page.locator('[data-filter="here"] strong').evaluate(n=>getComputedStyle(n).color),'rgb(34, 197, 94)');
 assert.equal(await page.locator('[data-filter="all"] strong').evaluate(n=>getComputedStyle(n).color),neutral);
});
test("manual refresh calls HA once per press and never refreshes on render",async t=>{
 const page=await liveFixture(t);
 await page.evaluate(()=>{window.refreshCalls=[];card.hass={...card._hass,user:{is_admin:true},callWS:async message=>{refreshCalls.push(message);await new Promise(r=>setTimeout(r,50));return {planning_available:true};}};for(const state of Object.values(states))state.attributes.config_entry_id='example-entry';card.render();card.render();});
 assert.equal(await page.evaluate(()=>refreshCalls.length),0);
 await page.evaluate(()=>{card.refresh();card.refresh();});
 await page.waitForFunction(()=>!card.refreshing);
 assert.deepEqual(await page.evaluate(()=>refreshCalls),[{type:'rotacloud_attendance/refresh',entry_id:'example-entry'}]);
});
test("leave/availability and previous-day attendance have separate tables and break warnings",async t=>{
 const page=await liveFixture(t);
 await page.evaluate(()=>{
  states['sensor.count_present'].attributes.day_start=Math.floor(Date.now()/1000)-7200;
  states['sensor.count_present'].attributes.planning_available=true;
  states['sensor.leave']={entity_id:'sensor.leave',state:'1',attributes:{rotacloud_kind:'count',rotacloud_status:'on_leave',rows:[{name:'Riley',times:['All Day']}]}};
  states['sensor.available']={entity_id:'sensor.available',state:'1',attributes:{rotacloud_kind:'count',rotacloud_status:'available',rows:[{name:'Jordan',times:['09:00 – 13:00','17:00 – 21:00']}]}};
  states['sensor.old']={entity_id:'sensor.old',state:'here',attributes:{rotacloud_kind:'staff',staff_name:'Previous Day',previous_day:true,clock_in:Math.floor(Date.now()/1000)-86400,completed_break_seconds:0}};
  states['sensor.Alex'].attributes.break_warning=true;
  states['sensor.Alex'].attributes.active_break_start=Math.floor(Date.now()/1000)-61;
  card.hass={...card._hass,states};
 });
 assert.equal(await page.locator('.primary tbody tr').count(),4);
 assert.equal(await page.locator('.previous tbody tr').count(),1);
 assert.equal(await page.getByRole('heading',{name:'Still Clocked In From Yesterday',exact:true}).count(),1);
 assert.equal(await page.locator('.planning tbody tr').count(),2);
 assert.equal(await page.getByRole('img',{name:'Break minimum not met',exact:true}).count(),1);
 assert.equal((await page.locator('.primary tbody tr').first().locator('td').nth(5).textContent()).includes('active'),false);
 await page.getByRole('button',{name:'Filter: On Leave',exact:true}).click();
 assert.equal(await page.locator('.planning tbody tr').count(),1);
 assert.match(await page.locator('.planning').textContent(),/Riley.*All Day/);
 await page.getByRole('button',{name:'Filter: Available',exact:true}).click();
 assert.match(await page.locator('.planning').textContent(),/Jordan.*09:00.*21:00/);
 await page.getByRole('button',{name:'Filter: Clocked in',exact:true}).click();
 if(process.env.FF_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.FF_SCREENSHOT_DIR,'dashboard-planning.png'),fullPage:true});
});
test("terminal supports focused physical keypad and separates break controls",async t=>{
 const page=await fixture(t);
 await page.evaluate(()=>{status='break';card.focus();});
 await page.keyboard.type('1234');
 await page.getByRole('heading',{name:'Hello, Alex'}).waitFor();
 assert.deepEqual(await page.locator('.stat small').allTextContents(),['Current Break','Total Break Time','Clocked In','Scheduled Finish']);
 assert.equal(await page.getByRole('button',{name:'END BREAK',exact:true}).locator('svg').count(),1);
 assert.equal(await page.locator('hr.divider').count(),1);
 assert.equal(await page.getByText('RotaCloud attendance',{exact:true}).count(),0);
 if(process.env.FF_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.FF_SCREENSHOT_DIR,'terminal-break-layout.png'),fullPage:true});
});

async function modularFixture(t,width=1440){
 const page=await liveFixture(t,width);
 await page.evaluate(()=>{
  card.remove();window.cards=[];
  for(const state of Object.values(states))state.attributes.config_entry_id='entry-a';
  states['sensor.count_present'].attributes.day_start=Math.floor(Date.now()/1000)-7200;
  states['sensor.count_present'].attributes.integration_name='Venue';
  states['sensor.count_present'].attributes.planning_available=true;
  for(const [kind,name,times]of [['on_leave','Riley',['All Day']],['available','Jordan',['09:00 – 13:00']]])states['sensor.'+kind]={entity_id:'sensor.'+kind,state:'1',attributes:{rotacloud_kind:'count',rotacloud_status:kind,config_entry_id:'entry-a',rows:[{name,times}]}};
  states['sensor.old']={entity_id:'sensor.old',state:'here',attributes:{rotacloud_kind:'staff',staff_name:'Yesterday',config_entry_id:'entry-a',previous_day:true,clock_in:Date.now()/1000-86400,completed_break_seconds:0}};
  window.wsCalls=[];window.hass={states,user:{id:'admin',is_admin:true},config:{time_zone:'Europe/London'},connection:{},callWS:async message=>{wsCalls.push(message);await new Promise(r=>setTimeout(r,20));return {planning_available:true};}};
  window.addCard=(type,config={},parent=document.body)=>{const c=document.createElement(type);c.setConfig(config);c.hass=hass;parent.append(c);cards.push(c);return c;};
 });return page;
}

test('card picker and visual editors cover every card without a PIN-length field',async t=>{
 const page=await modularFixture(t);await loadCard(page,'staff-terminal.js');
 const result=await page.evaluate(()=>{
  const kinds=['ff-staff-status','ff-staff-table','ff-staff-live','ff-staff-terminal'];
  return kinds.map(type=>{const constructor=customElements.get(type),stub=constructor.getStubConfig(hass),editor=constructor.getConfigElement();editor.setConfig({type:'custom:'+type,...stub});editor.hass=hass;document.body.append(editor);return {type,stub,fields:[...editor.shadowRoot.querySelectorAll('input,select')].map(x=>x.getAttribute('aria-label')),registered:window.customCards.some(c=>c.type===type)};});
 });
 assert.ok(result.every(x=>x.registered&&x.stub.entry_id==='entry-a'));
 assert.ok(result[0].fields.includes('Click behaviour'));
 assert.ok(result[1].fields.includes('Visible columns')===false);
 assert.ok(result[1].fields.includes('Clock-in'));
 assert.ok(result[3].fields.includes('Layout'));
 assert.ok(!result[3].fields.some(x=>/pin/i.test(x)));
 // A real editor change emits the full configuration, preserving unknown/legacy fields.
 await page.evaluate(()=>{const e=document.querySelector('ff-rotacloud-editor');e.setConfig({type:'custom:ff-staff-status',status:'here',group:'team',custom_option:7});e.addEventListener('config-changed',event=>window.edited=event.detail.config);});
 await page.getByRole('textbox',{name:'Title',exact:true}).first().fill('Working now');
 await page.getByRole('textbox',{name:'Title',exact:true}).first().blur();
 assert.deepEqual(await page.evaluate(()=>edited),{type:'custom:ff-staff-status',status:'here',group:'team',custom_option:7,title:'Working now'});
});

test('separate status cards filter only their linked view, group and integration',async t=>{
 const page=await modularFixture(t);
 await page.evaluate(()=>{
  const view=document.createElement('hui-view');document.body.append(view);window.statusCard=addCard('ff-staff-status',{status:'gone',group:'team'},view);window.table=addCard('ff-staff-table',{group:'team'},view);window.independent=addCard('ff-staff-table',{group:'other'},view);
  const second=document.createElement('hui-view');document.body.append(second);window.second=addCard('ff-staff-table',{group:'team'},second);
  window.otherEntry=addCard('ff-staff-table',{entry_id:'entry-b',group:'team'},view);
 });
 const status=page.locator('ff-staff-status');await status.getByRole('button',{name:'Gone',exact:true}).click();
 assert.equal(await page.evaluate(()=>table.shadowRoot.querySelectorAll('tbody tr').length),2);
 assert.equal(await page.evaluate(()=>independent.shadowRoot.querySelectorAll('tbody tr').length),4);
 assert.equal(await page.evaluate(()=>second.shadowRoot.querySelectorAll('tbody tr').length),4);
 assert.equal(await page.evaluate(()=>otherEntry.group.filter),null);
 await status.getByRole('button',{name:'Gone',exact:true}).click();
 assert.equal(await page.evaluate(()=>table.shadowRoot.querySelectorAll('tbody tr').length),4);
 assert.equal(await page.evaluate(()=>wsCalls.length),0);
});

test('table variants retain styling, select columns, sort, hide empty and label refresh',async t=>{
 const page=await modularFixture(t);
 await page.evaluate(()=>{
  window.table=addCard('ff-staff-table',{columns:['staff','clock_in','status'],sort_by:'staff',sort_direction:'desc',use_group:false,title:'Team'});
  window.leave=addCard('ff-staff-table',{table_type:'leave'});window.available=addCard('ff-staff-table',{table_type:'availability'});window.yesterday=addCard('ff-staff-table',{table_type:'yesterday'});
 });
 const table=page.locator('ff-staff-table').nth(0);
 assert.deepEqual(await table.locator('th').allTextContents(),['Staff','Clock-in','Status']);
 assert.equal(await table.locator('tbody tr').first().locator('td').first().textContent(),'Taylor');
 assert.match(await table.locator('tfoot').textContent(),/^Last API refresh: /);
 assert.equal(await table.locator('.pill.status').count(),4);
 assert.match(await page.locator('ff-staff-table').nth(1).locator('tbody').textContent(),/Riley.*All Day/);
 assert.match(await page.locator('ff-staff-table').nth(2).locator('tbody').textContent(),/Jordan.*09:00/);
 assert.match(await page.locator('ff-staff-table').nth(3).locator('tbody').textContent(),/Yesterday/);
 await page.evaluate(()=>{delete states['sensor.old'];for(const c of cards)c.hass={...hass,states};});
 assert.equal(await page.evaluate(()=>yesterday.hidden),true);assert.equal(await page.locator('ff-staff-table').nth(3).isVisible(),false);
 await page.evaluate(()=>table.setConfig({show_timestamp:false,show_refresh:false,filter:'here',use_group:false}));
 assert.equal(await table.locator('tfoot').count(),0);assert.equal(await table.getByRole('button',{name:'Refresh',exact:true}).count(),0);
 assert.equal(await table.locator('tbody tr').count(),1);
});

test('cards share refresh and a single local timer and release it on removal',async t=>{
 const page=await modularFixture(t);await loadCard(page,'staff-terminal.js');
 await page.evaluate(()=>{window.intervalStarts=0;window.intervalEnds=0;const start=window.setInterval.bind(window),end=window.clearInterval.bind(window);window.setInterval=(...args)=>{intervalStarts++;window.tick=args[0];return start(...args);};window.clearInterval=id=>{intervalEnds++;end(id);};
  window.a=addCard('ff-staff-table');window.b=addCard('ff-staff-table',{table_type:'leave'});window.terminal=addCard('ff-staff-terminal');for(let i=0;i<9;i++)addCard('ff-staff-status',{status:'here'});
 });
 assert.equal(await page.evaluate(()=>intervalStarts),1);
 await page.evaluate(()=>{tick();for(let i=0;i<10;i++){const value={...hass,states:{...states,'sensor.unrelated':{entity_id:'sensor.unrelated',state:String(i),attributes:{}}}};for(const c of cards)c.hass=value;}});
 assert.equal(await page.evaluate(()=>wsCalls.length),0);
 await page.evaluate(()=>{a.refresh();b.refresh();});await page.waitForFunction(()=>!a.refreshing&&!b.refreshing);
 assert.equal(await page.evaluate(()=>wsCalls.length),1);
 await page.evaluate(()=>{for(const c of cards)c.remove();});
 assert.equal(await page.evaluate(()=>intervalEnds),1);
});

test('terminal editor options preserve PIN clocking and automatic integration selection',async t=>{
 const page=await fixture(t);await page.evaluate(()=>{card.setConfig({title:'Clocking',subtitle:'Formula Fast',layout:'compact'});card.hass={...card._hass,states:{'sensor.present':{entity_id:'sensor.present',state:'1',attributes:{rotacloud_kind:'count',rotacloud_status:'present',config_entry_id:'automatic-entry'}}}};});
 assert.equal(await page.getByRole('heading',{name:'Clocking',exact:true}).count(),1);
 await pin(page);await page.getByRole('heading',{name:'Hello, Alex'}).waitFor();
 assert.equal(await page.evaluate(()=>calls[0].entry_id),'automatic-entry');
});

test('preview filters are isolated and integration selection never mixes staff',async t=>{
 const page=await modularFixture(t);
 await page.evaluate(()=>{
  window.table=addCard('ff-staff-table',{group:'same'});
  const preview=document.createElement('hui-card-preview');document.body.append(preview);window.previewStatus=addCard('ff-staff-status',{status:'gone',group:'same'},preview);
  const now=Date.now()/1000;states['sensor.other_count']={entity_id:'sensor.other_count',state:'1',attributes:{rotacloud_kind:'count',rotacloud_status:'present',config_entry_id:'entry-b',last_api_refresh:now}};
  states['sensor.other_staff']={entity_id:'sensor.other_staff',state:'here',attributes:{rotacloud_kind:'staff',staff_name:'Other venue',config_entry_id:'entry-b'}};
  window.hass={...hass,states};window.other=addCard('ff-staff-table',{entry_id:'entry-b'});
  window.explicit=addCard('ff-staff-table',{entry_id:'entry-a'});
  // Automatic selection must require a choice when more than one integration exists.
  window.ambiguous=addCard('ff-staff-table');
 });
 await page.locator('ff-staff-status').getByRole('button',{name:'Gone',exact:true}).click();
 assert.equal(await page.evaluate(()=>table.shadowRoot.querySelectorAll('tbody tr').length),4);
 assert.match(await page.evaluate(()=>other.shadowRoot.querySelector('tbody').textContent),/^Other venueHere/);
 assert.equal(await page.evaluate(()=>explicit.shadowRoot.querySelectorAll('tbody tr').length),4);
 assert.match(await page.evaluate(()=>ambiguous.shadowRoot.textContent),/Attendance unavailable/);
});

test('reconnecting a card restores its current filter subscription without leaking timers',async t=>{
 const page=await modularFixture(t);
 await page.evaluate(()=>{window.table=addCard('ff-staff-table');window.status=addCard('ff-staff-status',{status:'gone'});table.remove();document.body.append(table);});
 await page.locator('ff-staff-status').getByRole('button',{name:'Gone',exact:true}).click();
 assert.equal(await page.evaluate(()=>table.shadowRoot.querySelectorAll('tbody tr').length),2);
});

test('compact card layout scrolls tables on mobile and keeps status buttons stable',async t=>{
 const page=await modularFixture(t,390);
 await page.evaluate(()=>{document.body.style.color='white';window.table=addCard('ff-staff-table');window.counter=addCard('ff-staff-status',{status:'gone',title:'Finished',color:'#00cccc',icon:'mdi:flag-checkered'});});
 const button=page.locator('ff-staff-status').getByRole('button',{name:'Finished',exact:true}),box=await button.boundingBox();
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
 await page.evaluate(()=>{states['sensor.count_gone'].state='2';counter.hass={...hass,states};});await page.mouse.up();
 assert.equal(await button.getAttribute('aria-pressed'),'true');
 assert.equal(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),true);
 assert.equal(await button.locator('ha-icon').getAttribute('icon'),'mdi:flag-checkered');
 assert.equal(await page.locator('ff-staff-table').locator('tbody tr').count(),2);
 if(process.env.FF_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.FF_SCREENSHOT_DIR,'modular-mobile.png'),fullPage:true});
});

test('Sections grid sizes, resizing widths and shared filters work together',async t=>{
 const page=await modularFixture(t,1100);await loadCard(page,'staff-terminal.js');
 const sizes=await page.evaluate(()=>{
  document.body.style.color='white';const section=document.createElement('hui-view');section.style.cssText='display:grid;grid-template-columns:repeat(12,minmax(0,1fr));grid-auto-rows:minmax(56px,auto);gap:8px;width:100%;max-width:1000px;margin:auto';document.body.append(section);
  for(const status of ['here','break','due','gone']){const c=addCard('ff-staff-status',{status},section);c.style.cssText='grid-column:span 3;grid-row:span 2';}
  window.sectionTable=addCard('ff-staff-table',{},section);sectionTable.style.gridColumn='span 12';window.sectionTerminal=addCard('ff-staff-terminal',{layout:'compact'},section);sectionTerminal.style.gridColumn='span 6';
  return [cards[0].getGridOptions(),sectionTable.getGridOptions(),sectionTerminal.getGridOptions()];
 });
 assert.equal(sizes[0].columns,3);assert.equal(sizes[0].rows,2);
 assert.equal(sizes[1].columns,12);assert.equal(sizes[1].rows,'auto');
 assert.equal(sizes[2].columns,12);
 await page.locator('ff-staff-status').last().getByRole('button',{name:'Gone',exact:true}).click();
 assert.equal(await page.evaluate(()=>sectionTable.shadowRoot.querySelectorAll('tbody tr').length),2);
 assert.equal(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),true);
 await page.evaluate(()=>sectionTable.style.gridColumn='span 6');
 assert.equal(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),true);
 if(process.env.FF_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.FF_SCREENSHOT_DIR,'modular-sections.png'),fullPage:true});
});

test('Status click behaviours preserve grouping and use safe HA navigation/details events',async t=>{
 const page=await modularFixture(t);
 await page.evaluate(()=>{window.actionCard=addCard('ff-staff-status',{status:'here',tap_action:'more-info'});actionCard.addEventListener('hass-more-info',e=>window.detail=e.detail);});
 await page.locator('ff-staff-status').getByRole('button',{name:'Here',exact:true}).click();
 assert.deepEqual(await page.evaluate(()=>detail),{entityId:'sensor.count_here'});
 await page.evaluate(()=>actionCard.setConfig({status:'here',tap_action:'none'}));
 await page.locator('ff-staff-status').getByRole('button',{name:'Here',exact:true}).click();assert.equal(await page.evaluate(()=>actionCard.group.filter),null);
 await page.evaluate(()=>{actionCard.setConfig({status:'here',tap_action:'navigate',navigation_path:'/staff/terminal'});window.navigation=0;addEventListener('location-changed',()=>navigation++);actionCard.tapStatus();});
 assert.equal(await page.evaluate(()=>location.pathname),'/staff/terminal');assert.equal(await page.evaluate(()=>navigation),1);
 await page.evaluate(()=>{actionCard.setConfig({status:'here',tap_action:'navigate',navigation_path:'//external.example'});actionCard.tapStatus();});
 assert.equal(await page.evaluate(()=>navigation),1);
});
