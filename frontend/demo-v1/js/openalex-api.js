import { state, addLog } from './store.js';

export function shortOpenAlexId(id) {
  return String(id || '').split('/').pop();
}

function endpointUrl(endpoint) {
  if (/^https?:\/\//i.test(endpoint)) return new URL(endpoint);
  return new URL(`${state.config.openAlex.baseUrl}${endpoint}`);
}

function withCommonParams(url) {
  const { apiKey, mailto } = state.config.openAlex;
  if (apiKey) url.searchParams.set('api_key', apiKey);
  if (mailto) url.searchParams.set('mailto', mailto);
  return url;
}

async function requestJson(endpoint, params = {}) {
  const url = endpointUrl(endpoint);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
  }
  withCommonParams(url);
  const res = await fetch(url.toString(), { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    let body = '';
    try { body = await res.text(); } catch (error) { body = ''; }
    throw new Error(`Endpoint retornou HTTP ${res.status}. ${body.slice(0, 180)}`);
  }
  return res.json();
}

export async function testConnection() {
  const data = await requestJson(state.config.openAlex.authorsEndpoint, {
    search: 'websensors',
    'per-page': 1
  });
  return data?.meta || {};
}

export async function searchAuthors(query) {
  const data = await requestJson(state.config.openAlex.authorsEndpoint, {
    search: query,
    'per-page': 20,
    select: 'id,display_name,orcid,works_count,cited_by_count,last_known_institutions,summary_stats,ids,affiliations'
  });
  const results = Array.isArray(data?.results) ? data.results : [];
  return results.map(normalizeAuthor);
}

function normalizeAuthor(author) {
  const institutions = normalizeAuthorInstitutions(author);
  const inst = institutions[0] || null;
  return {
    id: author.id,
    shortId: shortOpenAlexId(author.id),
    queryIds: [author.id],
    display_name: author.display_name || 'Autor sem nome',
    orcid: author.orcid || author.ids?.orcid || '',
    works_count: author.works_count || 0,
    cited_by_count: author.cited_by_count || 0,
    h_index: author.summary_stats?.h_index || null,
    i10_index: author.summary_stats?.i10_index || null,
    institution_name: inst?.display_name || 'Instituição não identificada',
    institution_country: inst?.country_code || '',
    institutions,
    merged: false,
    raw: author
  };
}

function normalizeAuthorInstitutions(author) {
  const map = new Map();
  for (const inst of author.last_known_institutions || []) addInst(map, inst);
  for (const aff of author.affiliations || []) addInst(map, aff.institution);
  return Array.from(map.values());
}

function addInst(map, inst) {
  if (!inst) return;
  const key = inst.id || `${inst.display_name || 'instituicao'}-${inst.country_code || ''}`;
  if (!key || map.has(key)) return;
  map.set(key, {
    id: inst.id || key,
    display_name: inst.display_name || 'Instituição não identificada',
    country_code: String(inst.country_code || '').toUpperCase(),
    type: inst.type || ''
  });
}

export async function fetchWorksForAuthor(author, startYear, endYear, onProgress = () => {}) {
  const { worksEndpoint, perPage, maxPagesPerAuthor, requestDelayMs } = state.config.openAlex;
  const authorKey = shortOpenAlexId(author.id);
  const filter = [
    `authorships.author.id:${authorKey}`,
    `from_publication_date:${startYear}-01-01`,
    `to_publication_date:${endYear}-12-31`
  ].join(',');
  let cursor = '*';
  const all = [];

  for (let page = 1; page <= maxPagesPerAuthor; page += 1) {
    onProgress({ author, page, total: all.length, phase: 'works' });
    const data = await requestJson(worksEndpoint, { filter, 'per-page': perPage, cursor });
    const results = Array.isArray(data?.results) ? data.results : [];
    for (const work of results) {
      work.__queriedAuthorId = author.id;
      all.push(work);
    }
    cursor = data?.meta?.next_cursor;
    if (!cursor || results.length === 0) break;
    await sleep(requestDelayMs);
  }
  addLog(`${author.display_name}: ${all.length} publicações carregadas.`);
  return all;
}

export async function identifyCoauthorNationalities(works, groupAuthors, countryBrazil = 'BR', onProgress = () => {}) {
  const { nationalityRecentWorks = 10, nationalityConcurrency = 4, requestDelayMs = 250 } = state.config.openAlex;
  const baseCountry = String(countryBrazil || 'BR').toUpperCase();
  const groupIds = new Set();
  for (const author of groupAuthors || []) {
    for (const id of [...(author.queryIds || []), author.id].filter(Boolean)) {
      groupIds.add(id);
      groupIds.add(shortOpenAlexId(id));
    }
  }

  const targets = new Map();
  for (const work of works || []) {
    for (const author of work.authors || []) {
      if (!author?.id) continue;
      if (groupIds.has(author.id) || groupIds.has(shortOpenAlexId(author.id))) continue;
      if (!targets.has(author.id)) targets.set(author.id, { id: author.id, name: author.name || 'Coautor sem nome' });
    }
  }

  const authors = Array.from(targets.values());
  const profiles = { ...(state.authorCountryProfiles || {}) };
  const endpointFingerprint = String(state.config.openAlex.baseUrl || '');
  let loaded = 0;

  const pending = authors.filter((author) => {
    const cached = profiles[author.id];
    if (!cached) return true;
    if (cached.endpoint !== endpointFingerprint) return true;
    if (Number(cached.requestedWorks) !== Number(nationalityRecentWorks)) return true;
    if (String(cached.baseCountry || '').toUpperCase() !== baseCountry) return true;
    return !cached.primaryCountry;
  });

  loaded = authors.length - pending.length;
  onProgress({ loaded, total: authors.length, author: null, cached: loaded });

  for (let offset = 0; offset < pending.length; offset += nationalityConcurrency) {
    const batch = pending.slice(offset, offset + nationalityConcurrency);
    const results = await Promise.all(batch.map(async (author) => {
      try {
        const recentWorks = await fetchRecentWorksForNationality(author.id, nationalityRecentWorks);
        const recentProfile = estimateAuthorCountryProfileFromWorks(author.id, recentWorks, baseCountry);
        const fallbackProfile = recentProfile.primaryCountry
          ? null
          : estimateAuthorCountryProfileFromLoadedWorks(author.id, works, baseCountry);
        const profile = recentProfile.primaryCountry ? recentProfile : fallbackProfile;
        return {
          author,
          profile: {
            ...profile,
            authorName: author.name,
            endpoint: endpointFingerprint,
            baseCountry,
            requestedWorks: nationalityRecentWorks,
            resolvedAt: new Date().toISOString(),
            source: recentProfile.primaryCountry ? 'recent_works' : 'loaded_works_fallback'
          }
        };
      } catch (error) {
        const fallback = estimateAuthorCountryProfileFromLoadedWorks(author.id, works, baseCountry);
        addLog(`Nacionalidade de ${author.name}: consulta auxiliar falhou (${error.message}). Usando evidências do conjunto carregado.`);
        return {
          author,
          profile: {
            ...fallback,
            authorName: author.name,
            endpoint: endpointFingerprint,
            baseCountry,
            requestedWorks: nationalityRecentWorks,
            resolvedAt: new Date().toISOString(),
            source: 'loaded_works_fallback',
            error: error.message
          }
        };
      }
    }));

    for (const { author, profile } of results) {
      profiles[author.id] = profile;
      loaded += 1;
      onProgress({ loaded, total: authors.length, author, profile, cached: authors.length - pending.length });
    }
    if (offset + nationalityConcurrency < pending.length) await sleep(requestDelayMs);
  }

  state.authorCountryProfiles = profiles;
  const resolved = authors.filter((author) => profiles[author.id]?.primaryCountry).length;
  addLog(`Identificação de nacionalidade concluída para ${resolved}/${authors.length} coautores externos.`);
  return profiles;
}

async function fetchRecentWorksForNationality(authorId, limit) {
  const { worksEndpoint } = state.config.openAlex;
  const params = {
    filter: `authorships.author.id:${shortOpenAlexId(authorId)}`,
    sort: '-publication_date',
    'per-page': limit,
    select: 'id,publication_date,authorships'
  };
  try {
    const data = await requestJson(worksEndpoint, params);
    return Array.isArray(data?.results) ? data.results.slice(0, limit) : [];
  } catch (error) {
    // Alguns endpoints compatíveis podem não aceitar select. Repetir sem projeção.
    const data = await requestJson(worksEndpoint, {
      filter: params.filter,
      sort: params.sort,
      'per-page': limit
    });
    return Array.isArray(data?.results) ? data.results.slice(0, limit) : [];
  }
}

export function estimateAuthorCountryProfileFromWorks(authorId, recentWorks, baseCountry = 'BR') {
  const target = shortOpenAlexId(authorId);
  const countryCounts = new Map();
  const institutionCounts = new Map();
  let evidenceWorks = 0;

  for (const work of recentWorks || []) {
    const authorship = (work?.authorships || []).find((item) => shortOpenAlexId(item?.author?.id) === target);
    if (!authorship) continue;
    evidenceWorks += 1;
    const countriesInWork = new Set([
      ...(authorship.countries || []),
      ...(authorship.institutions || []).map((inst) => inst?.country_code)
    ].map((country) => String(country || '').toUpperCase()).filter(Boolean));
    for (const country of countriesInWork) countryCounts.set(country, (countryCounts.get(country) || 0) + 1);

    for (const inst of authorship.institutions || []) {
      const country = String(inst?.country_code || '').toUpperCase();
      const name = String(inst?.display_name || '').trim();
      if (!name && !country) continue;
      const key = inst?.id || `${name}-${country}`;
      const current = institutionCounts.get(key) || { id: inst?.id || '', name: name || 'Instituição não identificada', country, count: 0 };
      current.count += 1;
      institutionCounts.set(key, current);
    }
  }

  const normalizedBaseCountry = String(baseCountry || 'BR').toUpperCase();
  const countries = Array.from(countryCounts.entries())
    .map(([country, count]) => ({ country, count }))
    .sort((a, b) => {
      if (b.count !== a.count) return b.count - a.count;
      if (a.country === normalizedBaseCountry && b.country !== normalizedBaseCountry) return -1;
      if (b.country === normalizedBaseCountry && a.country !== normalizedBaseCountry) return 1;
      return a.country.localeCompare(b.country);
    });
  const primaryCountry = choosePrimaryCountryForProfile(countryCounts, baseCountry);
  const institutions = Array.from(institutionCounts.values())
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  const primaryInstitution = institutions.find((inst) => inst.country === primaryCountry) || institutions[0] || null;

  return {
    authorId,
    primaryCountry,
    countries,
    institutions,
    primaryInstitution,
    evidenceWorks
  };
}

function estimateAuthorCountryProfileFromLoadedWorks(authorId, works, baseCountry = 'BR') {
  const target = shortOpenAlexId(authorId);
  const pseudoWorks = [];
  for (const work of works || []) {
    const author = (work.authors || []).find((item) => shortOpenAlexId(item?.id) === target);
    if (!author) continue;
    pseudoWorks.push({
      authorships: [{
        author: { id: author.id },
        countries: author.countries || [],
        institutions: (author.institutions || []).map((inst) => ({
          id: inst.id,
          display_name: inst.name,
          country_code: inst.country
        }))
      }]
    });
  }
  return estimateAuthorCountryProfileFromWorks(authorId, pseudoWorks, baseCountry);
}

function choosePrimaryCountryForProfile(counts, baseCountry = 'BR') {
  const base = String(baseCountry || 'BR').toUpperCase();
  return Array.from((counts || new Map()).entries())
    .map(([country, count]) => ({ country: String(country || '').toUpperCase(), count: Number(count) || 0 }))
    .filter((row) => row.country)
    .sort((a, b) => {
      if (b.count !== a.count) return b.count - a.count;
      if (a.country === base && b.country !== base) return -1;
      if (b.country === base && a.country !== base) return 1;
      return a.country.localeCompare(b.country);
    })[0]?.country || '';
}

export async function hydrateMissingProceedingsMetrics(worksByAuthor, normalizedWorks, onProgress = () => {}) {
  const { worksEndpoint, requestDelayMs } = state.config.openAlex;
  const targets = Array.from(new Map(
    (normalizedWorks || [])
      .filter((work) => work?.id && work?.fwci === null && /proceedings|conference/i.test(String(work?.rawType || work?.type || '')))
      .map((work) => [work.id, work])
  ).values());

  const maxHydration = Math.min(targets.length, 80);
  let recovered = 0;
  for (let index = 0; index < maxHydration; index += 1) {
    const work = targets[index];
    const shortId = shortOpenAlexId(work.id);
    onProgress({ loaded: index, total: maxHydration, work });
    try {
      const detail = await requestJson(`${worksEndpoint}/${encodeURIComponent(shortId)}`);
      if (detail && typeof detail === 'object') {
        mergeDetailedWorkIntoCollections(worksByAuthor, work.id, detail);
        if (metricNumberFromPayload(detail, 'fwci') !== null) recovered += 1;
      }
    } catch (error) {
      addLog(`Não foi possível recuperar métricas completas de ${shortId}: ${error.message}`);
    }
    onProgress({ loaded: index + 1, total: maxHydration, work });
    await sleep(requestDelayMs);
  }
  if (targets.length > maxHydration) {
    addLog(`${targets.length - maxHydration} trabalhos sem FWCI não foram reconsultados para limitar chamadas adicionais.`);
  }
  if (recovered) addLog(`FWCI recuperado em consulta individual para ${recovered} trabalho(s) de conferência.`);
  return recovered;
}

function mergeDetailedWorkIntoCollections(worksByAuthor, workId, detail) {
  let found = false;
  for (const works of Object.values(worksByAuthor || {})) {
    if (!Array.isArray(works)) continue;
    for (let i = 0; i < works.length; i += 1) {
      const raw = unwrapRawWork(works[i]);
      if (sameWork(raw, workId, detail)) {
        works[i] = mergeRawWork(raw, detail);
        found = true;
      }
    }
  }
  if (!found) {
    const firstList = Object.values(worksByAuthor || {}).find(Array.isArray);
    if (firstList) firstList.push(detail);
  }
}

function unwrapRawWork(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
  if ('id' in value || 'doi' in value || 'fwci' in value || 'primary_location' in value) return value;
  for (const key of ['work', 'result', 'record', 'data', 'attributes']) {
    const nested = value[key];
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) return unwrapRawWork(nested);
  }
  return value;
}

function sameWork(raw, workId, detail) {
  if (!raw || typeof raw !== 'object') return false;
  if (raw.id && raw.id === workId) return true;
  if (detail?.doi && raw.doi && String(detail.doi).toLowerCase() === String(raw.doi).toLowerCase()) return true;
  return false;
}

function mergeRawWork(base, detail) {
  const merged = { ...(base || {}), ...(detail || {}) };
  for (const key of ['primary_location', 'open_access', 'ids', 'citation_normalized_percentile', 'primary_topic']) {
    merged[key] = { ...((base || {})[key] || {}), ...((detail || {})[key] || {}) };
  }
  if (Array.isArray(detail?.authorships) && detail.authorships.length) merged.authorships = detail.authorships;
  if (Array.isArray(detail?.topics) && detail.topics.length) merged.topics = detail.topics;
  if (Array.isArray(detail?.locations) && detail.locations.length) merged.locations = detail.locations;
  return merged;
}

function metricNumberFromPayload(value, wantedKey, depth = 0, seen = new Set()) {
  if (!value || typeof value !== 'object' || depth > 5 || seen.has(value)) return null;
  seen.add(value);
  for (const [key, nested] of Object.entries(value)) {
    if (String(key).toLowerCase() === wantedKey.toLowerCase()) {
      if (typeof nested === 'number' && Number.isFinite(nested)) return nested;
      if (typeof nested === 'string' && Number.isFinite(Number(nested))) return Number(nested);
      if (nested && typeof nested === 'object') {
        const candidate = nested.value ?? nested.score ?? nested.mean ?? nested.average;
        if (candidate !== undefined && Number.isFinite(Number(candidate))) return Number(candidate);
      }
    }
  }
  for (const nested of Object.values(value)) {
    if (nested && typeof nested === 'object') {
      const found = metricNumberFromPayload(nested, wantedKey, depth + 1, seen);
      if (found !== null) return found;
    }
  }
  return null;
}

export async function enrichSources(works, onProgress = () => {}) {
  const { sourcesEndpoint, requestDelayMs, maxSourcesToEnrich } = state.config.openAlex;
  const ids = Array.from(new Set(works.map(getSourceId).filter(Boolean))).slice(0, maxSourcesToEnrich);
  let loaded = 0;
  for (const id of ids) {
    if (state.sourceCache[id]) {
      loaded += 1;
      onProgress({ loaded, total: ids.length, sourceId: id, cached: true });
      continue;
    }
    const shortId = shortOpenAlexId(id);
    try {
      const data = await requestJson(`${sourcesEndpoint}/${encodeURIComponent(shortId)}`);
      state.sourceCache[id] = data;
    } catch (error) {
      state.sourceCache[id] = { id, error: error.message };
      addLog(`Falha ao enriquecer veículo ${shortId}: ${error.message}`);
    }
    loaded += 1;
    onProgress({ loaded, total: ids.length, sourceId: id, cached: false });
    await sleep(requestDelayMs);
  }
  return state.sourceCache;
}

function getSourceId(work) {
  if (work?.sourceId) return work.sourceId;
  const primary = work?.primary_location?.source || null;
  const sources = [primary, ...(work?.locations || []).map((location) => location?.source)].filter(Boolean);
  const preferredTypes = new Set(['journal', 'conference', 'book series', 'ebook platform']);
  const preferred = sources.find((source) => preferredTypes.has(String(source?.type || '').toLowerCase()));
  return preferred?.id || primary?.id || sources[0]?.id || '';
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, Number(ms) || 0));
}
