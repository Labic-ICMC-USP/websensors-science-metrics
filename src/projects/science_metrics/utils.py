"""Funções utilitárias compartilhadas pelos módulos do projeto Science Metrics.

Inclui serialização JSON, normalização de nomes e identificadores, resolução de segredos,
conversões numéricas seguras e cálculo de métricas bibliométricas simples.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def json_dumps(value: Any) -> str:
    """Serializa um valor em JSON compacto, preservando caracteres Unicode."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def json_loads(value: Any, default: Any = None) -> Any:
    """Desserializa JSON de forma tolerante e retorna um valor padrão quando o conteúdo é inválido."""
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def short_openalex_id(value: str | None) -> str:
    """Converte uma URL ou identificador OpenAlex para sua forma curta terminal."""
    return str(value or "").rstrip("/").split("/")[-1]


def normalize_name(value: str | None) -> str:
    """Normaliza nomes para comparação removendo acentos, pontuação e diferenças de caixa."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", text).lower()
    return " ".join(text.split())


def safe_database_name(value: str) -> str:
    """Converte um nome de grupo em um identificador seguro e estável para banco ArcadeDB."""
    normalized = normalize_name(value).replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    if not normalized:
        normalized = "science_metrics"
    if normalized[0].isdigit():
        normalized = f"g_{normalized}"
    return normalized[:80]


def stable_id(prefix: str, values: Iterable[str]) -> str:
    """Gera um identificador determinístico a partir de um prefixo e de um conjunto de valores."""
    payload = "|".join(sorted(str(v) for v in values if v))
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:18]
    return f"{prefix}_{digest}"


def to_float(value: Any) -> float | None:
    """Converte um valor para ``float`` finito ou retorna ``None`` quando a conversão não é segura."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def to_int(value: Any, default: int = 0) -> int:
    """Converte um valor para inteiro usando um padrão em caso de erro."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def dedupe_strings(values: Iterable[Any]) -> list[str]:
    """Remove duplicatas de uma sequência textual preservando a primeira ordem de ocorrência."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def resolve_secret(config: dict[str, Any], key: str, env_key: str | None = None, default: str = "") -> str:
    """Resolve um segredo priorizando a variável de ambiente configurada e usando o YAML apenas como fallback."""
    configured_env = config.get(f"{key}_env") or env_key
    if configured_env and os.getenv(str(configured_env)):
        return str(os.environ[str(configured_env)])
    value = config.get(key, default)
    return str(value if value is not None else default)


def ensure_dir(path: str | Path) -> Path:
    """Cria um diretório e seus pais, retornando o objeto ``Path`` correspondente."""
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def h_index(citations: Iterable[int | float]) -> int:
    """Calcula o h-index de uma coleção de contagens de citações."""
    ordered = sorted((max(0, int(c)) for c in citations), reverse=True)
    value = 0
    for index, count in enumerate(ordered, start=1):
        if count >= index:
            value = index
        else:
            break
    return value
