'use strict';
const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const kstParts = (date = new Date()) => Object.fromEntries(new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(date)).map(p => [p.type,p.value]));
const kstDate = (date) => { const p = kstParts(date); return `${p.year}-${p.month}-${p.day}`; };
const kstInput = (date) => { const p = kstParts(date); return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`; };
const clockTime = (date) => new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(date));
const dateTime = (date) => new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(date));
let user = null, csrfToken = '', sessionEpoch = 0, refreshVersion = 0, chatVersion = 0;
let attendance = null, tables = [], schedules = [], messages = new Map(), chatCursor = null, olderCursor = null;
let socket = null, reconnectTimer, pollingTimer, heartbeatTimer, refreshTimer, toastTimer, reconnectAttempts = 0;
let pendingMessage = null, cancelId = null;

function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 4500); }
async function refreshCsrf() {
  const response = await fetch('/api/csrf/', {credentials:'same-origin', cache:'no-store'});
  if (!response.ok) throw new Error('서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.');
  csrfToken = (await response.json()).csrf_token;
}
async function api(path, method = 'GET', body, retryCsrf = true) {
  const epoch = sessionEpoch;
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') { if (!csrfToken) await refreshCsrf(); headers['X-CSRFToken'] = csrfToken; }
  let response;
  try { response = await fetch(path, {method, headers, credentials:'same-origin', cache:'no-store', body:body === undefined ? undefined : JSON.stringify(body)}); }
  catch { throw new Error('연결이 끊겼어요. 저장 요청이었다면 목록에서 반영 여부를 확인해 주세요.'); }
  let data;
  try { data = await response.json(); } catch { throw new Error('서버 응답을 읽을 수 없어요. 서버 실행 상태를 확인해 주세요.'); }
  if (!response.ok) {
    if (response.status === 403 && data.error?.code === 'csrf_failed' && retryCsrf && epoch === sessionEpoch) {
      await refreshCsrf();
      return api(path, method, body, false); // A CSRF rejection has not executed the write.
    }
    if (response.status === 401 && user && epoch === sessionEpoch) showLogin('로그인이 만료됐어요. 다시 로그인해 주세요.');
    const error = new Error(data.error?.message || '요청을 처리하지 못했어요.');
    error.code = data.error?.code; error.details = data.error?.details; error.status = response.status;
    throw error;
  }
  return data;
}
async function busy(button, action, errorTarget) {
  if (button.disabled) return;
  button.disabled = true;
  if (errorTarget) errorTarget.textContent = '';
  try { await action(); }
  catch (error) { if (errorTarget) errorTarget.textContent = error.message; else toast(error.message); }
  finally { button.disabled = false; }
}
function stopRealtime() {
  clearTimeout(reconnectTimer); clearTimeout(refreshTimer); clearInterval(pollingTimer); clearInterval(heartbeatTimer);
  const previous = socket; socket = null;
  if (previous) { previous.onclose = null; previous.close(); }
}
function showLogin(message = '') {
  stopRealtime(); sessionEpoch++; refreshVersion++; chatVersion++; user = null;
  attendance = null; tables = []; schedules = []; messages.clear(); pendingMessage = null;
  document.querySelectorAll('dialog[open]').forEach(d => d.close());
  $('boot').hidden = true; $('app').hidden = true; $('login-screen').hidden = false;
  $('password').value = ''; $('login-error').textContent = message;
}
async function showApp(currentUser) {
  stopRealtime(); sessionEpoch++; user = currentUser; reconnectAttempts = 0;
  $('boot').hidden = true; $('login-screen').hidden = true; $('app').hidden = false;
  $('nickname').textContent = user.nickname; $('avatar').textContent = Array.from(user.nickname)[0] || 'K';
  $('password').value = ''; $('page-error').hidden = true;
  resetChat(); await refreshAll();
  if (!user) return;
  connectSocket();
  pollingTimer = setInterval(() => { if (!document.hidden) refreshAll(); }, 30000);
}
function connectionLabel(label, live = false) { $('connection').textContent = label; $('connection').classList.toggle('live', live); }
function connectSocket() {
  if (!user) return;
  const epoch = sessionEpoch;
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/room/`);
  socket = ws; connectionLabel('연결 중');
  ws.onopen = () => {
    if (epoch !== sessionEpoch) { ws.close(); return; }
    reconnectAttempts = 0; connectionLabel('실시간 연결', true); refreshAll();
    clearInterval(heartbeatTimer);
    heartbeatTimer = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type:'ping'})); }, 25000);
  };
  ws.onmessage = (event) => {
    if (epoch !== sessionEpoch || !user) return;
    let message; try { message = JSON.parse(event.data); } catch { return; }
    if (message.type === 'chat.message') { addMessages([message.data.message]); renderMessages(); }
    if (['attendance.updated','schedule.changed','connected'].includes(message.type)) {
      clearTimeout(refreshTimer); refreshTimer = setTimeout(() => refreshAll(), 150);
    }
  };
  ws.onclose = async (event) => {
    clearInterval(heartbeatTimer);
    if (epoch !== sessionEpoch || !user) return;
    connectionLabel('재연결 대기');
    if (event.code === 4401) { showLogin('로그인이 만료됐어요. 다시 로그인해 주세요.'); return; }
    try { await api('/api/auth/me/'); } catch { /* API handles session expiry; polling continues if offline. */ }
    if (epoch === sessionEpoch && user) reconnectTimer = setTimeout(connectSocket, Math.min(30000, 1500 * 2 ** reconnectAttempts++));
  };
}
function renderPresence() {
  if (!attendance) return;
  $('occupancy').textContent = attendance.current_count;
  $('presence-label').textContent = attendance.is_inside ? '지금 동아리방에 있어요' : '아직 입실하지 않았어요';
  $('presence-detail').textContent = attendance.active_visit ? `${clockTime(attendance.active_visit.entered_at)} 입실 · 나갈 때 퇴실 버튼을 눌러주세요.` : '도착하면 입실 버튼으로 알려주세요.';
  $('presence-button').textContent = attendance.is_inside ? '퇴실하기 ↗' : '입실하기 ↗';
  $('presence-button').disabled = false;
}
function renderTables() {
  const mine = tables.find(t => t.is_using);
  $('free-seats').textContent = tables.reduce((sum,t) => sum + Math.max(0,t.capacity-t.current_count),0);
  $('my-table').textContent = mine ? `${mine.name} 이용 중` : '테이블을 골라 자리를 잡아보세요.';
  $('table-list').innerHTML = tables.length ? tables.map((t,i) => `<article class="table-item ${t.is_using ? 'mine' : ''}"><strong>${escapeHtml(t.name)}</strong><div class="table-visual" aria-hidden="true"><div class="table-top">${String(i+1).padStart(2,'0')}</div>${Array.from({length:4},(_,n)=>`<i class="seat ${n < Math.ceil(t.current_count/t.capacity*4) ? 'occupied' : ''}"></i>`).join('')}</div><small>${t.current_count} / ${t.capacity}명 이용 중</small><button class="button ${t.is_using ? 'primary' : 'secondary'}" data-table="${t.id}" ${!t.is_using && (mine || t.current_count >= t.capacity) ? 'disabled' : ''}>${t.is_using ? '이용 종료' : t.current_count >= t.capacity ? '자리 없음' : mine ? '이동 전 종료' : '이용 시작'}</button></article>`).join('') : '<p class="empty">등록된 테이블이 없어요.</p>';
}
async function fetchSchedules() {
  const start = new Date(`${$('range-start').value}T00:00:00+09:00`);
  const end = new Date(new Date(`${$('range-end').value}T00:00:00+09:00`).getTime() + 86400000);
  if (!Number.isFinite(+start) || !Number.isFinite(+end) || start >= end) throw new Error('올바른 조회 시작일과 종료일을 선택하세요.');
  const query = new URLSearchParams({start:start.toISOString(),end:end.toISOString(),limit:'100'});
  const result = []; let offset = 0;
  do {
    query.set('offset', String(offset));
    const data = await api(`/api/schedules/?${query}`); result.push(...data.schedules); offset = data.next_offset;
  } while (offset !== null);
  return result;
}
function renderSchedules() {
  const now = Date.now();
  $('upcoming-count').textContent = schedules.filter(s => !s.is_cancelled && +new Date(s.ends_at) > now).length;
  $('schedule-list').innerHTML = schedules.length ? schedules.map(s => {
    const p = kstParts(s.starts_at), own = s.author.id === user.id, closed = s.is_cancelled || +new Date(s.ends_at) <= now;
    const r = s.recruitment, unavailable = !r.is_participating && (closed || r.capacity === null || r.participant_count >= r.capacity);
    const status = s.is_cancelled ? '취소됨' : closed ? '종료됨' : s.category;
    return `<article class="schedule-item ${s.is_cancelled ? 'cancelled' : ''}" data-schedule-card="${s.id}"><div class="schedule-top"><div class="date-tile"><small>${Number(p.month)}월</small><strong>${p.day}</strong></div><div class="schedule-info"><h3>${escapeHtml(s.title)}</h3><div class="meta">${escapeHtml(dateTime(s.starts_at))} – ${escapeHtml(dateTime(s.ends_at))}<br>${escapeHtml(s.author.nickname)} · ${escapeHtml(status)}</div>${s.description ? `<p class="description">${escapeHtml(s.description)}</p>` : ''}</div></div><div class="schedule-bottom"><span class="recruitment-label">${r.capacity === null ? '모집 미설정' : `참여 ${r.participant_count} / ${r.capacity}명`}${r.is_participating ? ' · 참여 중' : ''}</span><div class="schedule-actions">${own && !s.is_cancelled ? `<button class="text-button" data-schedule-action="edit" data-id="${s.id}">수정</button>${!closed ? `<button class="text-button" data-schedule-action="recruit" data-id="${s.id}">모집 설정</button>` : ''}<button class="text-button" data-schedule-action="cancel" data-id="${s.id}">취소</button>` : ''}<button class="button ${r.is_participating ? 'secondary' : 'primary'} small" data-schedule-action="join" data-id="${s.id}" ${unavailable ? 'disabled' : ''}>${r.is_participating ? '참여 취소' : closed ? '마감' : r.capacity === null ? '모집 전' : r.participant_count >= r.capacity ? '정원 마감' : '참여하기'}</button></div></div></article>`;
  }).join('') : '<p class="empty">이 기간에는 아직 일정이 없어요.<br>첫 모임을 만들어볼까요?</p>';
}
function renderAnalytics(data) {
  $('peak').textContent = `오늘 최대 ${data.peak_count ?? 0}명`;
  const max = Math.max(1, ...data.hourly.map(h => h.average_count || 0));
  $('hourly-chart').innerHTML = data.hourly.map(h => `<div class="chart-bar ${h.average_count === null ? 'future' : ''}" style="height:${h.average_count === null ? 5 : Math.max(3,h.average_count/max*100)}%" title="${h.hour}시 · ${h.average_count === null ? '아직 관측하지 않음' : `평균 ${h.average_count}명 / 최대 ${h.peak_count}명`}"></div>`).join('');
}
async function refreshAll() {
  if (!user) return;
  const epoch = sessionEpoch, version = ++refreshVersion;
  const results = await Promise.allSettled([api('/api/attendance/me/'),api('/api/tables/'),fetchSchedules(),api('/api/analytics/daily/'),syncChat()]);
  if (epoch !== sessionEpoch || version !== refreshVersion || !user) return;
  if (results[0].status === 'fulfilled') { attendance = results[0].value; renderPresence(); }
  if (results[1].status === 'fulfilled') { tables = results[1].value.tables; renderTables(); }
  if (results[2].status === 'fulfilled') { schedules = results[2].value; renderSchedules(); }
  if (results[3].status === 'fulfilled') renderAnalytics(results[3].value);
  const failures = results.filter(r => r.status === 'rejected');
  $('page-error').hidden = !failures.length;
  $('page-error').textContent = failures.length ? failures[0].reason.message : '';
}
function resetChat() { chatVersion++; messages = new Map(); chatCursor = null; olderCursor = null; renderMessages(); }
function addMessages(rows) { for (const row of rows) { if (kstDate(row.created_at) === $('chat-date').value) messages.set(row.id,row); } }
function renderMessages(forceBottom = false) {
  const box = $('messages'), nearBottom = box.scrollHeight-box.clientHeight-box.scrollTop < 70;
  const rows = [...messages.values()].sort((a,b) => a.id-b.id);
  box.innerHTML = rows.length ? rows.map(m => {
    const mine = m.user_id === user?.id;
    return `<div class="message ${mine ? 'mine' : ''}">${mine ? '' : `<span class="message-avatar">${escapeHtml(Array.from(m.nickname)[0] || 'K')}</span>`}<div class="message-body"><p class="message-name">${escapeHtml(m.nickname)}</p><div class="message-content">${escapeHtml(m.content)}</div><time>${escapeHtml(clockTime(m.created_at))}</time></div></div>`;
  }).join('') : '<p class="empty">아직 나눈 이야기가 없어요.<br>가벼운 인사부터 시작해볼까요? ☺</p>';
  if (nearBottom || forceBottom) box.scrollTop = box.scrollHeight;
  $('older-messages').hidden = olderCursor === null;
}
async function syncChat() {
  if (!user) return;
  const version = ++chatVersion, epoch = sessionEpoch, day = $('chat-date').value;
  if (!day) throw new Error('대화 날짜를 선택하세요.');
  let cursor = chatCursor, first = cursor === null;
  do {
    const query = new URLSearchParams({date:day,limit:'100'});
    if (cursor !== null) query.set('after_id',cursor);
    const data = await api(`/api/chat/messages/?${query}`);
    if (version !== chatVersion || epoch !== sessionEpoch || day !== $('chat-date').value) return;
    addMessages(data.messages);
    if (first) olderCursor = data.next_before_id;
    if (data.messages.length) cursor = data.messages.at(-1).id;
    chatCursor = cursor; renderMessages(first);
    if (first || !data.has_more) break;
    first = false;
  } while (true);
}
function openSchedule(schedule = null) {
  $('schedule-form').reset(); $('schedule-id').value = schedule?.id || '';
  $('schedule-dialog-title').textContent = schedule ? '일정 수정' : '새로운 일정';
  $('schedule-title').value = schedule?.title || ''; $('schedule-category').value = schedule?.category || 'study';
  $('schedule-description').value = schedule?.description || '';
  const start = new Date(Date.now()+3600000); start.setSeconds(0,0);
  $('schedule-start').value = kstInput(schedule?.starts_at || start);
  $('schedule-end').value = kstInput(schedule?.ends_at || new Date(+start+3600000));
  $('overlap-warning').hidden = true; $('schedule-error').textContent = '';
  $('schedule-dialog').showModal();
}

$('login-form').addEventListener('submit', event => {
  event.preventDefault();
  busy(event.submitter, async () => {
    await refreshCsrf();
    const result = await api('/api/auth/login/', 'POST', {username:$('username').value,password:$('password').value});
    csrfToken = result.csrf_token; await showApp(result.user);
  }, $('login-error'));
});
$('logout').addEventListener('click', event => busy(event.currentTarget, async () => { await api('/api/auth/logout/','POST'); showLogin(); toast('로그아웃했어요. 입실·테이블 이용 상태는 유지됩니다.'); }));
$('refresh').addEventListener('click', event => busy(event.currentTarget, refreshAll));
$('presence-button').addEventListener('click', event => busy(event.currentTarget, async () => {
  const inside = attendance?.is_inside;
  await api(`/api/attendance/${inside ? 'check-out' : 'check-in'}/`,'POST');
  toast(inside ? '퇴실했어요. 다음에 또 만나요!' : '입실했어요. 어서 오세요!'); await refreshAll();
}));
$('table-list').addEventListener('click', event => {
  const button = event.target.closest('[data-table]'); if (!button) return;
  const table = tables.find(t => String(t.id) === button.dataset.table); if (!table) return;
  busy(button, async () => { await api(`/api/tables/${table.id}/use/`,table.is_using ? 'DELETE' : 'POST',{}); toast(table.is_using ? '테이블 이용을 종료했어요.' : `${table.name} 이용을 시작했어요.`); await refreshAll(); });
});
$('range-form').addEventListener('submit', event => { event.preventDefault(); busy(event.submitter, refreshAll); });
$('new-schedule').addEventListener('click', () => openSchedule());
$('schedule-list').addEventListener('click', event => {
  const button = event.target.closest('[data-schedule-action]'); if (!button) return;
  const schedule = schedules.find(s => String(s.id) === button.dataset.id); if (!schedule) return;
  switch (button.dataset.scheduleAction) {
    case 'edit': openSchedule(schedule); break;
    case 'recruit':
      $('recruit-id').value = schedule.id; $('recruit-schedule-name').textContent = schedule.title;
      $('recruit-disabled').checked = schedule.recruitment.capacity === null;
      $('recruit-capacity').value = schedule.recruitment.capacity || 4;
      $('recruit-capacity').disabled = $('recruit-disabled').checked;
      $('recruit-error').textContent = ''; $('recruit-dialog').showModal(); break;
    case 'cancel': cancelId = schedule.id; $('cancel-error').textContent = ''; $('confirm-dialog').showModal(); break;
    case 'join': busy(button, async () => {
      await api(`/api/schedules/${schedule.id}/participation/`,schedule.recruitment.is_participating ? 'DELETE' : 'POST',{});
      toast(schedule.recruitment.is_participating ? '참여를 취소했어요.' : '모임에 참여했어요!'); await refreshAll();
    }); break;
  }
});
$('schedule-form').addEventListener('input', event => { if (event.target.id !== 'confirm-overlap') { $('confirm-overlap').checked = false; $('overlap-warning').hidden = true; } });
$('schedule-form').addEventListener('submit', event => {
  event.preventDefault(); busy(event.submitter, async () => {
    const id = $('schedule-id').value;
    const body = {title:$('schedule-title').value,description:$('schedule-description').value,category:$('schedule-category').value,
      starts_at:new Date(`${$('schedule-start').value}:00+09:00`).toISOString(),ends_at:new Date(`${$('schedule-end').value}:00+09:00`).toISOString(),confirm_overlap:$('confirm-overlap').checked};
    try {
      await api(id ? `/api/schedules/${id}/` : '/api/schedules/',id ? 'PATCH' : 'POST',body);
      $('schedule-dialog').close(); toast(id ? '일정을 수정했어요.' : '새 일정을 만들었어요. 모집은 일정의 ‘모집 설정’에서 열어주세요.'); await refreshAll();
    } catch(error) {
      if (error.code === 'schedule_overlap') {
        $('overlap-list').innerHTML = (error.details?.conflicts || []).map(s=>`<li>${escapeHtml(s.title)} · ${escapeHtml(dateTime(s.starts_at))}</li>`).join('') + (error.details?.has_more ? '<li>외 추가 일정이 있습니다.</li>' : '');
        $('overlap-warning').hidden = false;
      }
      throw error;
    }
  },$('schedule-error'));
});
$('confirm-cancel').addEventListener('click', event => busy(event.currentTarget, async () => { await api(`/api/schedules/${cancelId}/cancel/`,'POST',{}); $('confirm-dialog').close(); toast('일정을 취소했어요.'); await refreshAll(); }, $('cancel-error')));
$('recruit-disabled').addEventListener('change', () => { $('recruit-capacity').disabled = $('recruit-disabled').checked; });
$('recruit-form').addEventListener('submit', event => {
  event.preventDefault(); busy(event.submitter, async () => { await api(`/api/schedules/${$('recruit-id').value}/recruitment/`,'PUT',{capacity:$('recruit-disabled').checked ? null : Number($('recruit-capacity').value)}); $('recruit-dialog').close(); toast('모집 설정을 저장했어요.'); await refreshAll(); },$('recruit-error'));
});
document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>$(button.dataset.close).close()));
$('chat-date').addEventListener('change', () => { resetChat(); syncChat().catch(error=>toast(error.message)); });
$('older-messages').addEventListener('click', event => busy(event.currentTarget, async () => {
  if (!olderCursor) return;
  const day = $('chat-date').value, epoch = sessionEpoch;
  const data = await api(`/api/chat/messages/?${new URLSearchParams({date:day,before_id:olderCursor,limit:'100'})}`);
  if (epoch !== sessionEpoch || day !== $('chat-date').value) return;
  const height = $('messages').scrollHeight, top = $('messages').scrollTop;
  addMessages(data.messages); olderCursor = data.next_before_id; renderMessages(); $('messages').scrollTop = top + $('messages').scrollHeight-height;
}));
$('chat-form').addEventListener('submit', event => {
  event.preventDefault(); busy(event.submitter, async () => {
    const content = $('chat-input').value.trim(); if (!content) return;
    if (!pendingMessage || pendingMessage.content !== content) pendingMessage = {content,client_id:crypto.randomUUID()};
    const result = await api('/api/chat/messages/','POST',pendingMessage);
    pendingMessage = null; if ($('chat-input').value.trim() === content) $('chat-input').value = '';
    if ($('chat-date').value !== kstDate()) { $('chat-date').value = kstDate(); resetChat(); }
    addMessages([result.message]); renderMessages(true); await syncChat();
  });
});
document.querySelectorAll('.sidebar nav a').forEach(link=>link.addEventListener('click',()=>{ document.querySelectorAll('.sidebar nav a').forEach(a=>a.classList.remove('active')); link.classList.add('active'); }));
document.addEventListener('visibilitychange',()=>{ if (!document.hidden && user) refreshAll(); });
window.addEventListener('online',()=>{ if (user) { refreshAll(); if (!socket || socket.readyState === WebSocket.CLOSED) { clearTimeout(reconnectTimer); connectSocket(); } } });
$('today-label').textContent = new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',month:'long',day:'numeric',weekday:'long'}).format(new Date()) + ' · KOSS COMMUNITY';
$('range-start').value = kstDate(); $('range-end').value = kstDate(new Date(Date.now()+7*86400000)); $('chat-date').value = kstDate();
(async () => {
  try { await refreshCsrf(); const result = await api('/api/auth/me/'); await showApp(result.user); }
  catch (error) { showLogin(error.status === 401 ? '' : error.message); }
})();
