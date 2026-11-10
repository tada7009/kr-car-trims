/* 트림노트 — 국산차 트림·옵션 상담판 (정적 단일 페이지, 빌드 없음) */
(() => {
'use strict';

const BRANDS = { hyundai: '현대', kia: '기아', genesis: '제네시스', kgm: 'KGM', renault: '르노코리아', chevrolet: '쉐보레',
  tesla: '테슬라', bmw: 'BMW', mercedes: '벤츠', volvo: '볼보', lexus: '렉서스', toyota: '토요타', audi: '아우디',
  porsche: '포르쉐', volkswagen: '폭스바겐', polestar: '폴스타' };
const IMPORT = new Set(['tesla', 'bmw', 'mercedes', 'volvo', 'lexus', 'toyota', 'audi', 'porsche', 'volkswagen', 'polestar']);
const MARKETS = { dom: '국산차', imp: '수입차' };
const marketOf = b => (IMPORT.has(b) ? 'imp' : 'dom');
// 국산차는 차급, 수입차는 공식 가격표의 차체 구분으로 묶는다
const SEG_DOM = ['경차', '소형 SUV', '준중형 세단', '준중형 SUV', '중형 세단', '중형 SUV', '준대형 세단', '대형 세단',
  '대형 SUV', 'MPV·승합', '픽업', '고성능', '상용·트럭'];
const SEG_IMP = ['해치백', 'MPV', '세단', '전기 세단', '4도어 쿠페', '전기 4도어 쿠페', '왜건', 'SUV', '전기 SUV', '쿠페형 SUV',
  '쿠페', '카브리올레', '컨버터블', '로드스터', '픽업'];
let SEG = SEG_DOM;
const TRAY_MAX = 4;
const OPT_PREVIEW = 8;

// 상담 때 가장 많이 묻는 사양 — 품목 이름 규칙으로 트림마다 기본/옵션/없음을 판정한다
const KEYS = [
  { l: '휠 · 타이어', wheel: true },
  { l: '시트 재질', t: n => /시트/.test(n) && /(나파|천연 ?가죽|인조 ?가죽|가죽|직물|스웨이드)/.test(n) && !/스티어링|암레스트|도어/.test(n),
    v: n => /나파/.test(n) ? '나파가죽' : /천연 ?가죽/.test(n) ? '천연가죽' : /인조 ?가죽/.test(n) ? '인조가죽' : /스웨이드/.test(n) ? '스웨이드' : /가죽/.test(n) ? '가죽' : '직물' },
  { l: '1열 통풍시트', t: n => /통풍/.test(n) && !/^(2열|뒷좌석|3열|후석)/.test(n.trim()),
    v: n => /운전석 ?통풍/.test(n) && !/(동승석|앞좌석|1열)/.test(n) ? '운전석만' : '' },
  { l: '2열 열선 · 통풍', t: n => /(2열|뒷좌석|후석)[^,]*(열선|통풍)/.test(n), v: n => /통풍/.test(n) ? '통풍' : '열선' },
  // 인치는 '12.3인치'뿐 아니라 '11"', '12.3”'(쉐보레·르노 표기)로도 쓴다
  { l: '디스플레이(내비)', t: n => /\d+(\.\d+)?\s*(인치|"|”)/.test(n) && /(내비|커넥트|디스플레이 오디오|인포테인먼트|터치 ?스크린|통합형 디스플레이|센터 디스플레이)/.test(n) && !(/클러스터/.test(n) && !/(내비|센터 디스플레이|터치)/.test(n)) && !/헤드업/.test(n),
    v: n => (n.match(/(\d+(?:\.\d+)?)\s*(?:인치|"|”)/) || [])[1] + '인치' + (/(내비|커넥트|통합형|TMAP)/.test(n) ? ' 내비' : ' 화면') },
  { l: '헤드업 디스플레이', t: n => /헤드업|HUD/.test(n) && !/경고등/.test(n) },
  { l: '스마트 크루즈', t: n => /스마트 ?크루즈|어댑티브 크루즈|인텔리전트 크루즈|트래픽 어웨어 크루즈/.test(n) },
  // 수입차는 같은 기능을 파일럿 어시스트(볼보)·오토스티어(테슬라) 같은 자기 이름으로 적는다
  { l: '고속도로 주행 보조', t: n => /고속도로 ?주행 ?보조|파일럿 (보조|어시스트)|Pilot Assist|오토스티어/i.test(n),
    v: n => /파일럿|Pilot/i.test(n) ? '파일럿 어시스트' : /오토스티어/.test(n) ? '오토스티어' : /(보조 ?2|Ⅱ|차로 ?변경)/.test(n) ? 'HDA 2' : 'HDA' },
  { l: '서라운드 뷰 모니터', t: n => /서라운드 ?뷰|360/.test(n) },
  { l: '후측방 충돌 보조', t: n => /후측방 충돌|사각지대 (경고|감지|정보)|BLIS|후측방경보/.test(n), v: n => /방지 ?보조/.test(n) ? '방지 보조' : '경고' },
  { l: '후측방 모니터', t: n => /후측방 모니터|사각지대 영상/.test(n) },
  { l: '원격 스마트 주차', t: n => /원격 스마트 주차|원격 주차/.test(n) },
  { l: '전동 트렁크 · 테일게이트', t: n => /(파워|전동|스마트 파워|스마트 전동식?)\s?(트렁크|테일게이트|리프트게이트)/.test(n) },
  { l: '디지털 키', t: n => /디지털 ?키/.test(n) },
  { l: '무선 충전', t: n => /무선 ?충전/.test(n) },
  { l: '선루프', t: n => /선루프|비전 루프|글라스 루프|파노라믹 루프/.test(n) && !/스킨|미적용/.test(n) },
  { l: '빌트인 캠(블랙박스)', t: n => /빌트인 ?캠/.test(n) },
  { l: '프리미엄 사운드', t: n => /(보스|BOSE|렉시콘|메리디안|뱅앤올룹슨|B&O|하만|Harman|Bowers|부메스터|Burmester|JBL|크렐|프리미엄 사운드|레퍼런스 사운드)/i.test(n) && !/일반/.test(n),
    v: n => (n.match(/(보스|BOSE|렉시콘|메리디안|뱅앤올룹슨|하만|Harman Kardon|Bowers & Wilkins|부메스터|Burmester|JBL|크렐|레퍼런스)/i) || ['', ''])[1] },
];

const S = { index: null, byId: {}, models: {}, prep: new Map(), search: null, market: 'dom', brand: 'all', seg: 'all', listQ: '',
  view: {}, cmpView: { diff: true, f: '' }, tray: [], route: '' };

// ---------- 유틸 ----------
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const man = n => n == null ? '–' : (n / 10000).toLocaleString('ko-KR', { maximumFractionDigits: 1 });
const won = n => n == null ? '–' : n.toLocaleString('ko-KR') + '원';
const norm = s => String(s).toLowerCase().replace(/[\s·∙ㆍ,.\-_/&]+/g, '');
const norm2 = s => norm(String(s).replace(/\([^)]*\)/g, ''));
// fb: 첫 이미지가 안 열리면 대신 쓸 이미지(트림 사진 → 사이트에 저장한 차종 사진)
const img = (src, alt = '', eager = false, fb = '') => src
  ? `<img src="${esc(src)}" alt="${esc(alt)}" loading="${eager ? 'eager' : 'lazy'}" referrerpolicy="no-referrer"${fb && fb !== src ? ` data-fb="${esc(fb)}"` : ''} onerror="if(this.dataset.fb){this.src=this.dataset.fb;this.removeAttribute('data-fb')}else{this.style.visibility='hidden'}">`
  : '<span class="ph"></span>';
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* 저장할 수 없는 환경 */ } },
};
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.h); toast.h = setTimeout(() => (t.hidden = true), 1800);
}
async function getJSON(p) {
  const r = await fetch(p, { cache: 'no-cache' });
  if (!r.ok) throw new Error(p + ' ' + r.status);
  return r.json();
}
async function loadModel(id) {
  if (S.models[id]) return S.models[id];
  const meta = S.byId[id];
  if (!meta) throw new Error('알 수 없는 차종: ' + id);
  S.models[id] = await getJSON('data/' + meta.file);
  return S.models[id];
}
function canonCat(c) {
  if (/파워|성능|엔진|구동|주행 모드/.test(c) && !/보조/.test(c)) return '파워트레인 · 성능';
  if (/지능형|ADAS|운전자 ?보조|안전/.test(c)) return '안전 · 운전 보조';
  if (/외관|외장|익스테리어/.test(c)) return '외관';
  if (/시트/.test(c)) return '시트';
  if (/내장|인테리어/.test(c)) return '내장';
  if (/인포|멀티|오디오|내비/.test(c)) return '인포테인먼트';
  if (/편의|컨비니언스/.test(c)) return '편의';
  return '기타';
}

// ---------- 차종 데이터 가공(트림별 기본/옵션 집합) ----------
function prepVariant(model, v) {
  const pk = model.packages || {};
  const trims = v.trims.map(t => {
    const std = new Set(), std2 = new Set(), names = [];
    t.cats.forEach(c => c.items.forEach(i => { std.add(norm(i.n)); std2.add(norm2(i.n)); names.push(i.n); }));
    const opt = new Map(), opt2 = new Map(), optNames = [];
    t.opts.forEach((o, oi) => {
      const ref = { o, oi };
      [o.n].concat((pk[o.c]?.items || []).map(i => i.n)).forEach(n => {
        if (!opt.has(norm(n))) opt.set(norm(n), ref);
        if (!opt2.has(norm2(n))) opt2.set(norm2(n), ref);
        optNames.push([n, ref]);
      });
    });
    return { t, std, std2, opt, opt2, names, optNames };
  });
  const cats = [], catIdx = new Map(), seen = new Set();
  v.trims.forEach(t => t.cats.forEach(c => {
    const ck = norm(c.cat);
    if (!catIdx.has(ck)) { catIdx.set(ck, cats.length); cats.push({ cat: c.cat, items: [] }); }
    const bucket = cats[catIdx.get(ck)];
    c.items.forEach(i => { const k = norm(i.n); if (!seen.has(k)) { seen.add(k); bucket.items.push({ n: i.n, k, k2: norm2(i.n) }); } });
  }));
  const optRows = [], oseen = new Set();
  v.trims.forEach(t => t.opts.forEach(o => {
    const k = norm(o.n);
    if (oseen.has(k)) return; oseen.add(k);
    optRows.push({ n: o.n, k, k2: norm2(o.n), g: o.g, isOpt: true });
  }));
  return { trims, cats, optRows };
}
function prep(model, vi) {
  const key = model.id + '#' + vi;
  if (!S.prep.has(key)) S.prep.set(key, prepVariant(model, model.variants[vi]));
  return S.prep.get(key);
}
function cell(P, ti, row) {
  const T = P.trims[ti];
  if (row.isOpt) {
    const o = T.t.opts.find(x => norm(x.n) === row.k);
    if (o) return { s: 'opt', o };
    if (T.std.has(row.k) || T.std2.has(row.k2)) return { s: 'std' };
    return { s: 'none' };
  }
  if (T.std.has(row.k)) return { s: 'std' };
  const r = T.opt.get(row.k) || T.opt2.get(row.k2);
  if (r) return { s: 'opt', o: r.o };
  return { s: 'none' };
}
function wheelOf(names) {
  let best = 0;
  names.forEach(n => {
    if (!/(휠|타이어)/.test(n)) return;
    const m = n.match(/(\d{2})\s*(?:인치|"|”)/) || n.match(/R\s?(\d{2})\b/);
    if (m && +m[1] > best && +m[1] < 24) best = +m[1];
  });
  return best ? { v: best + '인치', inch: best } : null;
}
function keyCell(T, K) {
  if (K.wheel) {
    const w = wheelOf(T.names);
    let up = null;
    T.t.opts.forEach(o => { const ow = wheelOf([o.n]); if (ow && (!w || ow.inch > w.inch) && (!up || ow.inch > up.w.inch)) up = { o, w: ow }; });
    if (w) return { s: 'val', v: w.v, sub: up ? `${up.w.v} 선택 +${man(up.o.p)}만` : '' };
    if (up) return { s: 'opt', o: up.o, v: up.w.v };
    return { s: 'none' };
  }
  const hit = T.names.find(K.t);
  if (hit) return { s: 'std', v: K.v ? K.v(hit) : '' };
  const oh = T.optNames.find(([n]) => K.t(n));
  if (oh) return { s: 'opt', o: oh[1].o, v: K.v ? K.v(oh[0]) : '' };
  return { s: 'none' };
}
const isOn = c => c.s === 'std' || c.s === 'val';
function cellHTML(c, isNew) {
  if (c.s === 'std') return `<span class="st ${isNew ? 'st-new' : 'st-std'}">${c.v ? esc(c.v) : '기본'}</span>`;
  if (c.s === 'val') return `<span class="st-val">${esc(c.v)}</span>${c.sub ? `<span class="st-sub">${esc(c.sub)}</span>` : ''}`;
  if (c.s === 'opt') return `<span class="st st-opt" title="${esc(c.o.n)} ${won(c.o.p)}">${c.v ? esc(c.v) + ' ' : ''}<span class="won">${c.o.p ? '+' + man(c.o.p) + '만' : '선택'}</span></span><span class="st-sub">${esc(c.o.n)}</span>`;
  return '<span class="st-none">–</span>';
}
// 한 단계 올라갈 때 새로 기본이 되는 핵심 사양
function keyGain(P, i) {
  if (!i) return [];
  return KEYS.filter(K => {
    const a = keyCell(P.trims[i - 1], K), b = keyCell(P.trims[i], K);
    if (K.wheel) return a.s === 'val' && b.s === 'val' && b.v !== a.v;
    return isOn(b) && (!isOn(a) || (b.v && b.v !== a.v));
  }).map(K => K.l.replace(/\s?\(.*\)/, ''));
}

// ---------- 비교함 ----------
function trayLoad() { S.tray = store.get('tray', []).filter(x => S.byId[x.id]).slice(0, TRAY_MAX); trayBadge(); }
function traySave() { store.set('tray', S.tray); trayBadge(); }
function trayBadge() { document.querySelectorAll('.tray-count').forEach(e => (e.textContent = S.tray.length)); }
function trayHas(id, v, t) { return S.tray.findIndex(x => x.id === id && x.v === v && x.t === t); }
function trayToggle(id, v, t, o) {
  const i = trayHas(id, v, t);
  if (i >= 0) { S.tray.splice(i, 1); traySave(); toast('비교함에서 뺐습니다'); return; }
  if (S.tray.length >= TRAY_MAX) { toast(`비교함에는 ${TRAY_MAX}개까지 담을 수 있습니다`); return; }
  S.tray.push({ id, v, t, o: o || [] }); traySave(); toast('비교함에 담았습니다');
}

// ---------- 사이드바 ----------
function filtered() {
  SEG = S.market === 'imp' ? SEG_IMP : SEG_DOM;
  const q = norm(S.listQ || '');
  return S.index.models.filter(m => marketOf(m.brand) === S.market && (S.brand === 'all' || m.brand === S.brand)
    && (S.seg === 'all' || m.segment === S.seg) && (!q || norm(m.name + BRANDS[m.brand] + m.segment).includes(q)))
    .sort((a, b) => (SEG.indexOf(a.segment) - SEG.indexOf(b.segment)) || a.low - b.low);
}
// 지금 보는 시장(국산/수입)에 차종이 있는 브랜드
const marketBrands = () => ['all', ...Object.keys(BRANDS).filter(b => marketOf(b) === S.market && S.index.models.some(m => m.brand === b))];
const marketTabs = () => Object.entries(MARKETS).map(([k, l]) => {
  const n = S.index.models.filter(m => marketOf(m.brand) === k).length;
  return `<button type="button" class="${S.market === k ? 'on' : ''}" data-market="${k}" aria-pressed="${S.market === k}">${l}<span>${n}</span></button>`;
}).join('');
function renderSide() {
  const ms = S.index.models;
  $('#marketSeg').innerHTML = marketTabs();
  $('#brandChips').innerHTML = marketBrands().map(b =>
    `<button type="button" class="${S.brand === b ? 'on' : ''}" data-brand="${b}" aria-pressed="${S.brand === b}">${b === 'all' ? '전체' : BRANDS[b]}</button>`).join('');
  const cur = S.route.startsWith('m/') ? S.route.slice(2).split('?')[0] : '';
  let html = '';
  Object.keys(BRANDS).forEach(b => {
    const list = filtered().filter(m => m.brand === b);
    if (!list.length) return;
    html += `<div class="mgroup">${BRANDS[b]} · ${list.length}</div>` + list.map(m =>
      `<a class="mi${m.id === cur ? ' on' : ''}" href="#/m/${m.id}">${img(m.image)}<span class="n">${esc(m.name)}</span><span class="p">${man(m.low)}~</span></a>`).join('');
  });
  $('#mlist').innerHTML = html || '<p class="mgroup">조건에 맞는 차종이 없습니다</p>';
  $('#navTotal').textContent = ms.length;
  document.querySelectorAll('.snav-i').forEach(a => a.classList.toggle('on',
    (a.dataset.nav === 'home' && (!S.route || S.route === '/')) || (a.dataset.nav === 'compare' && S.route === 'compare')));
  $('#sideFoot').textContent = `가격표 수집 ${S.index.updated}`;
}

// ---------- 홈: 전체 차종 ----------
function renderHome() {
  const ms = S.index.models.filter(m => marketOf(m.brand) === S.market), list = filtered();
  const trims = ms.reduce((a, m) => a + m.trims, 0);
  const brands = marketBrands();
  const segs = SEG.filter(s => ms.some(m => m.segment === s && (S.brand === 'all' || m.brand === S.brand)));
  let rows = '';
  SEG.forEach(seg => {
    const l = list.filter(m => m.segment === seg);
    if (!l.length) return;
    rows += `<tr class="grp"><td colspan="6">${esc(seg)}<span>${l.length}</span></td></tr>` + l.map(m => `<tr class="r" data-go="#/m/${m.id}" tabindex="0">
      <td class="r-img"><div>${img(m.image, m.name)}</div></td>
      <td class="r-n"><b>${esc(m.name)}</b><span>${esc(m.fuels.slice(0, 4).join(' · '))}${m.fuels.length > 4 ? ' 외' : ''}</span></td>
      <td class="hide-m">${BRANDS[m.brand]}</td>
      <td class="num hide-m">${m.trims}</td>
      <td class="num"><b>${man(m.low)}</b>만원</td>
      <td class="num hide-m">${man(m.high)}만원</td></tr>`).join('');
  });
  $('#main').innerHTML = `
    <div class="title-row"><div><h1>${MARKETS[S.market]} 전체</h1>
      <p class="sub">제조사 공식 ${S.market === 'imp' ? '가격표·구성기' : '가격표'} 기준 ${ms.length}개 차종, 트림 ${trims}개. 차종을 누르면 트림·옵션 비교로 넘어갑니다.</p></div>
      <div class="market-seg big" role="group" aria-label="국산차·수입차">${marketTabs()}</div></div>
    <div class="tabs" role="tablist">${brands.map(b => `<button type="button" role="tab" aria-selected="${S.brand === b}" class="${S.brand === b ? 'on' : ''}" data-brand="${b}">${b === 'all' ? '전체' : BRANDS[b]}</button>`).join('')}</div>
    <div class="toolbar"><input class="field" id="listQ" type="search" placeholder="차종 이름으로 거르기" value="${esc(S.listQ)}" aria-label="차종 이름으로 거르기">
      <select id="segSel" aria-label="차급"><option value="all">모든 차급</option>${segs.map(s => `<option${S.seg === s ? ' selected' : ''}>${s}</option>`).join('')}</select>
      <span class="count">${list.length}개 차종</span></div>
    <div class="list"><table><thead><tr><th></th><th>차종 · 파워트레인</th><th class="hide-m">브랜드</th><th class="num hide-m">트림</th><th class="num">시작가</th><th class="num hide-m">최고가</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="6" class="empty">조건에 맞는 차종이 없습니다</td></tr>'}</tbody></table></div>` + footHTML();
}
function footHTML() {
  return `<p class="foot">가격은 각 제조사 공식 홈페이지 가격표(자가용, 공시된 세제 기준)를 자동으로 모은 값이며 탁송료·등록비·프로모션은 들어 있지 않습니다. 수입차는 공식 가격표·구성기 기준이며, BMW·벤츠는 공식 자료에 트림별 상세 품목이 공개되지 않아 가격과 트림 이름에서 확인되는 사양만 보여 줍니다.
  ● 기본 장착 · ○ 선택 옵션(패키지) 추가 시 장착 · – 선택 불가. <span style="color:var(--hue)">● 파란 점</span>은 바로 아래 트림에는 없고 이 트림부터 기본인 사양입니다. 사양 판정은 가격표 품목명 기준 자동 분류이므로 계약 전에는 공식 가격표로 한 번 더 확인해 주세요. 차량 이미지는 각 제조사 공식 홈페이지의 이미지입니다.</p>`;
}

// ---------- 차종 화면: 구성기 + 비교표 ----------
async function renderModel(id, params) {
  const main = $('#main');
  if (!S.models[id]) main.innerHTML = '<div class="loading">불러오는 중…</div>';
  let M;
  try { M = await loadModel(id); } catch (e) { main.innerHTML = `<div class="empty"><b>차종 정보를 불러오지 못했습니다</b>${esc(e.message)}</div>`; return; }
  const V = S.view;
  if (V.id !== id) Object.assign(V, { id, v: 0, t: 0, opts: new Set(), diff: true, f: '', closed: new Set(), allOpts: false, pkg: -1, media: 'ext', mi: 0 });
  if (params.f != null) { V.f = params.f; V.diff = false; }
  if (params.v != null) V.v = Math.min(+params.v, M.variants.length - 1);
  if (params.t != null) V.t = +params.t;
  const vi = V.v, VAR = M.variants[vi];
  V.t = Math.min(V.t, VAR.trims.length - 1);
  const P = prep(M, vi), meta = S.byId[id], T = VAR.trims[V.t];
  const bto = M.structure === 'bto';
  $('#mbarTitle').textContent = M.name;

  // 가장 눈에 띄는 단계(핵심 사양이 가장 많이 기본으로 바뀌는 트림)
  let best = null;
  VAR.trims.forEach((t, i) => { const g = keyGain(P, i); if (g.length && (!best || g.length > best.g.length)) best = { i, g }; });
  const find = best ? `<p class="find"><b>${esc(VAR.trims[best.i].name)}</b>(+${man(VAR.trims[best.i].price - VAR.trims[best.i - 1].price)}만)부터 ${best.g.slice(0, 3).map(esc).join(', ')}${best.g.length > 3 ? ` 등 ${best.g.length}개` : ''}가 기본입니다.</p>` : '';
  const prices = VAR.trims.map(t => t.price || 0), lo = Math.min(...prices), hi = Math.max(...prices);
  // 트림 버튼: 무대 아래에 크게 — 통화 중 한 번에 눌러 바꾼다
  const tbar = VAR.trims.length > 1 ? `<div class="tbar" role="radiogroup" aria-label="트림 바로 선택">${VAR.trims.map((t, i) =>
    `<button type="button" role="radio" aria-checked="${i === V.t}" class="${i === V.t ? 'on' : ''}" data-act="trim" data-i="${i}">
      <b>${esc(t.name)}</b><span>${man(t.price)}만${i ? ` · +${man(t.price - VAR.trims[i - 1].price)}` : ''}</span></button>`).join('')}</div>` : '';
  // 사진: 외관(트림 사진 → 대표 렌더 → 외관 사진) / 실내 갤러리
  const md = M.media || {};
  const extList = [...new Set([T.img, md.hero || M.image, ...(md.ext || [])].filter(Boolean))];
  const intList = md.int || [];
  if (V.media === 'int' && !intList.length) V.media = 'ext';
  const gal = V.media === 'int' ? intList : extList;
  V.mi = Math.min(V.mi || 0, gal.length - 1);
  const cur = gal[V.mi] || M.image;
  const isPhoto = V.media === 'int' || (md.ext || []).includes(cur) || (cur === md.hero && md.heroType === 'photo');
  const mtabs = `<div class="mtabs" role="tablist" aria-label="사진 종류">
    <button type="button" role="tab" aria-selected="${V.media !== 'int'}" class="${V.media !== 'int' ? 'on' : ''}" data-act="media" data-m="ext">외관</button>
    <button type="button" role="tab" aria-selected="${V.media === 'int'}" class="${V.media === 'int' ? 'on' : ''}" data-act="media" data-m="int" ${intList.length ? '' : 'disabled title="공식 실내 사진이 없습니다"'}>실내${intList.length ? ` ${intList.length}` : ''}</button></div>`;
  const thumbs = gal.length > 1 ? `<div class="thumbs">${gal.map((u, i) =>
    `<button type="button" class="${i === V.mi ? 'on' : ''}" data-act="photo" data-i="${i}" aria-label="사진 ${i + 1}">${img(u)}</button>`).join('')}</div>` : '';

  // 선택한 트림의 핵심 사양을 칩으로 — 통화 중 '이 트림엔 뭐가 들어가요?'에 바로 답한다
  const chipList = KEYS.map(K => ({ K, c: keyCell(P.trims[V.t], K) })).filter(x => x.c.s !== 'none');
  const CHIP = {  // 칩에 적을 짧은 말 (값이 있으면 값을 살린다)
    '휠 · 타이어': v => `${v} 휠`, '시트 재질': v => `${v} 시트`, '1열 통풍시트': v => v ? '운전석 통풍' : '1열 통풍',
    '2열 열선 · 통풍': v => `2열 ${v}`, '디스플레이(내비)': v => v, '고속도로 주행 보조': v => v,
    '후측방 충돌 보조': v => v === '경고' ? '후측방 경고' : '후측방 충돌방지', '프리미엄 사운드': v => v ? `${v} 사운드` : '프리미엄 사운드',
  };
  const chipLabel = ({ K, c }) => (CHIP[K.l] && c.v ? CHIP[K.l](c.v) : K.l.replace(/\s?\(.*\)/, '').replace('서라운드 뷰 모니터', '서라운드 뷰'));
  const chips = chipList.length ? `<p class="chips-h"><b>${esc(T.name)}</b> 핵심 사양 · 점선은 옵션</p><div class="chips">${chipList.map(x =>
    `<span class="kchip${x.c.s === 'opt' ? ' opt' : ''}"${x.c.s === 'opt' ? ` title="${esc(x.c.o.n)} +${man(x.c.o.p)}만"` : ''}>${esc(chipLabel(x))}</span>`).join('')}</div>` : '';
  const cards = VAR.trims.map((t, i) => {
    const prev = i ? VAR.trims[i - 1] : null;
    const added = i ? [...P.trims[i].std].filter(k => !P.trims[i - 1].std.has(k)).length : 0;
    const inTray = trayHas(id, vi, i) >= 0;
    const d = prev ? `<b>+${man(t.price - prev.price)}만</b>${added ? ` · 사양 +${added}` : ''}` : (bto ? '기본 가격' : '시작 트림');
    return `<div class="pick${i === V.t ? ' on' : ''}" role="radio" aria-checked="${i === V.t}" tabindex="0" data-act="trim" data-i="${i}">
      <span class="rd" aria-hidden="true"></span>${t.en ? `<span class="k">${esc(t.en)}</span>` : ''}
      <span class="t">${esc(t.name)}</span><span class="p">${won(t.price)}</span><span class="d">${d}</span>
      <button type="button" class="cmp${inTray ? ' in' : ''}" data-act="tray" data-i="${i}">${inTray ? '담김' : '＋비교'}</button></div>`;
  }).join('');

  main.classList.add('has-dock');
  main.innerHTML = `
    <div class="crumb"><a href="#/">전체 차종</a><span class="sep">/</span><span>${BRANDS[M.brand]}</span><span class="sep">/</span><span>${esc(M.name)}</span>
      <span class="src"><span>${esc(M.priceDate || '')}</span>${M.sources.map((s, i) => `<a href="${esc(s)}" target="_blank" rel="noopener">공식 가격표${M.sources.length > 1 ? ' ' + (i + 1) : ''}</a>`).join('')}</span></div>
    ${M.variants.length > 1 ? `<div class="tabs" role="tablist">${M.variants.map((v, i) => `<button type="button" role="tab" aria-selected="${i === vi}" class="${i === vi ? 'on' : ''}" data-act="variant" data-i="${i}">${esc(v.name)}</button>`).join('')}</div>` : ''}
    <div class="config">
      <section class="stage" aria-label="${esc(M.name)}">
        <div class="stage-top"><div><h1>${esc(M.name)}<span class="chip">${esc(M.segment)}</span></h1>
          <p class="meta">${BRANDS[M.brand]} · ${esc(VAR.name)} · 트림 ${VAR.trims.length}개${VAR.modelYear ? ' · ' + esc(VAR.modelYear) : ''}</p>${find}</div>
          <div class="figs"><div><b>${man(lo)}</b><span>시작가(만원)</span></div><div><b>${man(hi)}</b><span>최고가(만원)</span></div><div><b>${meta.trims}</b><span>전체 트림</span></div></div></div>
        <div class="car ${isPhoto ? 'photo' : 'cut'}">${mtabs}${img(cur, `${M.name} ${V.media === 'int' ? '실내' : '외관'}`, true, M.image)}</div>${thumbs}${tbar}${chips}
      </section>
      <div class="panel">
        <div><div class="panel-h"><h2>${bto ? '엔진 · 구동' : '트림'}</h2><span class="cnt">${V.t + 1} / ${VAR.trims.length}</span></div>
          <div class="cards" role="radiogroup" aria-label="트림">${cards}</div></div>
        <div id="optBox">${optionsHTML(M, V)}</div>
      </div>
    </div>
    ${keysHTML(P, VAR, V)}
    <section class="sec" id="mxSec"><div class="sec-h"><h2>${bto ? '선택 품목 비교' : '전체 사양 비교'}</h2><span class="sub" id="mxCount"></span>
      <div class="tools"><label class="tog"><input type="checkbox" data-act="diff" ${V.diff ? 'checked' : ''}>차이만 보기</label>
      <input class="field" id="mxFilter" type="search" placeholder="사양 찾기 (예: 통풍)" value="${esc(V.f)}" aria-label="사양 찾기"></div></div>
      ${bto ? '<p class="foot" style="margin:0 0 12px">제네시스는 트림 대신 엔진·구동 조합별 기본 가격에 선택 패키지를 더하는 구조입니다. 기본 사양은 모든 조합에 공통입니다.</p>' : ''}
      <div class="tbl-wrap"><table class="mx" id="mx">${theadHTML(VAR, V)}<tbody></tbody></table></div></section>
    ${(VAR.notes || []).length ? `<details class="notes-box"><summary>기타 안내사항<span>${VAR.notes.length}건</span></summary><ul class="notes">${VAR.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul></details>` : ''}
    ${footHTML()}
    <div class="dock" id="dock">${dockHTML(M, V)}</div>`;
  refreshMatrix();
  if (params.f != null) setTimeout(() => $('#mxSec')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60);
}
function theadHTML(VAR, V) {
  return `<thead><tr><th class="rh">사양</th>${VAR.trims.map((t, i) => `<th class="${i === V.t ? 'on' : ''}"><b>${esc(t.name)}</b><span class="num">${man(t.price)}만원</span></th>`).join('')}</tr></thead>`;
}
function keysHTML(P, VAR, V) {
  const rows = KEYS.map(K => {
    const cs = P.trims.map(T => keyCell(T, K));
    if (cs.every(c => c.s === 'none')) return '';
    return `<tr><th class="rh">${K.l}</th>${cs.map((c, i) => `<td class="c${i === V.t ? ' on' : ''}">${cellHTML(c, isOn(c) && c.s === 'std' && i > 0 && !isOn(cs[i - 1]))}</td>`).join('')}</tr>`;
  }).join('');
  if (!rows) return '';
  return `<section class="sec"><div class="sec-h"><h2>핵심 사양 한눈에</h2><span class="sub">상담 때 자주 묻는 ${KEYS.length}가지</span>
    <div class="tools legend"><span class="st st-std">기본</span><span class="st st-new">이 트림부터 기본</span><span class="st st-opt">옵션</span><span class="st-none">– 없음</span></div></div>
    <div class="tbl-wrap"><table class="mx">${theadHTML(VAR, V)}<tbody>${rows}</tbody></table></div></section>`;
}
function matrixRows(P, V) {
  const f = norm(V.f || '');
  let html = '', shown = 0, total = 0;
  const groups = P.cats.map(c => ({ cat: c.cat, rows: c.items }));
  if (P.optRows.length) groups.push({ cat: '선택 품목 (옵션 · 컬러 · 액세서리)', rows: P.optRows });
  groups.forEach(g => {
    let body = '', n = 0;
    g.rows.forEach(row => {
      total++;
      const cs = P.trims.map((_, i) => cell(P, i, row));
      const diff = new Set(cs.map(c => c.s)).size > 1;
      if (f && !norm(row.n).includes(f)) return;
      if (V.diff && !diff && !f) return;
      n++;
      body += `<tr><th class="rh">${esc(row.n)}${row.isOpt && row.g && row.g !== '옵션' ? `<span class="tag">${esc(row.g)}</span>` : ''}</th>` +
        cs.map((c, i) => `<td class="c${i === V.t ? ' on' : ''}">${cellHTML(c, c.s === 'std' && i > 0 && cs[i - 1].s !== 'std')}</td>`).join('') + '</tr>';
    });
    if (!n) return;
    shown += n;
    const closed = V.closed.has(g.cat);
    html += `<tr class="cat" data-act="cat" data-cat="${esc(g.cat)}"><td colspan="${P.trims.length + 1}">${closed ? '▸' : '▾'} ${esc(g.cat)}<span>${n}</span></td></tr>` + (closed ? '' : body);
  });
  if (!shown) html = `<tr class="empty-row"><td colspan="${P.trims.length + 1}">${f ? '찾는 사양이 없습니다. 다른 낱말로 찾아보세요.' : '트림 사이에 다른 사양이 없습니다. 차이만 보기를 끄면 전체 사양이 보입니다.'}</td></tr>`;
  return { html, count: `${shown}개 표시 · 전체 ${total}개` };
}
function optionsHTML(M, V) {
  const t = M.variants[V.v].trims[V.t];
  if (!t) return '';
  const list = t.opts.map((o, i) => [o, i]);
  const show = V.allOpts ? list : list.slice(0, OPT_PREVIEW);
  const items = show.map(([o, i]) => {
    const pk = M.packages?.[o.c];
    const subs = pk?.items?.length ? pk.items : null;
    const desc = pk?.desc && pk.desc !== '-' ? pk.desc : '';
    const card = `<label class="oc"><input type="checkbox" data-act="opt" data-i="${i}" ${V.opts.has(i) ? 'checked' : ''}>
      ${o.g && o.g !== '옵션' ? `<span class="g">${esc(o.g)}</span>` : ''}<span class="t">${esc(o.n)}</span>${o.note ? `<span class="nt">${esc(o.note)}</span>` : ''}
      <span class="p">${o.ask ? '가격 별도' : o.p ? '+' + won(o.p) : '무상'}</span>
      ${subs || desc ? `<button type="button" class="more" data-act="pkg" data-i="${i}" aria-expanded="${V.pkg === i}">${subs ? `구성 ${subs.length}개` : '설명'} ${V.pkg === i ? '닫기' : '보기'}</button>` : ''}</label>`;
    const detail = V.pkg === i ? `<div class="pkg"><b>${esc(o.n)}</b>${desc ? `<div style="color:var(--muted);margin-top:2px">${esc(desc)}</div>` : ''}
      ${subs ? `<ul>${subs.map(x => `<li>${esc(x.n)}${x.d && x.d !== '-' ? `<span>${esc(x.d)}</span>` : ''}</li>`).join('')}</ul>` : ''}</div>` : '';
    return card + detail;
  }).join('');
  return `<div class="panel-h"><h2>선택 옵션</h2><span class="cnt">${V.opts.size ? `${V.opts.size}개 선택 · ` : ''}${list.length}개</span></div>
    <div class="opts" style="grid-auto-flow:row dense">${items || '<p class="foot more-row" style="margin:0">이 트림에는 선택 옵션이 없습니다.</p>'}
    ${list.length > OPT_PREVIEW ? `<div class="more-row"><button type="button" class="btn sm" data-act="allOpts">${V.allOpts ? '옵션 접기' : `옵션 ${list.length - OPT_PREVIEW}개 더 보기`}</button></div>` : ''}</div>`;
}
function dockHTML(M, V) {
  const VAR = M.variants[V.v], t = VAR.trims[V.t];
  const sel = [...V.opts].map(i => t.opts[i]).filter(Boolean);
  const optSum = sel.reduce((a, o) => a + (o.p || 0), 0);
  const inTray = trayHas(M.id, V.v, V.t) >= 0;
  return `<div class="cell"><span>차량 가격</span><b>${won(t.price)}</b></div>
    <div class="cell"><span>선택 옵션 ${sel.length}개</span><b>${optSum ? '+' + won(optSum) : '0원'}</b></div>
    <div class="cell total"><span>합계</span><b>${won((t.price || 0) + optSum)}</b></div>
    <div class="who"><b>${esc(M.name)} ${esc(t.name)}</b> · ${esc(VAR.name)}</div>
    <div class="acts"><button type="button" class="btn" data-act="trayOpts">${inTray ? '비교함 갱신' : '비교함 담기'}</button>
    <button type="button" class="btn pri" data-act="copy">요약 복사</button></div>`;
}
function summaryText(M, vi, ti, optIdx) {
  const v = M.variants[vi], t = v.trims[ti], T = prep(M, vi).trims[ti];
  const sel = optIdx.map(i => t.opts[i]).filter(Boolean);
  const sum = (t.price || 0) + sel.reduce((a, o) => a + (o.p || 0), 0);
  const keys = KEYS.map(K => {
    const c = keyCell(T, K), l = K.l.replace(/\s?\(.*\)/, '');
    if (isOn(c)) return l + (c.v ? `(${c.v})` : '');
    if (c.s === 'opt' && sel.includes(c.o)) return l + '(옵션)';
    return null;
  }).filter(Boolean);
  return [`[${BRANDS[M.brand]} ${M.name} · ${v.name} · ${t.name}]`, `차량 가격 ${won(t.price)}`,
    ...sel.map(o => `+ ${o.n} ${won(o.p)}`), `= 합계 ${won(sum)}`, '', `주요 사양: ${keys.join(', ')}`,
    `(${M.priceDate || ''} 제조사 가격표 기준, 탁송료·등록비 별도)`].join('\n');
}

// ---------- 비교함(차종 간 비교) ----------
async function renderCompare() {
  const main = $('#main');
  $('#mbarTitle').textContent = '비교함';
  if (!S.tray.length) {
    main.innerHTML = `<div class="crumb"><a href="#/">전체 차종</a><span class="sep">/</span><span>비교함</span></div>
      <div class="title-row" style="margin-bottom:16px"><h1>비교함</h1></div>
      <div class="empty"><b>비교할 트림을 담아 주세요</b>차종 화면의 트림 카드에서 ＋비교를 누르면 최대 ${TRAY_MAX}개까지 나란히 비교됩니다. 다른 차종끼리도 됩니다.</div>` + footHTML();
    return;
  }
  main.innerHTML = '<div class="loading">불러오는 중…</div>';
  await Promise.all(S.tray.map(x => loadModel(x.id).catch(() => null)));
  const cols = S.tray.map((x, ci) => {
    const M = S.models[x.id]; if (!M) return null;
    const vi = Math.min(x.v, M.variants.length - 1), v = M.variants[vi];
    const ti = Math.min(x.t, v.trims.length - 1), t = v.trims[ti];
    const sel = (x.o || []).map(i => t.opts[i]).filter(Boolean);
    return { ci, x, M, v, t, T: prep(M, vi).trims[ti], sel, sum: (t.price || 0) + sel.reduce((a, o) => a + (o.p || 0), 0) };
  }).filter(Boolean);
  const V = S.cmpView, n = cols.length + 1;
  const head = `<thead><tr><th class="rh">비교 항목</th>${cols.map(c => `<th><div class="cmp-h"><div class="im">${img(c.t.img || c.M.image, c.M.name)}</div>
    <span>${BRANDS[c.M.brand]} · ${esc(c.M.segment)}</span><a href="#/m/${c.M.id}?v=${c.x.v}&t=${c.x.t}">${esc(c.M.name)} ${esc(c.t.name)}</a>
    <span>${esc(c.v.name)}</span><span class="p">${won(c.sum)}</span><span>${c.sel.length ? `옵션 ${c.sel.length}개 포함` : '옵션 없음'}</span>
    <button type="button" class="btn sm x" data-act="trayDel" data-i="${c.ci}">빼기</button></div></th>`).join('')}</tr></thead>`;
  const priceRows = [['차량 가격', c => won(c.t.price)], ['선택 옵션', c => c.sel.length ? c.sel.map(o => `${esc(o.n)} +${man(o.p)}만`).join('<br>') : '–'],
    ['합계', c => `<b>${won(c.sum)}</b>`]].map(([l, f]) => `<tr><th class="rh">${l}</th>${cols.map(c => `<td class="c num">${f(c)}</td>`).join('')}</tr>`).join('');
  const keyRows = KEYS.map(K => `<tr><th class="rh">${K.l}</th>${cols.map(c => `<td class="c">${cellHTML(keyCell(c.T, K))}</td>`).join('')}</tr>`).join('');
  const groups = new Map();
  cols.forEach(c => c.t.cats.forEach(cat => {
    const g = canonCat(cat.cat);
    if (!groups.has(g)) groups.set(g, new Map());
    cat.items.forEach(i => { const k = norm2(i.n); if (!groups.get(g).has(k)) groups.get(g).set(k, i.n); });
  }));
  const f = norm(V.f || ''), order = ['파워트레인 · 성능', '안전 · 운전 보조', '외관', '내장', '시트', '편의', '인포테인먼트', '기타'];
  let full = '', shown = 0;
  [...groups.keys()].sort((a, b) => order.indexOf(a) - order.indexOf(b)).forEach(g => {
    let body = '', cnt = 0;
    groups.get(g).forEach((label, k) => {
      const cs = cols.map(c => c.T.std2.has(k) ? { s: 'std' } : (c.T.opt2.get(k) ? { s: 'opt', o: c.T.opt2.get(k).o } : { s: 'none' }));
      if (f && !norm(label).includes(f)) return;
      if (V.diff && new Set(cs.map(c => c.s)).size < 2 && !f) return;
      cnt++;
      body += `<tr><th class="rh">${esc(label)}</th>${cs.map(c => `<td class="c">${cellHTML(c)}</td>`).join('')}</tr>`;
    });
    if (cnt) { shown += cnt; full += `<tr class="cat"><td colspan="${n}">${esc(g)}<span>${cnt}</span></td></tr>` + body; }
  });
  main.innerHTML = `<div class="crumb"><a href="#/">전체 차종</a><span class="sep">/</span><span>비교함</span></div>
    <div class="sec-h" style="margin-bottom:16px"><h2 style="font-size:30px;line-height:36px">비교함</h2><span class="sub">${cols.length}개 트림 · 다른 차종끼리도 나란히</span>
      <div class="tools"><button type="button" class="btn" data-act="trayClear">모두 비우기</button><button type="button" class="btn pri" data-act="cmpCopy">비교 요약 복사</button></div></div>
    <div class="tbl-wrap"><table class="mx cmp">${head}<tbody>
      <tr class="cat"><td colspan="${n}">가격</td></tr>${priceRows}
      <tr class="cat"><td colspan="${n}">핵심 사양</td></tr>${keyRows}</tbody></table></div>
    <section class="sec"><div class="sec-h"><h2>전체 사양 비교</h2><span class="sub">${shown}개 표시</span>
      <div class="tools"><label class="tog"><input type="checkbox" data-act="cmpDiff" ${V.diff ? 'checked' : ''}>차이만 보기</label>
      <input class="field" id="cmpFilter" type="search" placeholder="사양 찾기" value="${esc(V.f)}" aria-label="사양 찾기"></div></div>
      <div class="tbl-wrap"><table class="mx cmp">${head}<tbody>${full || `<tr class="empty-row"><td colspan="${n}">표시할 사양이 없습니다</td></tr>`}</tbody></table></div></section>` + footHTML();
}

// ---------- 통합 검색 ----------
async function gsearch(q) {
  const pop = $('#gsPop');
  q = q.trim();
  if (!q) { pop.hidden = true; return; }
  const ql = q.toLowerCase(), qn = norm(q), ms = S.index.models;
  const byName = ms.filter(m => norm(m.name + BRANDS[m.brand] + m.segment).includes(qn)).slice(0, 8);
  let html = '';
  if (byName.length) html += '<div class="gs-h">차종</div>' + byName.map(m => `<div class="gs-i" data-go="#/m/${m.id}">${img(m.image)}<b>${esc(m.name)}</b>
      <span class="s">${BRANDS[m.brand]} · ${man(m.low)}만~</span></div>`).join('');
  if (qn.length >= 2) {
    if (!S.search) { try { S.search = await getJSON('data/search.json'); } catch (e) { S.search = {}; } }
    const hits = ms.filter(m => { const s = S.search[m.id] || ''; return !byName.includes(m) && (s.includes(ql) || s.replace(/\s+/g, '').includes(qn)); }).slice(0, 14);
    if (hits.length) html += `<div class="gs-h">'${esc(q)}' 사양이 있는 차종</div>` + hits.map(m => `<div class="gs-i" data-go="#/m/${m.id}?f=${encodeURIComponent(q)}">${img(m.image)}<b>${esc(m.name)}</b>
      <span class="s">사양표에서 보기</span></div>`).join('');
  }
  pop.innerHTML = html || '<div class="gs-h">찾는 차종이나 사양이 없습니다</div>';
  pop.hidden = false;
}

// ---------- 라우팅 ----------
function parseHash() {
  const h = location.hash.replace(/^#\/?/, '');
  const [path, qs] = h.split('?');
  const params = {};
  new URLSearchParams(qs || '').forEach((v, k) => (params[k] = v));
  return { path, params };
}
async function route() {
  const { path, params } = parseHash();
  S.route = location.hash.replace(/^#\/?/, '');
  setMenu(false);
  $('#gsPop').hidden = true;
  $('#main').classList.remove('has-dock');
  if (path.startsWith('m/')) {
    const m = S.byId[path.slice(2)];
    if (m && marketOf(m.brand) !== S.market) { S.market = marketOf(m.brand); S.brand = 'all'; S.seg = 'all'; }
    await renderModel(path.slice(2), params);
  }
  else if (path === 'compare') await renderCompare();
  else { $('#mbarTitle').textContent = '트림노트'; renderHome(); }
  renderSide();
  if (!params.f) window.scrollTo(0, 0);
}
function setMenu(open) { $('#side').classList.toggle('open', open); $('#menuBtn').setAttribute('aria-expanded', open); }

// ---------- 화면 일부만 다시 그리기 ----------
function rerender() { const y = window.scrollY; renderModel(S.view.id, {}).then(() => window.scrollTo(0, y)); }
function refreshMatrix() {
  const M = S.models[S.view.id]; if (!M || !$('#mx')) return;
  const r = matrixRows(prep(M, S.view.v), S.view);
  $('#mx tbody').innerHTML = r.html; $('#mxCount').textContent = r.count;
}
function refreshOptions() {
  const M = S.models[S.view.id]; if (!M) return;
  $('#optBox').innerHTML = optionsHTML(M, S.view);
  $('#dock').innerHTML = dockHTML(M, S.view);
}
async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast('복사했습니다. 카톡에 붙여 넣으세요'); }
  catch (e) {
    const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); toast('복사했습니다'); } catch (_) { toast('복사하지 못했습니다'); }
    ta.remove();
  }
}

// ---------- 이벤트 ----------
function bind() {
  window.addEventListener('hashchange', route);
  document.addEventListener('click', e => {
    const mk = e.target.closest('[data-market]');
    if (mk) {
      S.market = mk.dataset.market; S.brand = 'all'; S.seg = 'all';
      try { localStorage.setItem('market', S.market); } catch (_) { /* 저장할 수 없는 환경 */ }
      renderSide(); if (!S.route || S.route === '/') renderHome(); else location.hash = '#/'; return;
    }
    const b = e.target.closest('[data-brand]');
    if (b) { S.brand = b.dataset.brand; S.seg = 'all'; renderSide(); if (!S.route || S.route === '/') renderHome(); return; }
    const go = e.target.closest('tr[data-go]');
    if (go) location.hash = go.dataset.go;
  });
  document.addEventListener('keydown', e => {
    const go = e.target.closest && e.target.closest('tr[data-go]');
    if (go && e.key === 'Enter') location.hash = go.dataset.go;
    const pick = e.target.closest && e.target.closest('.pick');
    if (pick && (e.key === 'Enter' || e.key === ' ') && e.target === pick) { e.preventDefault(); pick.click(); }
    if ((e.key === '/' || (e.key === 'k' && (e.ctrlKey || e.metaKey))) && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); $('#q').focus(); $('#q').select(); }
  });
  $('#menuBtn').addEventListener('click', () => setMenu(!$('#side').classList.contains('open')));
  const themeBtn = $('#themeBtn');
  const themeLabel = () => (themeBtn.textContent = document.documentElement.dataset.theme === 'dark' ? '밝게' : '어둡게');
  themeLabel();
  themeBtn.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next; themeLabel();
    try { localStorage.setItem('theme', next); } catch (e) { /* 저장할 수 없는 환경 */ }
  });
  const q = $('#q');
  let tm;
  q.addEventListener('input', () => { clearTimeout(tm); tm = setTimeout(() => gsearch(q.value), 120); });
  q.addEventListener('focus', () => q.value && gsearch(q.value));
  q.addEventListener('keydown', e => {
    const items = [...document.querySelectorAll('.gs-i')];
    let i = items.findIndex(x => x.classList.contains('on'));
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault(); items[i]?.classList.remove('on');
      i = e.key === 'ArrowDown' ? Math.min(items.length - 1, i + 1) : Math.max(0, i - 1);
      items[i]?.classList.add('on'); items[i]?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') { const t = items[i] || items[0]; if (t) { location.hash = t.dataset.go; q.blur(); } }
    else if (e.key === 'Escape') { $('#gsPop').hidden = true; q.blur(); }
  });
  $('#gsPop').addEventListener('mousedown', e => { const t = e.target.closest('[data-go]'); if (t) { e.preventDefault(); location.hash = t.dataset.go; q.blur(); $('#gsPop').hidden = true; } });
  q.addEventListener('blur', () => setTimeout(() => ($('#gsPop').hidden = true), 150));

  const main = $('#main');
  main.addEventListener('click', e => {
    const a = e.target.closest('[data-act]'); if (!a) return;
    const act = a.dataset.act, V = S.view;
    if (act === 'variant') { V.v = +a.dataset.i; V.t = 0; V.opts = new Set(); V.pkg = -1; V.mi = 0; return rerender(); }
    if (act === 'tray') { e.stopPropagation(); trayToggle(V.id, V.v, +a.dataset.i); return rerender(); }
    if (act === 'trim') { if (V.t !== +a.dataset.i) { V.t = +a.dataset.i; V.opts = new Set(); V.pkg = -1; if (V.media !== 'int') V.mi = 0; rerender(); } return; }
    if (act === 'media') { if (V.media !== a.dataset.m) { V.media = a.dataset.m; V.mi = 0; rerender(); } return; }
    if (act === 'photo') { V.mi = +a.dataset.i; return rerender(); }
    if (act === 'cat') { const c = a.dataset.cat; V.closed.has(c) ? V.closed.delete(c) : V.closed.add(c); return refreshMatrix(); }
    if (act === 'pkg') { e.preventDefault(); V.pkg = V.pkg === +a.dataset.i ? -1 : +a.dataset.i; return refreshOptions(); }
    if (act === 'allOpts') { V.allOpts = !V.allOpts; return refreshOptions(); }
    if (act === 'copy') return copy(summaryText(S.models[V.id], V.v, V.t, [...V.opts]));
    if (act === 'trayOpts') {
      const i = trayHas(V.id, V.v, V.t);
      if (i >= 0) { S.tray[i].o = [...V.opts]; traySave(); toast('비교함의 옵션을 갱신했습니다'); }
      else trayToggle(V.id, V.v, V.t, [...V.opts]);
      return rerender();
    }
    if (act === 'trayDel') { S.tray.splice(+a.dataset.i, 1); traySave(); return renderCompare(); }
    if (act === 'trayClear') { S.tray = []; traySave(); return renderCompare(); }
    if (act === 'cmpCopy') return copy(S.tray.map(x => S.models[x.id] ? summaryText(S.models[x.id], x.v, x.t, x.o || []) : '').join('\n\n────────\n\n'));
  });
  main.addEventListener('change', e => {
    const a = e.target.closest('[data-act]');
    if (e.target.id === 'segSel') { S.seg = e.target.value; renderHome(); renderSide(); return; }
    if (!a) return;
    const V = S.view;
    if (a.dataset.act === 'diff') { V.diff = a.checked; refreshMatrix(); }
    if (a.dataset.act === 'opt') { const i = +a.dataset.i; a.checked ? V.opts.add(i) : V.opts.delete(i); refreshOptions(); }
    if (a.dataset.act === 'cmpDiff') { S.cmpView.diff = a.checked; renderCompare(); }
  });
  main.addEventListener('input', e => {
    if (e.target.id === 'mxFilter') { S.view.f = e.target.value; refreshMatrix(); }
    if (e.target.id === 'listQ') {
      S.listQ = e.target.value; clearTimeout(main.t);
      main.t = setTimeout(() => { renderHome(); renderSide(); const el = $('#listQ'); el.focus(); el.setSelectionRange(el.value.length, el.value.length); }, 200);
    }
    if (e.target.id === 'cmpFilter') {
      S.cmpView.f = e.target.value; clearTimeout(main.t);
      main.t = setTimeout(async () => { await renderCompare(); const el = $('#cmpFilter'); el.focus(); el.setSelectionRange(el.value.length, el.value.length); }, 250);
    }
  });
}

// ---------- 시작 ----------
(async function start() {
  try { S.index = await getJSON('data/index.json'); }
  catch (e) { $('#main').innerHTML = `<div class="empty"><b>데이터를 불러오지 못했습니다</b>${esc(e.message)}</div>`; return; }
  S.index.models.forEach(m => (S.byId[m.id] = m));
  try { const mk = localStorage.getItem('market'); if (MARKETS[mk]) S.market = mk; } catch (_) { /* 저장할 수 없는 환경 */ }
  trayLoad(); bind(); route();
})();
})();
