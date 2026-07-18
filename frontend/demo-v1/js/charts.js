import { WORLD_COUNTRIES } from './world-countries.js';
const SVG_NS = 'http://www.w3.org/2000/svg';


function clear(el) { el.innerHTML = ''; }
function fmt(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 's/d';
  return Number(value).toLocaleString('pt-BR', { maximumFractionDigits: digits });
}

function makeSvg(container, height = 310) {
  clear(container);
  const width = Math.max(container.clientWidth || 640, 420);
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  container.appendChild(svg);
  return { svg, width, height };
}

function el(name, attrs = {}, text = '') {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text) node.textContent = text;
  return node;
}

function scaleLinear(domainMin, domainMax, rangeMin, rangeMax) {
  const d = domainMax - domainMin || 1;
  return (v) => rangeMin + ((v - domainMin) / d) * (rangeMax - rangeMin);
}

export function renderBarChart(container, data, options = {}) {
  const rows = data || [];
  if (!rows.length) return renderEmptyChart(container, 'Sem dados para o gráfico.');
  const { svg, width, height } = makeSvg(container, options.height || 310);
  const m = { top: 26, right: 18, bottom: 54, left: 58 };
  const innerW = width - m.left - m.right;
  const innerH = height - m.top - m.bottom;
  const max = Math.max(...rows.map((d) => Number(d.value) || 0), 1);
  const barW = innerW / rows.length;

  drawGrid(svg, m, innerW, innerH, max, 4);
  rows.forEach((d, i) => {
    const value = Number(d.value) || 0;
    const h = (value / max) * innerH;
    const x = m.left + i * barW + Math.min(8, barW * .18);
    const y = m.top + innerH - h;
    const w = Math.max(5, barW - Math.min(16, barW * .36));
    svg.appendChild(el('rect', { x, y, width: w, height: h, rx: 7, class: d.className || 'chart-bar' }));
    svg.appendChild(el('text', { x: x + w / 2, y: height - 28, 'text-anchor': 'middle', fill: '#65738a', 'font-size': '11', transform: options.rotateLabels ? `rotate(-28 ${x + w / 2} ${height - 28})` : '' }, String(d.label).slice(0, 16)));
    if (options.showValues !== false) svg.appendChild(el('text', { x: x + w / 2, y: Math.max(16, y - 6), 'text-anchor': 'middle', fill: '#173957', 'font-size': '11', 'font-weight': '800' }, fmt(value, 1)));
  });
}

export function renderGroupedBarChart(container, rows, options = {}) {
  if (!rows?.length) return renderEmptyChart(container, 'Sem dados para o gráfico.');
  const { svg, width, height } = makeSvg(container, options.height || 390);
  const m = { top: 34, right: 18, bottom: 55, left: 58 };
  const innerW = width - m.left - m.right;
  const innerH = height - m.top - m.bottom;
  const max = Math.max(...rows.flatMap((d) => [d.a || 0, d.b || 0]), 1);
  const groupW = innerW / rows.length;
  const barW = Math.max(6, groupW * .28);

  drawGrid(svg, m, innerW, innerH, max, 5);
  rows.forEach((d, i) => {
    const x0 = m.left + i * groupW + groupW / 2;
    const aH = ((d.a || 0) / max) * innerH;
    const bH = ((d.b || 0) / max) * innerH;
    svg.appendChild(el('rect', { x: x0 - barW - 2, y: m.top + innerH - aH, width: barW, height: aH, rx: 6, class: 'chart-bar' }));
    svg.appendChild(el('rect', { x: x0 + 2, y: m.top + innerH - bH, width: barW, height: bH, rx: 6, class: 'chart-bar alt' }));
    svg.appendChild(el('text', { x: x0, y: height - 20, 'text-anchor': 'middle', fill: '#65738a', 'font-size': '11' }, String(d.label)));
  });
  drawLegend(svg, width - 280, 15, options.labelA || 'Apenas nacional', options.labelB || 'Internacional');
}

export function renderLineChart(container, data, options = {}) {
  const rows = (data || []).filter((d) => d.value !== null && d.value !== undefined);
  if (!rows.length) return renderEmptyChart(container, 'Sem dados para o gráfico.');
  const { svg, width, height } = makeSvg(container, options.height || 310);
  const m = { top: 30, right: 24, bottom: 44, left: 58 };
  const innerW = width - m.left - m.right;
  const innerH = height - m.top - m.bottom;
  const xValues = rows.map((d) => Number(d.label));
  const yValues = rows.map((d) => Number(d.value));
  const minX = Math.min(...xValues), maxX = Math.max(...xValues);
  const maxY = Math.max(...yValues, 1);
  const x = scaleLinear(minX, maxX, m.left, m.left + innerW);
  const y = scaleLinear(0, maxY * 1.08, m.top + innerH, m.top);

  drawGrid(svg, m, innerW, innerH, maxY, 4);
  const points = rows.map((d) => `${x(Number(d.label))},${y(Number(d.value))}`).join(' ');
  svg.appendChild(el('polyline', { points, class: options.className || 'chart-line' }));
  rows.forEach((d) => {
    const cx = x(Number(d.label));
    const cy = y(Number(d.value));
    svg.appendChild(el('circle', { cx, cy, r: 4, class: 'chart-point' }));
    svg.appendChild(el('text', { x: cx, y: height - 16, 'text-anchor': 'middle', fill: '#65738a', 'font-size': '11' }, String(d.label)));
  });
}

export function renderHistogram(container, values, options = {}) {
  const nums = (values || []).filter((v) => Number.isFinite(Number(v))).map(Number);
  if (!nums.length) return renderEmptyChart(container, 'Sem valores de FWCI disponíveis.');
  const bins = options.bins || [0, .5, 1, 1.5, 2, 3, 5, Infinity];
  const labels = ['0-0,5', '0,5-1', '1-1,5', '1,5-2', '2-3', '3-5', '5+'];
  const rows = labels.map((label, i) => ({ label, value: nums.filter((v) => v >= bins[i] && v < bins[i + 1]).length }));
  renderBarChart(container, rows, { height: options.height || 310, showValues: true });
}

export function renderDonutChart(container, rows, options = {}) {
  if (!rows?.length || rows.every((r) => !r.value)) return renderEmptyChart(container, 'Sem dados para o gráfico.');
  const { svg, width, height } = makeSvg(container, options.height || 390);
  const cx = width / 2;
  const cy = height / 2 - 10;
  const r = Math.min(width, height) * .28;
  const stroke = Math.max(34, r * .34);
  const total = rows.reduce((acc, d) => acc + (Number(d.value) || 0), 0);
  const classes = ['donut-national', 'donut-international'];
  let offset = 0;

  rows.forEach((d, i) => {
    const frac = total ? (Number(d.value) || 0) / total : 0;
    const dash = frac * 2 * Math.PI * r;
    const circle = el('circle', {
      cx, cy, r,
      fill: 'none',
      class: classes[i % classes.length],
      'stroke-width': stroke,
      'stroke-dasharray': `${dash} ${2 * Math.PI * r - dash}`,
      'stroke-dashoffset': -offset,
      transform: `rotate(-90 ${cx} ${cy})`
    });
    svg.appendChild(circle);
    offset += dash;
  });

  svg.appendChild(el('text', { x: cx, y: cy - 4, 'text-anchor': 'middle', fill: '#102033', 'font-size': '30', 'font-weight': '950' }, fmt(total, 0)));
  svg.appendChild(el('text', { x: cx, y: cy + 24, 'text-anchor': 'middle', fill: '#65738a', 'font-size': '12', 'font-weight': '800' }, 'publicações'));

  const legendY = height - 70;
  rows.forEach((d, i) => {
    const x = 34 + i * (width / 2 - 10);
    const y = legendY;
    svg.appendChild(el('rect', { x, y, width: 12, height: 12, rx: 3, class: classes[i % classes.length] }));
    svg.appendChild(el('text', { x: x + 18, y: y + 11, fill: '#32475d', 'font-size': '12', 'font-weight': '750' }, `${d.label}: ${fmt(d.value, 0)} (${fmt((d.value / total) * 100, 1)}%)`));
  });
}

export function renderWorldHeatmap(container, rows, options = {}) {
  const data = (rows || [])
    .filter((d) => d?.label && Number(d.value) > 0)
    .map((d) => ({ code: String(d.label).toUpperCase(), value: Number(d.value) || 0 }))
    .sort((a, b) => b.value - a.value);

  // Renderizar sempre o mapa completo, mesmo sem internacionalização.
  // Assim o usuário mantém a referência geográfica e entende visualmente que não há países destacados.
  const values = new Map(data.map((d) => [d.code, d.value]));
  const max = data.length ? Math.max(...data.map((d) => d.value), 1) : 1;
  renderSvgChoropleth(container, values, max, data, options);
}

function renderSvgChoropleth(container, values, max, data, options) {
  clear(container);
  container.style.position = 'relative';

  const summary = document.createElement('div');
  summary.className = 'map-summary-row';
  const totalLinks = data.reduce((acc, d) => acc + d.value, 0);
  const top = data.slice(0, 5);
  summary.innerHTML = `
    <div><strong>${fmt(data.length, 0)}</strong><span> países parceiros</span></div>
    <div><strong>${fmt(totalLinks, 0)}</strong><span> ocorrências de colaboração</span></div>
    <div class="map-top-countries">${top.length
      ? top.map((d) => `<span>${countryFlag(d.code)} ${escapeMapHtml(d.code)} <strong>${fmt(d.value, 0)}</strong></span>`).join('')
      : '<span class="map-no-international">Sem colaboração internacional no recorte atual</span>'}</div>`;
  container.appendChild(summary);

  const mapWrap = document.createElement('div');
  mapWrap.className = 'world-map-wrap';
  container.appendChild(mapWrap);

  const width = 1080;
  const height = options.height || 520;
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Mapa-múndi com intensidade de colaboração internacional por país');
  svg.setAttribute('class', 'world-choropleth-svg');
  mapWrap.appendChild(svg);

  svg.appendChild(el('rect', { x: 0, y: 0, width, height, rx: 18, class: 'map-background' }));

  const detail = document.createElement('div');
  detail.className = 'map-country-detail';
  detail.innerHTML = '<strong>Explore o mapa</strong><span>Passe o mouse ou clique em um país destacado.</span>';
  mapWrap.appendChild(detail);

  for (const feature of WORLD_COUNTRIES.features || []) {
    const code = String(feature?.properties?.iso2 || '').toUpperCase();
    const value = values.get(code) || 0;
    const pathData = geometryToSvgPath(feature.geometry, width, height);
    if (!pathData) continue;
    const name = feature?.properties?.name || code || 'País';
    const path = el('path', {
      d: pathData,
      fill: choroplethColor(value, max),
      stroke: value > 0 ? '#f8fafc' : '#69737f',
      'stroke-width': value > 0 ? 0.85 : 0.72,
      opacity: 1,
      class: value > 0 ? 'map-country active' : 'map-country'
    });
    const title = document.createElementNS(SVG_NS, 'title');
    title.textContent = value > 0
      ? `${name} (${code}): ${fmt(value, 0)} publicações com colaboração internacional`
      : `${name} (${code}): sem colaboração identificada`;
    path.appendChild(title);
    if (value > 0) {
      path.setAttribute('tabindex', '0');
      path.setAttribute('role', 'button');
      path.setAttribute('aria-label', `${name}: ${fmt(value, 0)} publicações com colaboração internacional`);
      const show = () => {
        detail.innerHTML = `<strong>${countryFlag(code)} ${escapeMapHtml(name)}</strong><span>${fmt(value, 0)} publicações com colaboração internacional</span>`;
      };
      path.addEventListener('mouseenter', show);
      path.addEventListener('focus', show);
      path.addEventListener('click', show);
    }
    svg.appendChild(path);
  }

  mapWrap.appendChild(makeMapLegend(max));
}

function geometryToSvgPath(geometry, width, height) {
  if (!geometry?.coordinates) return '';
  const polygons = geometry.type === 'Polygon'
    ? [geometry.coordinates]
    : geometry.type === 'MultiPolygon' ? geometry.coordinates : [];
  const parts = [];
  for (const polygon of polygons) {
    for (const ring of polygon) {
      if (!ring?.length) continue;
      const points = ring.map(([lon, lat]) => projectNaturalEarthLike(lon, lat, width, height));
      parts.push(`M${points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join('L')}Z`);
    }
  }
  return parts.join('');
}

function projectNaturalEarthLike(lon, lat, width, height) {
  // Projeção equiretangular suavizada e com margens fixas para renderização robusta sem tiles externos.
  const marginX = 18;
  const marginY = 26;
  const usableW = width - marginX * 2;
  const usableH = height - marginY * 2;
  const x = marginX + ((Number(lon) + 180) / 360) * usableW;
  const clampedLat = Math.max(-84, Math.min(84, Number(lat)));
  const y = marginY + ((84 - clampedLat) / 168) * usableH;
  return [x, y];
}

function choroplethColor(value, max) {
  if (!value) return '#cfd5dc';
  const ratio = Math.max(0, Math.min(1, value / Math.max(max, 1)));
  if (ratio >= 0.8) return '#7a1520';
  if (ratio >= 0.55) return '#b4232f';
  if (ratio >= 0.3) return '#dd4b39';
  if (ratio >= 0.12) return '#f28a59';
  return '#f8c79f';
}

function makeMapLegend(max) {
  const legend = document.createElement('div');
  legend.className = 'map-legend';
  const steps = [
    { label: 'Sem internacionalização', value: 0 },
    { label: 'Baixa', value: Math.max(1, Math.ceil(max * 0.08)) },
    { label: 'Média', value: Math.max(1, Math.ceil(max * 0.35)) },
    { label: 'Alta', value: Math.max(1, Math.ceil(max * 0.7)) }
  ];
  legend.innerHTML = `<strong>Publicações</strong>${steps.map((step) => `<span><i style="background:${choroplethColor(step.value, max)}"></i>${step.label}</span>`).join('')}`;
  return legend;
}

function countryFlag(code) {
  const value = String(code || '').toUpperCase();
  if (!/^[A-Z]{2}$/.test(value)) return '🌍';
  return [...value].map((c) => String.fromCodePoint(127397 + c.charCodeAt(0))).join('');
}

function escapeMapHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}

function drawGrid(svg, m, innerW, innerH, max, steps) {
  for (let i = 0; i <= steps; i += 1) {
    const y = m.top + innerH - (innerH * i / steps);
    svg.appendChild(el('line', { x1: m.left, x2: m.left + innerW, y1: y, y2: y, class: 'chart-gridline' }));
    svg.appendChild(el('text', { x: m.left - 10, y: y + 4, 'text-anchor': 'end', fill: '#65738a', 'font-size': '11' }, fmt(max * i / steps, 1)));
  }
}

function drawLegend(svg, x, y, labelA, labelB) {
  svg.appendChild(el('rect', { x, y, width: 12, height: 12, rx: 3, class: 'chart-bar' }));
  svg.appendChild(el('text', { x: x + 18, y: y + 11, fill: '#32475d', 'font-size': '12', 'font-weight': '750' }, labelA));
  svg.appendChild(el('rect', { x: x + 145, y, width: 12, height: 12, rx: 3, class: 'chart-bar alt' }));
  svg.appendChild(el('text', { x: x + 163, y: y + 11, fill: '#32475d', 'font-size': '12', 'font-weight': '750' }, labelB));
}

function renderEmptyChart(container, message) {
  clear(container);
  const div = document.createElement('div');
  div.className = 'empty-state';
  div.textContent = message;
  container.appendChild(div);
}
