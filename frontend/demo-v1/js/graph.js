function html(text) {
  return String(text ?? '').replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}

export function renderCollaborationGraph(container, detailsEl, graph) {
  container.innerHTML = '';
  if (!graph?.nodes?.length) {
    container.innerHTML = '<div class="empty-state large">Sem nós suficientes para montar o grafo.</div>';
    return;
  }

  const legend = document.createElement('div');
  legend.className = 'network-legend';
  legend.innerHTML = '<span><i class="legend-dot group"></i>Pessoas do grupo</span><span><i class="legend-dot external-national"></i>Coautores externos nacionais</span><span><i class="legend-dot external-international"></i>Coautores externos internacionais</span><span class="zoom-hint">Use a roda do mouse ou o gesto de pinça para aproximar.</span>';
  container.appendChild(legend);

  const chart = document.createElement('div');
  container.appendChild(chart);

  if (window.d3?.forceSimulation) renderWithD3(chart, detailsEl, graph);
  else renderFallback(chart, detailsEl, graph);
}

function renderWithD3(container, detailsEl, graph) {
  const width = Math.max(container.clientWidth || 900, 620);
  const height = 620;
  const nodes = graph.nodes.map((d) => ({ ...d }));
  const links = graph.links.map((d) => ({ ...d }));

  const svg = window.d3.select(container).append('svg').attr('viewBox', `0 0 ${width} ${height}`);
  const viewport = svg.append('g').attr('class', 'network-viewport');
  svg.call(window.d3.zoom()
    .scaleExtent([0.35, 4])
    .on('zoom', (event) => viewport.attr('transform', event.transform)));

  const link = viewport.append('g')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('class', 'network-link')
    .attr('stroke-width', (d) => Math.max(1, Math.min(8, Math.sqrt(d.weight))));

  const node = viewport.append('g')
    .selectAll('circle')
    .data(nodes)
    .join('circle')
    .attr('class', (d) => `network-node ${d.group}`)
    .attr('r', (d) => d.group === 'group' ? 11 + Math.min(9, Math.sqrt(d.works || 1)) : 6 + Math.min(7, Math.sqrt(d.works || 1)))
    .on('click', (_, d) => showNodeDetails(detailsEl, d))
    .call(window.d3.drag()
      .on('start', dragstarted)
      .on('drag', dragged)
      .on('end', dragended));

  const label = viewport.append('g')
    .selectAll('text')
    .data(nodes.filter((d) => d.group === 'group' || (d.works || 0) >= 2))
    .join('text')
    .attr('class', 'network-label')
    .text((d) => shortName(d.name));

  const simulation = window.d3.forceSimulation(nodes)
    .force('link', window.d3.forceLink(links).id((d) => d.id).distance((d) => Math.max(52, 110 - d.weight * 8)).strength(.25))
    .force('charge', window.d3.forceManyBody().strength((d) => d.group === 'group' ? -360 : -120))
    .force('center', window.d3.forceCenter(width / 2, height / 2))
    .force('collision', window.d3.forceCollide().radius((d) => d.group === 'group' ? 30 : 18))
    .on('tick', () => {
      link
        .attr('x1', (d) => d.source.x)
        .attr('y1', (d) => d.source.y)
        .attr('x2', (d) => d.target.x)
        .attr('y2', (d) => d.target.y);
      node
        .attr('cx', (d) => d.x = clamp(d.x, 18, width - 18))
        .attr('cy', (d) => d.y = clamp(d.y, 18, height - 18));
      label
        .attr('x', (d) => d.x + 12)
        .attr('y', (d) => d.y + 4);
    });

  function dragstarted(event) {
    if (!event.active) simulation.alphaTarget(.3).restart();
    event.subject.fx = event.subject.x;
    event.subject.fy = event.subject.y;
  }
  function dragged(event) {
    event.subject.fx = event.x;
    event.subject.fy = event.y;
  }
  function dragended(event) {
    if (!event.active) simulation.alphaTarget(0);
    event.subject.fx = null;
    event.subject.fy = null;
  }
}

function renderFallback(container, detailsEl, graph) {
  const width = Math.max(container.clientWidth || 900, 620);
  const height = 620;
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  container.appendChild(svg);

  const nodes = graph.nodes.map((node, i) => ({
    ...node,
    x: width / 2 + Math.cos(i) * 80,
    y: height / 2 + Math.sin(i) * 80,
    vx: 0,
    vy: 0
  }));
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const links = graph.links.map((l) => ({ ...l, source: nodeById.get(l.source), target: nodeById.get(l.target) })).filter((l) => l.source && l.target);

  for (let iter = 0; iter < 240; iter += 1) {
    for (const a of nodes) {
      for (const b of nodes) {
        if (a === b) continue;
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (a.group === 'group' || b.group === 'group' ? 280 : 120) / (dist * dist);
        a.vx += (dx / dist) * force;
        a.vy += (dy / dist) * force;
      }
    }
    for (const l of links) {
      const dx = l.target.x - l.source.x;
      const dy = l.target.y - l.source.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const desired = Math.max(55, 110 - l.weight * 8);
      const force = (dist - desired) * .006;
      l.source.vx += (dx / dist) * force;
      l.source.vy += (dy / dist) * force;
      l.target.vx -= (dx / dist) * force;
      l.target.vy -= (dy / dist) * force;
    }
    for (const n of nodes) {
      n.vx += (width / 2 - n.x) * .002;
      n.vy += (height / 2 - n.y) * .002;
      n.x = clamp(n.x + n.vx, 20, width - 20);
      n.y = clamp(n.y + n.vy, 20, height - 20);
      n.vx *= .82;
      n.vy *= .82;
    }
  }

  for (const l of links) {
    const line = document.createElementNS(svgNS, 'line');
    line.setAttribute('x1', l.source.x);
    line.setAttribute('y1', l.source.y);
    line.setAttribute('x2', l.target.x);
    line.setAttribute('y2', l.target.y);
    line.setAttribute('class', 'network-link');
    line.setAttribute('stroke-width', Math.max(1, Math.min(8, Math.sqrt(l.weight))));
    svg.appendChild(line);
  }

  for (const n of nodes) {
    const circle = document.createElementNS(svgNS, 'circle');
    circle.setAttribute('cx', n.x);
    circle.setAttribute('cy', n.y);
    circle.setAttribute('r', n.group === 'group' ? 13 : 8);
    circle.setAttribute('class', `network-node ${n.group}`);
    circle.addEventListener('click', () => showNodeDetails(detailsEl, n));
    svg.appendChild(circle);
    if (n.group === 'group' || n.works >= 2) {
      const text = document.createElementNS(svgNS, 'text');
      text.setAttribute('x', n.x + 12);
      text.setAttribute('y', n.y + 4);
      text.setAttribute('class', 'network-label');
      text.textContent = shortName(n.name);
      svg.appendChild(text);
    }
  }
}

function showNodeDetails(detailsEl, node) {
  const typeLabel = node.group === 'group'
    ? 'Pessoa do grupo'
    : (node.group === 'external-international' ? 'Coautor externo internacional' : 'Coautor externo nacional');
  const ids = Array.isArray(node.aliases) && node.aliases.length ? node.aliases : [node.id];
  const institutions = Array.isArray(node.institutions) ? node.institutions : [];
  const publications = Array.isArray(node.publications) ? node.publications : [];

  const institutionBlock = institutions.length
    ? `<ul class="node-institution-list">${institutions.map((inst) => `<li><strong>${html(inst.name || 'Instituição não identificada')}</strong><span>${html(inst.country || 'País não identificado')}${Number.isFinite(inst.count) ? ` · ${inst.count} publicação${inst.count === 1 ? '' : 'ões'}` : ''}</span></li>`).join('')}</ul>`
    : '<p class="rank-meta">Nenhuma instituição identificada nas autorias carregadas.</p>';

  const publicationBlock = publications.length
    ? `<div class="node-publication-list">${publications.map((work) => {
        const title = work.doi
          ? `<a href="${html(normalizeDoiUrl(work.doi))}" target="_blank" rel="noopener noreferrer">${html(work.title || 'Título não informado')}</a>`
          : `<strong>${html(work.title || 'Título não informado')}</strong>`;
        const fwci = work.fwci === null || work.fwci === undefined || work.fwci === '' ? 's/d' : Number(work.fwci).toLocaleString('pt-BR', { maximumFractionDigits: 2 });
        return `<article class="node-publication-item">
          <div>${title}</div>
          <span>${html(work.year || 's/d')} · ${html(work.sourceName || 'Veículo não identificado')} · FWCI ${fwci} · ${(Number(work.citedByCount) || 0).toLocaleString('pt-BR')} citações</span>
        </article>`;
      }).join('')}</div>`
    : '<p class="rank-meta">Nenhuma publicação associada ao nó.</p>';

  detailsEl.innerHTML = `
    <h3>${html(node.name)}</h3>
    <div class="kv-list">
      <div class="kv-row"><span>Tipo</span><strong>${typeLabel}</strong></div>
      <div class="kv-row"><span>País principal</span><strong>${html(node.country || 'Não identificado')}</strong></div>
      <div class="kv-row"><span>Publicações na rede</span><strong>${node.works || 0}</strong></div>
      <div class="kv-row"><span>Citações agregadas</span><strong>${(node.citations || 0).toLocaleString('pt-BR')}</strong></div>
      <div class="kv-row"><span>Instituição principal</span><strong>${html(node.institution || 'Não identificada')}</strong></div>
    </div>
    <h4>${ids.length > 1 ? 'Perfis integrados' : 'ID bibliográfico'}</h4>
    <ul class="merge-alias-list node-id-list">${ids.map((id) => `<li>${html(String(id).split('/').pop())}</li>`).join('')}</ul>
    <h4>Instituições identificadas nas publicações</h4>
    ${institutionBlock}
    <h4>Publicações deste autor na rede</h4>
    ${publicationBlock}
  `;
}

function normalizeDoiUrl(value) {
  const doi = String(value || '').trim();
  if (!doi) return '#';
  if (/^https?:\/\//i.test(doi)) return doi;
  return `https://doi.org/${doi.replace(/^doi:\s*/i, '')}`;
}

function shortName(name) {
  const parts = String(name || '').split(/\s+/).filter(Boolean);
  if (parts.length <= 2) return parts.join(' ');
  return `${parts[0]} ${parts[parts.length - 1]}`;
}

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}
