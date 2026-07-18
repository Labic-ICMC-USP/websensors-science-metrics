const STATE_KEY = 'wsm.sessionState.v11';

export const state = {
  config: null,
  groupAuthors: [],
  authorResults: [],
  worksByAuthor: {},
  works: [],
  sourceCache: {},
  authorCountryProfiles: {},
  metrics: null,
  logs: []
};

export function loadState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STATE_KEY) || '{}');
    state.groupAuthors = Array.isArray(saved.groupAuthors) ? saved.groupAuthors : [];
    state.worksByAuthor = {};
    state.works = Array.isArray(saved.works) ? saved.works : [];
    state.sourceCache = saved.sourceCache || {};
    state.authorCountryProfiles = saved.authorCountryProfiles || {};
  } catch (error) {
    addLog(`Não foi possível restaurar a sessão: ${error.message}`);
  }
}

export function saveState() {
  const lightweightWorks = state.works.map(({ raw, ...rest }) => rest);
  const payload = {
    groupAuthors: state.groupAuthors,
    works: lightweightWorks,
    sourceCache: state.sourceCache,
    authorCountryProfiles: state.authorCountryProfiles
  };
  try {
    sessionStorage.setItem(STATE_KEY, JSON.stringify(payload));
  } catch (error) {
    const minimalPayload = { groupAuthors: state.groupAuthors, works: [], sourceCache: {}, authorCountryProfiles: state.authorCountryProfiles || {} };
    try {
      sessionStorage.setItem(STATE_KEY, JSON.stringify(minimalPayload));
    } catch (_) {
      // Em sessões muito grandes, manter apenas o estado em memória.
    }
  }
}

export function clearAllData() {
  state.groupAuthors = [];
  state.authorResults = [];
  state.worksByAuthor = {};
  state.works = [];
  state.sourceCache = {};
  state.authorCountryProfiles = {};
  state.metrics = null;
  saveState();
}

export function clearWorksData() {
  state.worksByAuthor = {};
  state.works = [];
  state.metrics = null;
  saveState();
}

export function addAuthor(author) {
  if (!author?.id) return false;
  if (state.groupAuthors.some((a) => a.id === author.id)) return false;
  state.groupAuthors.push(author);
  saveState();
  return true;
}

export function removeAuthor(authorId) {
  state.groupAuthors = state.groupAuthors.filter((a) => a.id !== authorId);
  delete state.worksByAuthor[authorId];
  state.works = [];
  state.metrics = null;
  saveState();
}

export function addLog(message) {
  const stamp = new Date().toLocaleTimeString('pt-BR');
  state.logs.unshift(`[${stamp}] ${message}`);
  state.logs = state.logs.slice(0, 120);
}
