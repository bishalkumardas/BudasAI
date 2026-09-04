(() => {const modal=document.querySelector('[data-search-modal]'),input=document.querySelector('#site-search'),menu=document.querySelector('[data-menu]'),nav=document.querySelector('#primary-nav');const open=()=>{modal.hidden=false;setTimeout(()=>input.focus(),0)},close=()=>modal.hidden=true;document.querySelectorAll('[data-open-search]').forEach(button=>button.addEventListener('click',open));document.querySelector('[data-close-search]').addEventListener('click',close);modal.addEventListener('click',e=>{if(e.target===modal)close()});document.addEventListener('keydown',e=>{if(e.key==='Escape')close();if(e.key==='/'&&document.activeElement.tagName!=='INPUT'){e.preventDefault();open()}});menu.addEventListener('click',()=>{nav.classList.toggle('open');menu.setAttribute('aria-expanded',nav.classList.contains('open'))})})();

(() => {
  const ticker = document.querySelector('.ticker-track');
  if (!ticker) return;
  const viewport = ticker.closest('.ticker-viewport');
  const source = ticker.querySelector('.ticker-set');
  if (!viewport || !source) return;
  const speed = 72;

  const updateTicker = () => {
    const distance = source.getBoundingClientRect().width;
    if (!distance) return;
    while (ticker.scrollWidth < viewport.clientWidth + distance) {
      const copy = source.cloneNode(true);
      copy.setAttribute('aria-hidden', 'true');
      copy.querySelectorAll('a').forEach(link => link.setAttribute('tabindex', '-1'));
      ticker.append(copy);
    }
    ticker.style.setProperty('--ticker-distance', `${distance}px`);
    ticker.style.setProperty('--ticker-duration', `${distance / speed}s`);
  };

  updateTicker();
  if (window.ResizeObserver) new ResizeObserver(updateTicker).observe(viewport);
  else window.addEventListener('resize', updateTicker);
})();

(() => {
  const chart = document.querySelector('[data-market-chart]');
  if (!chart) return;
  const svg = chart.querySelector('svg');
  const status = chart.querySelector('.chart-status');
  const tooltip = chart.querySelector('.chart-tooltip');
  const buttons = [...chart.querySelectorAll('[data-period]')];
  const currency = chart.dataset.currency || 'USD';
  const svgNS = 'http://www.w3.org/2000/svg';
  const price = value => new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 4 }).format(value);
  const displayDate = value => {
    const parts = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long', year: 'numeric', weekday: 'long', timeZone: 'Asia/Kolkata' }).formatToParts(new Date(value));
    const get = type => parts.find(part => part.type === type)?.value || '';
    return `${get('day')} ${get('month')} ${get('year')}, ${get('weekday')}`;
  };
  const make = (name, attrs = {}, text = '') => { const node = document.createElementNS(svgNS, name); Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value)); node.textContent = text; return node; };
  const hideTip = () => { tooltip.hidden = true; };
  const showTip = (point, event) => {
    tooltip.innerHTML = `<strong>${price(point.value)}</strong>${displayDate(point.timestamp)}`;
    tooltip.hidden = false;
    const box = svg.getBoundingClientRect();
    const x = event?.clientX ? event.clientX - box.left : box.width * (point.x / 600);
    tooltip.style.left = `${Math.min(Math.max(6, x + 12), box.width - 160)}px`;
    tooltip.style.top = `${Math.max(8, box.height * (point.y / 240) - 18)}px`;
  };
  const draw = points => {
    svg.replaceChildren();
    if (!points.length) { status.hidden = false; status.textContent = 'No stored data is available for this period.'; return; }
    status.hidden = true;
    const first = Number(points[0].value);
    const raw = points.map(point => ({ ...point, time: new Date(point.timestamp).getTime(), change: ((Number(point.value) / first) - 1) * 100 }));
    const left = 58, right = 14, top = 12, bottom = 38, width = 600 - left - right, height = 240 - top - bottom;
    const low = Math.min(...raw.map(point => point.change)), high = Math.max(...raw.map(point => point.change));
    const padding = Math.max((high - low) * .12, .1), min = low - padding, max = high + padding, spread = max - min;
    const start = raw[0].time, end = raw[raw.length - 1].time, duration = end - start || 1;
    const scaled = raw.map(point => ({ ...point, x: left + ((point.time - start) / duration) * width, y: top + (max - point.change) / spread * height }));
    for (let i = 0; i <= 4; i += 1) {
      const value = min + (spread * i / 4), y = top + height - (height * i / 4);
      svg.append(make('line', { x1: left, x2: 600 - right, y1: y, y2: y, class: 'chart-grid' }));
      svg.append(make('text', { x: left - 8, y: y + 4, 'text-anchor': 'end', class: 'chart-axis-label' }, `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`));
    }
    for (let i = 0; i <= 3; i += 1) {
      const point = scaled[Math.round((scaled.length - 1) * i / 3)];
      svg.append(make('text', { x: point.x, y: 228, 'text-anchor': i === 0 ? 'start' : i === 3 ? 'end' : 'middle', class: 'chart-axis-label' }, displayDate(point.timestamp)));
    }
    const line = make('polyline', { points: scaled.map(point => `${point.x},${point.y}`).join(' ') }); svg.append(line);
    const hitArea = make('rect', { x: left, y: top, width, height, fill: 'transparent', class: 'chart-hit-area' });
    const nearest = event => { const bounds = svg.getBoundingClientRect(), x = ((event.clientX - bounds.left) / bounds.width) * 600; return scaled.reduce((closest, point) => Math.abs(point.x - x) < Math.abs(closest.x - x) ? point : closest); };
    hitArea.addEventListener('mousemove', event => showTip(nearest(event), event)); hitArea.addEventListener('mouseleave', hideTip); svg.append(hitArea);
  };
  const setPeriod = async period => {
    buttons.forEach(button => { const selected = button.dataset.period === period; button.classList.toggle('active', selected); button.setAttribute('aria-pressed', String(selected)); });
    status.hidden = false; status.textContent = `Loading ${period} chart…`;
    try { const response = await fetch(`${chart.dataset.historyUrl}?period=${encodeURIComponent(period)}`); if (!response.ok) throw new Error('History unavailable'); draw((await response.json()).points || []); }
    catch { status.textContent = 'Unable to load chart data. Please try again.'; }
  };
  buttons.forEach(button => button.addEventListener('click', () => setPeriod(button.dataset.period)));
  draw(window.marketHistory || []);
})();

document.querySelectorAll('[data-news-image]').forEach(image => {
  image.addEventListener('error', () => {
    image.hidden = true;
    image.parentElement.classList.add('has-image-fallback');
  }, { once: true });
});
