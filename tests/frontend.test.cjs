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
          clock_in:now-3600,scheduled_end:now+3600,break_seconds:600,active_break_start:now-60,
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
