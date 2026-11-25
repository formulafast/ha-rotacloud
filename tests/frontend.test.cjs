const {test, before, after} = require("node:test");
const assert = require("node:assert/strict");
const {chromium} = require("playwright");
const path = require("node:path");
let browser;
before(async () => { browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH || undefined}); });
after(async () => { await browser?.close(); });

async function fixture(t, width=1024) {
  const page=await browser.newPage({viewport:{width,height:900}});
  t.after(()=>page.close());
  const errors=[]; page.on("pageerror", e=>errors.push(e.message));
  t.after(()=>assert.deepEqual(errors,[]));
  await page.setContent('<body style="margin:0;background:#252525"></body>');
  await page.addScriptTag({path:path.join(__dirname,"../custom_components/rotacloud_attendance/frontend/staff-terminal.js")});
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
    if(button === "START BREAK") assert.equal(await page.locator(".stat").filter({hasText:"Breaks today"}).locator("strong").textContent(),"0h 13m");
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
  await page.addScriptTag({path:path.join(__dirname,"../custom_components/rotacloud_attendance/frontend/staff-live.js")});
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
  assert.equal(await page.locator(".pill.status").count(),4);assert.equal(await page.locator(".counts svg").count(),7);
  assert.equal(await page.getByRole("img",{name:"Shift completed",exact:true}).count(),2);
  const late=page.locator(".timing").filter({hasText:"5m late"}).first();assert.equal(await late.evaluate(n=>getComputedStyle(n).backgroundColor),"rgb(239, 68, 68)");
  const early=page.locator(".timing").filter({hasText:"4m early"});assert.equal(await early.evaluate(n=>getComputedStyle(n).backgroundColor),"rgb(234, 179, 8)");
  for(const column of [2,3,6,7])assert.equal(await page.locator(`tbody tr:first-child td:nth-child(${column})`).evaluate(n=>getComputedStyle(n).textAlign),"center");
  assert.equal(await page.locator(".finish").first().evaluate(n=>getComputedStyle(n).right),"12px");
  assert.equal(await page.locator("tbody tr:first-child td:first-child").evaluate(n=>getComputedStyle(n).color),"rgb(255, 255, 255)");
  await page.waitForFunction(()=>card.shadowRoot.querySelector('.logo').naturalWidth>0);
  if(process.env.FF_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.FF_SCREENSHOT_DIR,"live-attendance-desktop.png"),fullPage:true});
});
test("live applies integration thresholds/colours independently and has mobile scrolling",async t=>{
  const page=await liveFixture(t,390);
  await page.evaluate(()=>{states["sensor.count_present"].attributes.display_options={clock_in_late:{minutes:5,color:[0,255,255]},clock_out_late:{minutes:0,color:[128,0,128]},clock_in_early:{minutes:3,color:[0,255,0]},clock_out_early:{minutes:6,color:[255,0,255]}};card.hass={states};});
  const pills=await page.locator(".timing").allTextContents();assert.deepEqual(pills.sort(),["10m late","4m early"].sort());
  assert.equal(await page.locator(".timing").filter({hasText:"10m late"}).evaluate(n=>getComputedStyle(n).backgroundColor),"rgb(128, 0, 128)");
  assert.equal(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),true);
  assert.equal(await page.locator(".scroll").evaluate(n=>n.scrollWidth>n.clientWidth),true);
  if(process.env.FF_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.FF_SCREENSHOT_DIR,"live-attendance-mobile.png"),fullPage:true});
});
