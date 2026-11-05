// Optional browser integration test. Run with tests/run_ui_smoke.py against its isolated DB.
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.UI_TEST_BASE;
const password = process.env.UI_TEST_PASSWORD;
if (!base || !password) throw new Error('Use tests/run_ui_smoke.py to create an isolated test environment.');
const artifacts = process.env.UI_TEST_ARTIFACTS;
await mkdir(artifacts, {recursive:true});
const browser = await chromium.launch({headless:true, ...(process.env.BROWSER_EXECUTABLE ? {executablePath:process.env.BROWSER_EXECUTABLE} : {})});
const errors = [];
const waitText = async (locator, expected) => {
  await locator.filter({hasText:expected}).waitFor();
  assert.ok((await locator.innerText()).includes(expected));
};
try {
  const contextA = await browser.newContext({viewport:{width:1440,height:1100}});
  const contextB = await browser.newContext({viewport:{width:1280,height:1000}});
  const a = await contextA.newPage(), b = await contextB.newPage();
  for (const page of [a,b]) page.on('pageerror', error=>errors.push(error.message));
  await a.goto(base);
  await a.locator('#login-screen').waitFor();
  await a.screenshot({path:`${artifacts}/login.png`,fullPage:true});
  await a.getByLabel('로그인 ID', {exact:true}).fill('demo-room-a');
  await a.getByLabel('비밀번호', {exact:true}).fill('intentionally-incorrect');
  await a.getByRole('button',{name:'동아리방 들어가기'}).click();
  await waitText(a.locator('#login-error'),'로그인 정보가 올바르지 않습니다');
  await a.getByLabel('비밀번호', {exact:true}).fill(password);
  await a.getByRole('button',{name:'동아리방 들어가기'}).click();
  await a.locator('#app').waitFor();
  await waitText(a.locator('#connection'),'실시간 연결');
  await waitText(a.locator('#nickname'),'데모 다람쥐');
  await b.goto(base);
  await b.getByLabel('로그인 ID', {exact:true}).fill('demo-room-b');
  await b.getByLabel('비밀번호', {exact:true}).fill(password);
  await b.getByRole('button',{name:'동아리방 들어가기'}).click();
  await b.locator('#app').waitFor();
  await waitText(b.locator('#connection'),'실시간 연결');

  await a.locator('#presence-button').click();
  await waitText(a.locator('#presence-label'),'지금 동아리방에 있어요');
  await waitText(b.locator('#occupancy'),'1');
  const firstTable = a.locator('.table-item').first();
  await firstTable.getByRole('button',{name:'이용 시작'}).click();
  await waitText(a.locator('#my-table'),'테이블 1 이용 중');
  await b.locator('#refresh').click();
  await waitText(b.locator('.table-item').first(),'1 / 4명');
  assert.equal(await a.locator('#occupancy').innerText(),'1');

  const message = '같이 만들어요! <img src=x onerror=alert(1)>';
  await a.locator('#chat-input').fill(message);
  await a.getByRole('button',{name:'메시지 보내기'}).click();
  await waitText(b.locator('#messages'),message);
  assert.equal(await b.locator('#messages img').count(),0);
  assert.equal(await b.locator('.message-content').filter({hasText:message}).count(),1);

  const day = new Date(Date.now()+2*86400000).toISOString().slice(0,10);
  async function create(title) {
    await a.locator('#new-schedule').click();
    await a.locator('#schedule-title').fill(title);
    await a.locator('#schedule-start').fill(`${day}T10:00`);
    await a.locator('#schedule-end').fill(`${day}T11:00`);
    await a.locator('#schedule-description').fill('브라우저 연결 테스트 모임');
    await a.getByRole('button',{name:'일정 저장하기'}).click();
  }
  await create('프론트 연결 모임');
  await a.locator('#schedule-dialog').waitFor({state:'hidden'});
  await b.getByRole('heading',{name:'프론트 연결 모임',exact:true}).waitFor();
  await create('겹침 확인 모임');
  await a.locator('#overlap-warning').waitFor();
  await a.locator('#confirm-overlap').check();
  await a.getByRole('button',{name:'일정 저장하기'}).click();
  await a.locator('#schedule-dialog').waitFor({state:'hidden'});
  const overlap = a.locator('.schedule-item').filter({has:a.getByRole('heading',{name:'겹침 확인 모임',exact:true})});
  await overlap.getByRole('button',{name:'취소',exact:true}).click();
  await a.getByRole('button',{name:'일정 취소하기',exact:true}).click();
  await a.locator('#confirm-dialog').waitFor({state:'hidden'});
  await waitText(overlap,'취소됨');
  let cardA = a.locator('.schedule-item').filter({has:a.getByRole('heading',{name:'프론트 연결 모임',exact:true})});
  await cardA.getByRole('button',{name:'수정',exact:true}).click();
  await a.locator('#schedule-title').fill('함께 만드는 KOSS');
  await a.getByRole('button',{name:'일정 저장하기'}).click();
  await a.locator('#schedule-dialog').waitFor({state:'hidden'});
  cardA = a.locator('.schedule-item').filter({has:a.getByRole('heading',{name:'함께 만드는 KOSS',exact:true})});
  await cardA.getByRole('button',{name:'모집 설정',exact:true}).click();
  await a.locator('#recruit-disabled').uncheck();
  await a.locator('#recruit-capacity').fill('2');
  await a.getByRole('button',{name:'모집 설정 저장',exact:true}).click();
  await a.locator('#recruit-dialog').waitFor({state:'hidden'});
  await cardA.getByRole('button',{name:'참여하기',exact:true}).click();
  await waitText(cardA,'참여 1 / 2명');
  const cardB = b.locator('.schedule-item').filter({has:b.getByRole('heading',{name:'함께 만드는 KOSS',exact:true})});
  await cardB.getByRole('button',{name:'참여하기',exact:true}).click();
  await waitText(cardA,'참여 2 / 2명');
  await cardA.getByRole('button',{name:'모집 설정',exact:true}).click();
  await a.locator('#recruit-capacity').fill('1');
  await a.getByRole('button',{name:'모집 설정 저장',exact:true}).click();
  await waitText(a.locator('#recruit-error'),'정원은 현재 참여 인원보다 작을 수 없습니다');
  await a.locator('#recruit-dialog').getByRole('button',{name:'닫기',exact:true}).click();
  await cardB.getByRole('button',{name:'참여 취소',exact:true}).click();
  await waitText(cardA,'참여 1 / 2명');
  assert.equal(await cardB.getByRole('button',{name:'수정',exact:true}).count(),0);

  await a.evaluate(() => window.scrollTo(0,0));
  await a.screenshot({path:`${artifacts}/dashboard.png`,fullPage:true});
  await a.setViewportSize({width:390,height:844});
  await a.screenshot({path:`${artifacts}/mobile.png`,fullPage:true});
  assert.equal(await a.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false,'No mobile horizontal overflow');
  await a.locator('#new-schedule').click();
  await a.screenshot({path:`${artifacts}/mobile-dialog.png`,fullPage:true});
  await a.locator('#schedule-dialog').getByRole('button',{name:'닫기',exact:true}).click();
  await a.setViewportSize({width:1440,height:1100});

  await firstTable.getByRole('button',{name:'이용 종료',exact:true}).click();
  await waitText(a.locator('#my-table'),'테이블을 골라');
  await a.locator('#presence-button').click();
  await waitText(b.locator('#occupancy'),'0');
  await a.locator('#logout').click();
  await a.locator('#login-screen').waitFor();
  // Same cookie now cannot call protected API; do not inspect cookie contents.
  assert.equal((await a.request.get(`${base}/api/auth/me/`)).status(),401);
  await a.reload();
  await a.locator('#login-screen').waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS: login/CSRF, 2-user realtime attendance/chat/schedules, XSS text rendering, tables, schedule CRUD/overlap, recruitment/capacity, logout, mobile layout.');
  console.log(`Screenshots: ${artifacts}`);
} finally { await browser.close(); }
