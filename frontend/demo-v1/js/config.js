export const DEFAULT_CONFIG = {
  systemName: 'Science Metrics',
  logoUrl: 'https://websensors.icmc.usp.br/assets/img/logo.png',
  openAlex: {
    baseUrl: 'https://api.openalex.org',
    authorsEndpoint: '/authors',
    worksEndpoint: '/works',
    sourcesEndpoint: '/sources',
    apiKey: '',
    mailto: '',
    perPage: 200,
    maxPagesPerAuthor: 10,
    requestDelayMs: 250,
    maxSourcesToEnrich: 150,
    maxExternalCoauthors: 80,
    nationalityRecentWorks: 10,
    nationalityConcurrency: 4
  },
  defaults: {
    startYear: 2020,
    endYear: new Date().getFullYear(),
    countryBrazil: 'BR'
  }
};

const CONFIG_KEY = 'wsm.runtimeConfig';

function deepMerge(base, override) {
  const out = Array.isArray(base) ? [...base] : { ...base };
  for (const [key, value] of Object.entries(override || {})) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      out[key] = deepMerge(base?.[key] || {}, value);
    } else if (value !== undefined && value !== null) {
      out[key] = value;
    }
  }
  return out;
}

function normalizeConfig(cfg) {
  const merged = deepMerge(DEFAULT_CONFIG, cfg || {});
  const oa = merged.openAlex;
  oa.baseUrl = stripTrailingSlashes(String(oa.baseUrl || DEFAULT_CONFIG.openAlex.baseUrl));
  oa.authorsEndpoint = normalizeEndpoint(oa.authorsEndpoint, '/authors');
  oa.worksEndpoint = normalizeEndpoint(oa.worksEndpoint, '/works');
  oa.sourcesEndpoint = normalizeEndpoint(oa.sourcesEndpoint, '/sources');
  oa.perPage = clampNumber(oa.perPage, 25, 200, 200);
  oa.maxPagesPerAuthor = clampNumber(oa.maxPagesPerAuthor, 1, 50, 10);
  oa.requestDelayMs = clampNumber(oa.requestDelayMs, 0, 5000, 250);
  oa.maxSourcesToEnrich = clampNumber(oa.maxSourcesToEnrich, 0, 1000, 150);
  oa.maxExternalCoauthors = clampNumber(oa.maxExternalCoauthors, 10, 300, 80);
  oa.nationalityRecentWorks = clampNumber(oa.nationalityRecentWorks, 3, 25, 10);
  oa.nationalityConcurrency = clampNumber(oa.nationalityConcurrency, 1, 8, 4);
  merged.defaults.startYear = clampNumber(merged.defaults.startYear, 1900, 2100, 2020);
  merged.defaults.endYear = clampNumber(merged.defaults.endYear, 1900, 2100, new Date().getFullYear());
  merged.defaults.countryBrazil = String(merged.defaults.countryBrazil || 'BR').trim().toUpperCase().slice(0, 2) || 'BR';
  return merged;
}

function normalizeEndpoint(value, fallback) {
  const text = String(value || fallback).trim();
  if (startsWithHttpProtocol(text)) return stripTrailingSlashes(text);
  const withSlash = text.startsWith('/') ? text : `/${text}`;
  return withSlash.length > 1 ? stripTrailingSlashes(withSlash) : withSlash;
}

function startsWithHttpProtocol(value) {
  const lower = String(value || '').toLowerCase();
  return lower.startsWith('http://') || lower.startsWith('https://');
}

function stripTrailingSlashes(value) {
  let text = String(value || '').trim();
  while (text.length > 1 && text.endsWith('/')) {
    text = text.slice(0, -1);
  }
  return text;
}

function clampNumber(value, min, max, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, Math.round(n)));
}

export async function loadInitialConfig() {
  let fromFile = {};
  try {
    const res = await fetch('./config.json', { cache: 'no-store' });
    if (res.ok) fromFile = await res.json();
  } catch (error) {
    // Abrir via file:// pode bloquear a leitura de config.json. A UI ainda funciona com padrão.
  }

  let fromSession = {};
  try {
    fromSession = JSON.parse(sessionStorage.getItem(CONFIG_KEY) || '{}');
  } catch (error) {
    fromSession = {};
  }

  return normalizeConfig(deepMerge(fromFile, fromSession));
}

export function saveRuntimeConfig(cfg) {
  const normalized = normalizeConfig(cfg);
  sessionStorage.setItem(CONFIG_KEY, JSON.stringify(normalized));
  return normalized;
}

export function resetRuntimeConfig() {
  sessionStorage.removeItem(CONFIG_KEY);
  return normalizeConfig(DEFAULT_CONFIG);
}

export function configToFormObject(cfg) {
  return {
    systemName: cfg.systemName,
    logoUrl: cfg.logoUrl,
    baseUrl: cfg.openAlex.baseUrl,
    authorsEndpoint: cfg.openAlex.authorsEndpoint,
    worksEndpoint: cfg.openAlex.worksEndpoint,
    sourcesEndpoint: cfg.openAlex.sourcesEndpoint,
    apiKey: cfg.openAlex.apiKey,
    mailto: cfg.openAlex.mailto,
    perPage: cfg.openAlex.perPage,
    maxPagesPerAuthor: cfg.openAlex.maxPagesPerAuthor,
    requestDelayMs: cfg.openAlex.requestDelayMs,
    maxSourcesToEnrich: cfg.openAlex.maxSourcesToEnrich,
    maxExternalCoauthors: cfg.openAlex.maxExternalCoauthors,
    nationalityRecentWorks: cfg.openAlex.nationalityRecentWorks,
    nationalityConcurrency: cfg.openAlex.nationalityConcurrency,
    countryBrazil: cfg.defaults.countryBrazil
  };
}

export function formObjectToConfig(form, previous) {
  return normalizeConfig({
    ...previous,
    systemName: form.systemName,
    logoUrl: form.logoUrl,
    openAlex: {
      ...previous.openAlex,
      baseUrl: form.baseUrl,
      authorsEndpoint: form.authorsEndpoint,
      worksEndpoint: form.worksEndpoint,
      sourcesEndpoint: form.sourcesEndpoint,
      apiKey: form.apiKey,
      mailto: form.mailto,
      perPage: form.perPage,
      maxPagesPerAuthor: form.maxPagesPerAuthor,
      requestDelayMs: form.requestDelayMs,
      maxSourcesToEnrich: form.maxSourcesToEnrich,
      maxExternalCoauthors: form.maxExternalCoauthors,
      nationalityRecentWorks: form.nationalityRecentWorks,
      nationalityConcurrency: form.nationalityConcurrency
    },
    defaults: {
      ...previous.defaults,
      countryBrazil: form.countryBrazil
    }
  });
}
