import { shortOpenAlexId } from './openalex-api.js';

export const CATEGORY_META = {
  national_only: {
    label: 'Apenas nacional',
    icon: '🇧🇷',
    description: 'Todos os coautores com país principal identificado são nacionais.'
  },
  international: {
    label: 'Internacional',
    icon: '🇧🇷 + 🌍',
    description: 'Há pelo menos um coautor cujo país principal é estrangeiro.'
  }
};

export function consolidateWorks(worksByAuthor, groupAuthors, sourceCache, countryBrazil = 'BR', authorCountryProfiles = {}) {
  const aliases = buildGroupAliasMap(groupAuthors);
  const byId = new Map();

  for (const [groupAuthorId, works] of Object.entries(worksByAuthor || {})) {
    for (const rawInput of works || []) {
      const raw = unwrapWorkRecord(rawInput);
      if (!raw || typeof raw !== 'object') continue;
      const id = raw.id || raw.doi || `${raw.display_name || raw.title}-${raw.publication_year}`;
      const candidate = normalizeWork(raw, aliases, sourceCache, countryBrazil);
      if (!byId.has(id)) byId.set(id, candidate);
      else mergeNormalizedWork(byId.get(id), candidate);
      const item = byId.get(id);
      if (aliases.has(groupAuthorId)) item.groupAuthorIds.add(aliases.get(groupAuthorId));
      else if (groupAuthors.some((a) => a.id === groupAuthorId)) item.groupAuthorIds.add(groupAuthorId);
      for (const found of getGroupAuthorsInWork(raw, aliases)) item.groupAuthorIds.add(found.groupId);
    }
  }

  const consolidated = Array.from(byId.values()).map((work) => ({
    ...work,
    groupAuthorIds: Array.from(work.groupAuthorIds)
  }));

  // Regra global de nacionalidade: resolver uma única vez o país principal de cada autor
  // e reaplicar a mesma classificação em todas as telas e métricas.
  return applyGlobalAuthorCountryRules(consolidated, groupAuthors, countryBrazil, authorCountryProfiles);
}

export function buildGroupAliasMap(groupAuthors = []) {
  const aliases = new Map();
  for (const author of groupAuthors) {
    const ids = Array.isArray(author.queryIds) && author.queryIds.length ? author.queryIds : [author.id];
    for (const id of ids.filter(Boolean)) aliases.set(id, author.id);
    aliases.set(author.id, author.id);
  }
  return aliases;
}

function normalizeWork(raw, aliases, sourceCache, countryBrazil) {
  const source = getSource(raw);
  const sourceCacheItem = source?.id ? sourceCache?.[source.id] : null;
  const sourceStats = sourceCacheItem?.summary_stats || source?.summary_stats || {};
  const countryInfo = classifyInternationalization(raw, countryBrazil);
  const groupAuthorsInWork = getGroupAuthorsInWork(raw, aliases);
  const topicInfo = normalizeTopicInfo(raw);
  const openAccessInfo = normalizeOpenAccess(raw);

  return {
    id: raw.id || '',
    shortId: shortOpenAlexId(raw.id),
    title: raw.title || raw.display_name || 'Título não informado',
    year: raw.publication_year || null,
    publicationDate: raw.publication_date || '',
    type: normalizeWorkType(raw),
    rawType: raw?.primary_location?.raw_type || raw?.type_crossref || raw?.type || '',
    sourceType: source?.type || inferSourceTypeFromRawType(raw?.primary_location?.raw_type) || 'não informado',
    doi: raw.doi || raw.ids?.doi || '',
    externalUrl: raw.id || '',
    citedByCount: numberOrNull(raw.cited_by_count),
    fwci: extractFwci(raw),
    citationPercentile: normalizePercentile(raw.citation_normalized_percentile),
    top10: Boolean(raw.citation_normalized_percentile?.is_in_top_10_percent),
    top1: Boolean(raw.citation_normalized_percentile?.is_in_top_1_percent),
    sourceId: source?.id || '',
    sourceName: source?.display_name || 'Veículo não identificado',
    sourceImpact: numberOrNull(sourceStats?.['2yr_mean_citedness']),
    sourceHIndex: numberOrNull(sourceStats?.h_index),
    isOpenAccess: openAccessInfo.isOpenAccess,
    openAccessStatus: openAccessInfo.status,
    authors: normalizeAuthors(raw.authorships),
    groupAuthorsInWork,
    groupAuthorIds: new Set(groupAuthorsInWork.map((a) => a.groupId)),
    countries: countryInfo.countries,
    baseCountry: countryInfo.baseCountry,
    hasBaseCountry: countryInfo.hasBaseCountry,
    brazilInstitutionCount: countryInfo.baseInstitutionCount,
    foreignInstitutionCount: countryInfo.foreignInstitutionCount,
    institutions: countryInfo.institutions,
    internationalCategory: countryInfo.category,
    internationalLabel: CATEGORY_META[countryInfo.category]?.label || 'Apenas nacional',
    topics: topicInfo.topics,
    primaryTopic: topicInfo.primaryTopic,
    subfield: topicInfo.subfield,
    field: topicInfo.field,
    domain: topicInfo.domain,
    raw
  };
}

function normalizeWorkType(raw) {
  // Para a classificação exibida ao usuário, priorizar o tipo bruto da localização principal.
  // Ele preserva distinções úteis como journal-article, proceedings-article, dissertation etc.
  return raw?.primary_location?.raw_type || raw?.type_crossref || raw?.type || 'tipo não informado';
}

function inferSourceTypeFromRawType(rawType) {
  const value = String(rawType || '').toLowerCase();
  if (value.includes('proceedings') || value.includes('conference')) return 'conference';
  if (value.includes('journal')) return 'journal';
  if (value.includes('book')) return 'book';
  if (value.includes('dissertation') || value.includes('thesis')) return 'thesis';
  if (value.includes('dataset')) return 'dataset';
  return '';
}

function getSource(raw) {
  const primaryLocation = raw?.primary_location || null;
  const primary = primaryLocation?.source || null;
  const sources = [primary, ...(raw?.locations || []).map((l) => l?.source)].filter(Boolean);
  const preferredTypes = new Set(['journal', 'conference', 'book series', 'ebook platform']);
  const found = sources.find((source) => preferredTypes.has(String(source?.type || '').toLowerCase())) || primary || sources[0] || null;
  if (found) return found;
  if (primaryLocation?.raw_source_name) {
    return {
      id: '',
      display_name: primaryLocation.raw_source_name,
      type: inferSourceTypeFromRawType(primaryLocation.raw_type),
      summary_stats: {}
    };
  }
  return null;
}

export function extractFwci(rawInput) {
  // FWCI é uma métrica do Work, independentemente de journal/proceedings/source.
  // Alguns endpoints compatíveis encapsulam o Work ou devolvem representações parciais;
  // por isso primeiro desembrulhamos o registro e depois usamos fallbacks conhecidos e busca profunda.
  const raw = unwrapWorkRecord(rawInput);
  const direct = firstNumber(
    raw?.fwci,
    raw?.metrics?.fwci,
    raw?.summary_stats?.fwci,
    raw?.citation_metrics?.fwci,
    raw?.bibliometrics?.fwci,
    raw?.attributes?.fwci,
    raw?.data?.fwci
  );
  if (direct !== null) return direct;
  return findMetricByKey(raw, 'fwci', 5);
}

function unwrapWorkRecord(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
  if ('id' in value || 'doi' in value || 'fwci' in value || 'primary_location' in value) return value;
  for (const key of ['work', 'result', 'record', 'data', 'attributes']) {
    const nested = value[key];
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      const unwrapped = unwrapWorkRecord(nested);
      if (unwrapped && typeof unwrapped === 'object') return unwrapped;
    }
  }
  return value;
}

function findMetricByKey(value, wantedKey, maxDepth, depth = 0, seen = new Set()) {
  if (!value || typeof value !== 'object' || depth > maxDepth || seen.has(value)) return null;
  seen.add(value);
  for (const [key, nested] of Object.entries(value)) {
    if (String(key).toLowerCase() === wantedKey.toLowerCase()) {
      const parsed = metricNumber(nested);
      if (parsed !== null) return parsed;
    }
  }
  for (const nested of Object.values(value)) {
    if (nested && typeof nested === 'object') {
      const found = findMetricByKey(nested, wantedKey, maxDepth, depth + 1, seen);
      if (found !== null) return found;
    }
  }
  return null;
}

function mergeNormalizedWork(target, candidate) {
  // Não deixar uma representação parcial sobrescrever métricas válidas de outra ocorrência do mesmo Work.
  const prefer = (key) => {
    if (isMissingValue(target[key]) && !isMissingValue(candidate[key])) target[key] = candidate[key];
  };
  for (const key of [
    'title', 'year', 'publicationDate', 'type', 'rawType', 'sourceType', 'doi', 'externalUrl',
    'citedByCount', 'citationPercentile', 'sourceId', 'sourceName', 'sourceImpact', 'sourceHIndex',
    'openAccessStatus', 'primaryTopic', 'subfield', 'field', 'domain'
  ]) prefer(key);

  const candidateFwci = metricNumber(candidate.fwci);
  if (metricNumber(target.fwci) === null && candidateFwci !== null) target.fwci = candidateFwci;
  target.top10 = Boolean(target.top10 || candidate.top10);
  target.top1 = Boolean(target.top1 || candidate.top1);
  target.isOpenAccess = Boolean(target.isOpenAccess || candidate.isOpenAccess);
  target.hasBaseCountry = Boolean(target.hasBaseCountry || candidate.hasBaseCountry);
  target.brazilInstitutionCount = Math.max(Number(target.brazilInstitutionCount) || 0, Number(candidate.brazilInstitutionCount) || 0);
  target.foreignInstitutionCount = Math.max(Number(target.foreignInstitutionCount) || 0, Number(candidate.foreignInstitutionCount) || 0);
  target.countries = unique([...(target.countries || []), ...(candidate.countries || [])]);
  target.authors = mergeObjectsByKey(target.authors, candidate.authors, (a) => a.id || a.name);
  target.institutions = mergeObjectsByKey(target.institutions, candidate.institutions, (i) => i.id || `${i.name}-${i.country}`);
  target.topics = mergeObjectsByKey(target.topics, candidate.topics, (t) => t.id || t.name);
  target.groupAuthorsInWork = mergeObjectsByKey(target.groupAuthorsInWork, candidate.groupAuthorsInWork, (a) => a.groupId || a.id);
  if (candidate.internationalCategory === 'international') {
    target.internationalCategory = 'international';
    target.internationalLabel = CATEGORY_META.international.label;
  }
  if (rawRichness(candidate.raw) > rawRichness(target.raw)) target.raw = candidate.raw;
}

function mergeObjectsByKey(a = [], b = [], keyFn) {
  const map = new Map();
  for (const item of [...(a || []), ...(b || [])]) {
    if (!item) continue;
    const key = keyFn(item);
    if (!map.has(key)) map.set(key, item);
  }
  return Array.from(map.values());
}

function isMissingValue(value) {
  return value === null || value === undefined || value === '' || value === 'Veículo não identificado' || value === 'não informado';
}

function rawRichness(raw) {
  if (!raw || typeof raw !== 'object') return 0;
  let score = Object.keys(raw).length;
  if (extractFwci(raw) !== null) score += 20;
  if (raw.primary_location?.raw_source_name) score += 3;
  if (raw.primary_location?.source) score += 3;
  if (Array.isArray(raw.topics) && raw.topics.length) score += 2;
  return score;
}

function normalizeOpenAccess(raw) {
  const explicit = raw?.open_access?.is_oa;
  const locationValue = raw?.best_oa_location?.is_oa ?? raw?.primary_location?.is_oa;
  const isOpenAccess = typeof explicit === 'boolean' ? explicit : Boolean(locationValue);
  return {
    isOpenAccess,
    status: raw?.open_access?.oa_status || (isOpenAccess ? 'open access' : 'closed')
  };
}

function normalizeAuthors(authorships = []) {
  return (authorships || []).map((a) => ({
    id: a.author?.id || '',
    shortId: shortOpenAlexId(a.author?.id),
    name: a.author?.display_name || 'Autor sem nome',
    position: a.author_position || '',
    countries: unique([...(a.countries || []), ...(a.institutions || []).map((i) => i.country_code)].map((c) => String(c || '').toUpperCase()).filter(Boolean)),
    institutions: (a.institutions || []).map((i) => ({
      id: i.id || '',
      name: i.display_name || '',
      country: String(i.country_code || '').toUpperCase(),
      type: i.type || ''
    }))
  }));
}

function getGroupAuthorsInWork(raw, aliases) {
  return normalizeAuthors(raw.authorships)
    .map((a) => ({ ...a, groupId: aliases.get(a.id) }))
    .filter((a) => a.groupId);
}

function applyGlobalAuthorCountryRules(works, groupAuthors = [], countryBrazil = 'BR', authorCountryProfiles = {}) {
  const baseCountry = String(countryBrazil || 'BR').toUpperCase();
  const aliases = buildGroupAliasMap(groupAuthors);
  const preferredCountryByAuthor = new Map();

  for (const author of groupAuthors || []) {
    const preferred = String(author?.institution_country || '').toUpperCase();
    if (preferred) preferredCountryByAuthor.set(author.id, preferred);
  }

  const countryCounters = new Map();
  for (const work of works || []) {
    for (const author of work.authors || []) {
      if (!author?.id) continue;
      const canonicalId = aliases.get(author.id) || author.id;
      if (!countryCounters.has(canonicalId)) countryCounters.set(canonicalId, new Map());
      const counts = countryCounters.get(canonicalId);
      for (const country of authorCountryCodes(author)) {
        counts.set(country, (counts.get(country) || 0) + 1);
      }
    }
  }

  const lookupCountryByAuthor = new Map();
  for (const [authorId, profile] of Object.entries(authorCountryProfiles || {})) {
    const country = String(profile?.primaryCountry || '').toUpperCase();
    if (!country) continue;
    lookupCountryByAuthor.set(authorId, country);
    lookupCountryByAuthor.set(shortOpenAlexId(authorId), country);
  }

  const profiles = new Map();
  for (const [authorId, counts] of countryCounters.entries()) {
    const preferredCountry = preferredCountryByAuthor.get(authorId) || '';
    const lookupCountry = lookupCountryByAuthor.get(authorId) || lookupCountryByAuthor.get(shortOpenAlexId(authorId)) || '';
    // Autores do grupo usam a instituição escolhida pelo usuário. Coautores externos
    // usam prioritariamente a estimativa obtida nas produções recentes auxiliares.
    const primaryCountry = preferredCountry || lookupCountry || choosePrimaryCountry(counts, baseCountry);
    profiles.set(authorId, {
      primaryCountry,
      isInternational: Boolean(primaryCountry && primaryCountry !== baseCountry),
      countrySource: preferredCountry ? 'group_preference' : (lookupCountry ? 'recent_works' : 'loaded_works')
    });
  }

  return (works || []).map((work) => {
    const affiliationCountries = unique([
      ...(work.affiliationCountries || []),
      ...(work.countries || [])
    ].map((c) => String(c || '').toUpperCase()).filter(Boolean));

    const authors = (work.authors || []).map((author) => {
      const canonicalId = author?.id ? (aliases.get(author.id) || author.id) : '';
      const profile = canonicalId ? profiles.get(canonicalId) : null;
      const lookupCountry = canonicalId
        ? (lookupCountryByAuthor.get(canonicalId) || lookupCountryByAuthor.get(shortOpenAlexId(canonicalId)) || '')
        : '';
      const preferredCountry = canonicalId ? (preferredCountryByAuthor.get(canonicalId) || '') : '';
      const localCountry = choosePrimaryCountry(countMap(authorCountryCodes(author)), baseCountry);
      const primaryCountry = preferredCountry || lookupCountry || profile?.primaryCountry || localCountry || '';
      return {
        ...author,
        canonicalId: canonicalId || author?.id || '',
        primaryCountry,
        countrySource: preferredCountry ? 'group_preference' : (lookupCountry ? 'recent_works' : (profile?.countrySource || 'work_affiliation')),
        isInternational: Boolean(primaryCountry && primaryCountry !== baseCountry)
      };
    });

    const primaryCountries = unique(authors.map((a) => a.primaryCountry).filter(Boolean));
    const internationalAuthors = authors.filter((a) => a.isInternational);
    const category = internationalAuthors.length ? 'international' : 'national_only';

    return {
      ...work,
      authors,
      affiliationCountries,
      countries: primaryCountries,
      hasBaseCountry: primaryCountries.includes(baseCountry),
      internationalCategory: category,
      internationalLabel: CATEGORY_META[category].label,
      nationalCoauthorCount: authors.filter((a) => a.primaryCountry === baseCountry).length,
      internationalCoauthorCount: internationalAuthors.length
    };
  });
}

function authorCountryCodes(author) {
  return unique([
    ...(author?.countries || []),
    ...((author?.institutions || []).map((i) => i?.country))
  ].map((c) => String(c || '').toUpperCase()).filter(Boolean));
}

function countMap(values = []) {
  const map = new Map();
  for (const value of values) map.set(value, (map.get(value) || 0) + 1);
  return map;
}

function choosePrimaryCountry(counts, baseCountry = 'BR', preferredCountry = '') {
  const preferred = String(preferredCountry || '').toUpperCase();
  if (preferred) return preferred;
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

function classifyInternationalization(raw, countryBrazil) {
  const baseCountry = String(countryBrazil || 'BR').toUpperCase();
  const institutionsMap = new Map();
  for (const authorship of raw.authorships || []) {
    for (const inst of authorship.institutions || []) {
      const id = inst.id || `${inst.display_name || 'instituicao'}-${inst.country_code || 'sem-pais'}`;
      institutionsMap.set(id, {
        id,
        name: inst.display_name || 'Instituição sem nome',
        country: String(inst.country_code || '').toUpperCase(),
        type: inst.type || ''
      });
    }
  }
  const institutions = Array.from(institutionsMap.values());
  const authorshipCountries = (raw.authorships || []).flatMap((a) => a.countries || []);
  const countries = unique([
    ...institutions.map((i) => i.country),
    ...authorshipCountries
  ].map((c) => String(c || '').toUpperCase()).filter(Boolean));
  const hasBaseCountry = countries.includes(baseCountry);
  const hasForeign = countries.some((c) => c && c !== baseCountry);
  const baseInstitutionCount = institutions.filter((i) => i.country === baseCountry).length;
  const foreignInstitutionCount = institutions.filter((i) => i.country && i.country !== baseCountry).length;
  const category = hasForeign ? 'international' : 'national_only';
  return { category, countries, institutions, baseCountry, hasBaseCountry, baseInstitutionCount, foreignInstitutionCount };
}

function normalizeTopicInfo(raw) {
  const primary = raw.primary_topic || null;
  const topic = primary ? topicNode(primary, 'topic') : null;
  const subfield = primary?.subfield ? topicNode(primary.subfield, 'subfield') : null;
  const field = primary?.field ? topicNode(primary.field, 'field') : null;
  const domain = primary?.domain ? topicNode(primary.domain, 'domain') : null;
  const topics = Array.isArray(raw.topics) ? raw.topics.map((t) => topicNode(t, 'topic')).filter(Boolean) : [];
  if (topic && !topics.some((t) => t.id === topic.id)) topics.unshift(topic);
  return {
    primaryTopic: topic,
    subfield: subfield || { id: '', name: 'Sem subárea', level: 'subfield' },
    field: field || { id: '', name: 'Sem área', level: 'field' },
    domain: domain || { id: '', name: 'Sem domínio', level: 'domain' },
    topics
  };
}

function topicNode(obj, level) {
  if (!obj) return null;
  return {
    id: obj.id || obj.openalex || obj.wikidata || obj.display_name || '',
    name: obj.display_name || obj.name || 'Sem tópico',
    level,
    score: numberOrNull(obj.score)
  };
}

export function computeMetrics(works) {
  const total = works.length;
  const byYear = groupBy(works.filter((w) => w.year), (w) => w.year);
  const yearSeries = Object.entries(byYear)
    .map(([year, items]) => ({
      year: Number(year),
      publications: items.length,
      citations: sum(items.map((w) => w.citedByCount)),
      avgFwci: mean(items.map((w) => w.fwci)),
      avgSourceImpact: mean(items.map((w) => w.sourceImpact)),
      avgSourceHIndex: mean(items.map((w) => w.sourceHIndex))
    }))
    .sort((a, b) => a.year - b.year);

  const categories = {};
  for (const key of Object.keys(CATEGORY_META)) {
    const items = works.filter((w) => w.internationalCategory === key);
    categories[key] = summarizeGroup(items, total);
  }

  const baseCountry = works[0]?.baseCountry || 'BR';
  const countryCounts = countValues(works.flatMap((w) => foreignCountryCodesForWork(w, baseCountry)));
  const institutionCounts = countInstitutions(works);
  const sourceCounts = countValues(works.map((w) => w.sourceName).filter(Boolean));
  const typeCounts = countValues(works.map((w) => w.type).filter(Boolean));
  const sourceTypeCounts = countValues(works.map((w) => w.sourceType).filter(Boolean));
  const sourceMetrics = summarizeSources(works);

  return {
    total,
    citations: sum(works.map((w) => w.citedByCount)),
    avgCitations: mean(works.map((w) => w.citedByCount)),
    medianCitations: median(works.map((w) => w.citedByCount)),
    avgFwci: mean(works.map((w) => w.fwci)),
    medianFwci: median(works.map((w) => w.fwci)),
    avgSourceImpact: mean(works.map((w) => w.sourceImpact)),
    avgSourceHIndex: mean(works.map((w) => w.sourceHIndex)),
    openAccessShare: ratio(works.filter((w) => w.isOpenAccess === true).length, total),
    hIndex: hIndex(works.map((w) => w.citedByCount)),
    top10Share: ratio(works.filter((w) => isTop10(w)).length, total),
    uniqueSources: new Set(works.map((w) => w.sourceName).filter(Boolean)).size,
    uniqueCountries: new Set(works.flatMap((w) => w.countries)).size,
    yearSeries,
    categories,
    topSources: topN(sourceCounts, 12),
    topSourceMetrics: sourceMetrics.slice(0, 20),
    topCountries: topN(countryCounts, 12),
    allCountries: topN(countryCounts, 250),
    topInstitutions: topInstitutionRows(institutionCounts, 80),
    topTypes: topN(typeCounts, 20),
    topSourceTypes: topN(sourceTypeCounts, 20),
    topWorksByFwci: works.filter((w) => w.fwci !== null).sort((a, b) => b.fwci - a.fwci).slice(0, 10),
    topWorksByCitations: [...works].sort((a, b) => (b.citedByCount || 0) - (a.citedByCount || 0)).slice(0, 10),
    topicSummary: summarizeTopics(works)
  };
}


function foreignCountryCodesForWork(work, baseCountry = 'BR') {
  const base = String(baseCountry || 'BR').toUpperCase();
  // Países do painel de internacionalização seguem a mesma regra dos coautores:
  // usar somente o país principal resolvido de cada autor, nunca uma afiliação secundária isolada.
  const codes = unique((work?.authors || [])
    .map((author) => String(author?.primaryCountry || '').toUpperCase())
    .filter(Boolean));
  return codes.filter((code) => code !== base);
}

function summarizeGroup(items, total) {
  return {
    total: items.length,
    share: ratio(items.length, total),
    citations: sum(items.map((w) => w.citedByCount)),
    avgCitations: mean(items.map((w) => w.citedByCount)),
    avgFwci: mean(items.map((w) => w.fwci)),
    medianFwci: median(items.map((w) => w.fwci)),
    avgSourceImpact: mean(items.map((w) => w.sourceImpact)),
    avgSourceHIndex: mean(items.map((w) => w.sourceHIndex)),
    openAccessShare: ratio(items.filter((w) => w.isOpenAccess === true).length, items.length),
    hIndex: hIndex(items.map((w) => w.citedByCount)),
    top10Share: ratio(items.filter((w) => isTop10(w)).length, items.length),
    years: Object.entries(groupBy(items.filter((w) => w.year), (w) => w.year))
      .map(([year, rows]) => ({ year: Number(year), count: rows.length, avgFwci: mean(rows.map((w) => w.fwci)) }))
      .sort((a, b) => a.year - b.year),
    works: items
  };
}

export function summarizeTopics(works, level = 'topic') {
  const map = new Map();
  for (const work of works) {
    const node = getTopicForLevel(work, level);
    const key = node?.id || `sem-${level}`;
    const name = node?.name || labelForMissingLevel(level);
    if (!map.has(key)) map.set(key, { id: key, label: name, level, works: [] });
    map.get(key).works.push(work);
  }
  return Array.from(map.values())
    .map((row) => ({
      ...row,
      total: row.works.length,
      citations: sum(row.works.map((w) => w.citedByCount)),
      avgCitations: mean(row.works.map((w) => w.citedByCount)),
      avgFwci: mean(row.works.map((w) => w.fwci)),
      medianFwci: median(row.works.map((w) => w.fwci)),
      hIndex: hIndex(row.works.map((w) => w.citedByCount)),
      avgSourceImpact: mean(row.works.map((w) => w.sourceImpact)),
      avgSourceHIndex: mean(row.works.map((w) => w.sourceHIndex)),
      openAccessShare: ratio(row.works.filter((w) => w.isOpenAccess === true).length, row.works.length),
      top10Share: ratio(row.works.filter((w) => isTop10(w)).length, row.works.length),
      typeBreakdown: topN(countValues(row.works.map((w) => w.type)), 5)
    }))
    .sort((a, b) => b.total - a.total || (b.avgFwci || 0) - (a.avgFwci || 0));
}

export function getTopicForLevel(work, level) {
  if (level === 'domain') return work.domain;
  if (level === 'field') return work.field;
  if (level === 'subfield') return work.subfield;
  return work.primaryTopic || { id: '', name: 'Sem tópico', level: 'topic' };
}

function labelForMissingLevel(level) {
  return ({ topic: 'Sem tópico', subfield: 'Sem subárea', field: 'Sem área', domain: 'Sem domínio' })[level] || 'Sem tema';
}

function summarizeSources(works) {
  const map = new Map();
  for (const work of works) {
    const key = work.sourceId || work.sourceName || 'sem-veiculo';
    if (!map.has(key)) {
      map.set(key, {
        id: key,
        label: work.sourceName || 'Veículo não identificado',
        sourceType: work.sourceType || 'não informado',
        works: 0,
        sourceImpactValues: [],
        sourceHIndexValues: []
      });
    }
    const row = map.get(key);
    row.works += 1;
    if (isNumericValue(work.sourceImpact)) row.sourceImpactValues.push(Number(work.sourceImpact));
    if (isNumericValue(work.sourceHIndex)) row.sourceHIndexValues.push(Number(work.sourceHIndex));
  }
  return Array.from(map.values())
    .map((row) => ({
      id: row.id,
      label: row.label,
      sourceType: row.sourceType,
      value: row.works,
      works: row.works,
      sourceImpact: mean(row.sourceImpactValues),
      sourceHIndex: row.sourceHIndexValues.length ? Math.max(...row.sourceHIndexValues) : null
    }))
    .sort((a, b) => b.works - a.works || (b.sourceHIndex || 0) - (a.sourceHIndex || 0));
}

export function buildCollaborationGraph(works, groupAuthors, maxExternal = 80) {
  const aliasMap = buildGroupAliasMap(groupAuthors);
  const groupById = new Map(groupAuthors.map((a) => [a.id, a]));
  const baseCountry = String(works.find((w) => w.baseCountry)?.baseCountry || 'BR').toUpperCase();
  const externalCounts = new Map();

  // Contar somente coautores externos identificáveis. Um ID vazio não pode representar
  // autores diferentes, pois isso produziria nós e arestas falsas entre publicações.
  for (const work of works) {
    const hasGroup = (work.authors || []).some((a) => a?.id && aliasMap.has(a.id));
    if (!hasGroup) continue;
    const seenExternal = new Set();
    for (const author of work.authors || []) {
      if (!author?.id || aliasMap.has(author.id) || seenExternal.has(author.id)) continue;
      seenExternal.add(author.id);
      const current = externalCounts.get(author.id) || { author, count: 0, citations: 0 };
      current.count += 1;
      current.citations += Number(work.citedByCount) || 0;
      externalCounts.set(author.id, current);
    }
  }

  const includedExternal = new Set(Array.from(externalCounts.values())
    .sort((a, b) => b.count - a.count || b.citations - a.citations)
    .slice(0, maxExternal)
    .map((x) => x.author.id));

  const nodesMap = new Map();
  const edgeMap = new Map();

  // Inicializar as pessoas do grupo, inclusive os perfis mesclados.
  for (const author of groupAuthors) {
    nodesMap.set(author.id, createGraphNode({
      id: author.id,
      name: author.display_name,
      group: 'group',
      aliases: author.queryIds || [author.id],
      preferredInstitution: author.institution_name || '',
      preferredCountry: author.institution_country || ''
    }));
  }

  for (const work of works) {
    // Participantes únicos desta publicação. O Map impede arestas duplicadas e self-loops
    // quando dois aliases de um autor mesclado aparecem no mesmo Work.
    const participants = new Map();

    for (const author of work.authors || []) {
      if (!author) continue;
      const groupId = author.id ? aliasMap.get(author.id) : null;

      if (groupId) {
        const groupAuthor = groupById.get(groupId);
        if (!participants.has(groupId)) {
          participants.set(groupId, {
            id: groupId,
            author,
            isGroup: true,
            nodeGroup: 'group',
            name: groupAuthor?.display_name || author.name
          });
        } else {
          mergeParticipantMetadata(participants.get(groupId).author, author);
        }
        continue;
      }

      // Sem ID não há identidade bibliográfica segura para conectar esse autor entre Works.
      if (!author.id || !includedExternal.has(author.id)) continue;
      if (!participants.has(author.id)) {
        participants.set(author.id, {
          id: author.id,
          author,
          isGroup: false,
          nodeGroup: 'external-national',
          name: author.name
        });
      } else {
        mergeParticipantMetadata(participants.get(author.id).author, author);
      }
    }

    const authors = Array.from(participants.values());
    if (!authors.some((a) => a.isGroup)) continue;

    // Atualizar os nós com os metadados da autoria real desta publicação.
    for (const participant of authors) {
      let node = nodesMap.get(participant.id);
      if (!node) {
        node = createGraphNode({
          id: participant.id,
          name: participant.name,
          group: participant.nodeGroup
        });
        nodesMap.set(participant.id, node);
      }
      addAuthorshipToGraphNode(node, participant.author, work, baseCountry);
    }

    // Uma aresta só existe quando os dois autores aparecem juntos nesta publicação.
    for (let i = 0; i < authors.length; i += 1) {
      for (let j = i + 1; j < authors.length; j += 1) {
        const a = authors[i].id;
        const b = authors[j].id;
        if (!a || !b || a === b) continue;
        const [source, target] = [a, b].sort();
        const key = `${source}||${target}`;
        const current = edgeMap.get(key) || { source, target, workIds: new Set(), works: [] };
        if (!current.workIds.has(work.id)) {
          current.workIds.add(work.id);
          current.works.push(work.title);
        }
        edgeMap.set(key, current);
      }
    }
  }

  const nodes = Array.from(nodesMap.values()).map((node) => finalizeGraphNode(node, baseCountry));
  const existingIds = new Set(nodes.map((n) => n.id));
  const links = Array.from(edgeMap.values())
    .filter((edge) => existingIds.has(edge.source) && existingIds.has(edge.target))
    .map(({ workIds, ...edge }) => ({ ...edge, weight: workIds.size }));

  return { nodes, links };
}

function createGraphNode({ id, name, group, aliases = null, preferredInstitution = '', preferredCountry = '' }) {
  return {
    id,
    name: name || 'Autor sem nome',
    group,
    aliases: aliases || [id],
    preferredInstitution,
    preferredCountry: String(preferredCountry || '').toUpperCase(),
    institutionCounts: new Map(),
    countryCounts: new Map(),
    publicationMap: new Map()
  };
}

function mergeParticipantMetadata(target, source) {
  if (!target || !source) return;
  target.countries = unique([...(target.countries || []), ...(source.countries || [])]);
  target.institutions = mergeObjectsByKey(target.institutions, source.institutions, (i) => i.id || `${i.name}-${i.country}`);
}

function addAuthorshipToGraphNode(node, author, work, baseCountry) {
  for (const inst of author?.institutions || []) {
    const name = String(inst?.name || '').trim();
    const country = String(inst?.country || '').toUpperCase();
    if (!name && !country) continue;
    const key = inst?.id || `${name}-${country}`;
    const current = node.institutionCounts.get(key) || { id: inst?.id || '', name: name || 'Instituição não identificada', country, count: 0 };
    current.count += 1;
    node.institutionCounts.set(key, current);
  }

  // O grafo consome o país principal já resolvido globalmente. Isso mantém a mesma
  // classificação usada no dashboard, no mapa e nas tabelas.
  const primaryCountry = String(author?.primaryCountry || '').toUpperCase();
  if (primaryCountry) {
    node.countryCounts.set(primaryCountry, (node.countryCounts.get(primaryCountry) || 0) + 1);
  } else {
    for (const country of authorCountryCodes(author)) {
      node.countryCounts.set(country, (node.countryCounts.get(country) || 0) + 1);
    }
  }

  if (!node.publicationMap.has(work.id)) {
    node.publicationMap.set(work.id, {
      id: work.id,
      title: work.title,
      year: work.year,
      doi: work.doi || '',
      fwci: work.fwci,
      citedByCount: work.citedByCount,
      sourceName: work.sourceName || '',
      type: work.type || '',
      internationalCategory: work.internationalCategory || '',
      baseCountry
    });
  }
}

function finalizeGraphNode(node, baseCountry) {
  const normalizedBaseCountry = String(baseCountry || 'BR').toUpperCase();
  const institutions = Array.from(node.institutionCounts.values())
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  const countries = Array.from(node.countryCounts.entries())
    .map(([country, count]) => ({ country, count }))
    .sort((a, b) => {
      if (b.count !== a.count) return b.count - a.count;
      // Em empate de frequência, priorizar o país-base. Isso evita classificar como
      // internacional um coautor cuja atuação principal continua sendo brasileira.
      if (a.country === normalizedBaseCountry && b.country !== normalizedBaseCountry) return -1;
      if (b.country === normalizedBaseCountry && a.country !== normalizedBaseCountry) return 1;
      return a.country.localeCompare(b.country);
    });
  const publications = Array.from(node.publicationMap.values())
    .sort((a, b) => (b.year || 0) - (a.year || 0) || String(a.title).localeCompare(String(b.title)));

  const normalizedPreferredCountry = String(node.preferredCountry || '').toUpperCase();
  const primaryCountry = normalizedPreferredCountry || countries[0]?.country || '';

  let primaryInstitution = null;
  if (node.preferredInstitution) {
    primaryInstitution = {
      name: node.preferredInstitution,
      country: normalizedPreferredCountry,
      count: Number.MAX_SAFE_INTEGER
    };
  } else if (primaryCountry) {
    // A instituição principal deve ser coerente com o país principal do autor.
    primaryInstitution = institutions
      .filter((inst) => String(inst.country || '').toUpperCase() === primaryCountry)
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))[0] || institutions[0] || null;
  } else {
    primaryInstitution = institutions[0] || null;
  }

  // A classificação do coautor usa exclusivamente o país principal resolvido.
  // País principal BR => coautor nacional, mesmo que existam afiliações secundárias
  // ou publicações pontuais associadas a instituições de outros países.
  const resolvedGroup = node.group === 'group'
    ? 'group'
    : (primaryCountry && primaryCountry !== normalizedBaseCountry
      ? 'external-international'
      : 'external-national');

  return {
    id: node.id,
    name: node.name,
    group: resolvedGroup,
    aliases: node.aliases,
    works: publications.length,
    citations: publications.reduce((sum, p) => sum + (Number(p.citedByCount) || 0), 0),
    institution: primaryInstitution?.name || '',
    country: primaryCountry,
    institutions,
    countries,
    publications
  };
}

function isInternationalAuthor(author, baseCountry) {
  const base = String(baseCountry || 'BR').toUpperCase();
  const primary = String(author?.primaryCountry || '').toUpperCase();
  if (primary) return primary !== base;
  return choosePrimaryCountry(countMap(authorCountryCodes(author)), base) !== base;
}

function countInstitutions(works) {
  const map = new Map();
  for (const work of works) {
    const seen = new Set();
    for (const inst of work.institutions || []) {
      const key = inst.id || `${inst.name}-${inst.country}`;
      if (!key || seen.has(key)) continue;
      seen.add(key);
      const current = map.get(key) || {
        id: key,
        label: inst.name || 'Instituição sem nome',
        country: inst.country || '',
        scope: inst.country && inst.country !== work.baseCountry ? 'international' : 'national',
        value: 0
      };
      current.value += 1;
      map.set(key, current);
    }
  }
  return map;
}

function topInstitutionRows(map, n) {
  return Array.from(map.values())
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label))
    .slice(0, n);
}

function metricNumber(value) {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const direct = Number(trimmed);
    if (Number.isFinite(direct)) return direct;
    if (/^-?\d+,\d+$/.test(trimmed)) {
      const decimalComma = Number(trimmed.replace(',', '.'));
      return Number.isFinite(decimalComma) ? decimalComma : null;
    }
    return null;
  }
  if (typeof value === 'object') {
    for (const key of ['value', 'score', 'mean', 'average']) {
      const parsed = metricNumber(value?.[key]);
      if (parsed !== null) return parsed;
    }
  }
  return null;
}

function isNumericValue(value) {
  return metricNumber(value) !== null;
}

function numberOrNull(value) {
  return metricNumber(value);
}

function firstNumber(...values) {
  for (const value of values) {
    const parsed = metricNumber(value);
    if (parsed !== null) return parsed;
  }
  return null;
}

function normalizePercentile(obj) {
  const v = Number(obj?.value);
  if (!Number.isFinite(v)) return null;
  return v > 1 ? v / 100 : v;
}

function isTop10(work) {
  if (work.top10) return true;
  if (work.citationPercentile === null) return false;
  return work.citationPercentile >= 0.9;
}

export function mean(values) {
  const nums = values.filter(isNumericValue).map(Number);
  return nums.length ? sum(nums) / nums.length : null;
}

export function median(values) {
  const nums = values.filter(isNumericValue).map(Number).sort((a, b) => a - b);
  if (!nums.length) return null;
  const mid = Math.floor(nums.length / 2);
  return nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
}

export function sum(values) {
  return values.filter(isNumericValue).reduce((acc, v) => acc + Number(v), 0);
}

export function ratio(part, total) {
  return total ? part / total : 0;
}

export function hIndex(values) {
  const nums = values.filter(isNumericValue).map(Number).sort((a, b) => b - a);
  let h = 0;
  for (let i = 0; i < nums.length; i += 1) {
    if (nums[i] >= i + 1) h = i + 1;
    else break;
  }
  return h;
}

function groupBy(items, keyFn) {
  return items.reduce((acc, item) => {
    const key = keyFn(item);
    acc[key] = acc[key] || [];
    acc[key].push(item);
    return acc;
  }, {});
}

function countValues(values) {
  const map = new Map();
  for (const value of values) {
    if (!value) continue;
    map.set(value, (map.get(value) || 0) + 1);
  }
  return map;
}

function topN(map, n) {
  return Array.from(map.entries())
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value || String(a.label).localeCompare(String(b.label)))
    .slice(0, n);
}

function unique(values) {
  return Array.from(new Set(values));
}
