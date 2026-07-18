"""Cliente HTTP mínimo para o ArcadeDB usado pela pipeline Science Metrics.

O módulo encapsula operações de disponibilidade, administração de bancos, comandos,
consultas e criação de registros. A intenção é concentrar aqui os detalhes do protocolo
HTTP do ArcadeDB para que os steps trabalhem com uma interface pequena e testável.
"""

from __future__ import annotations

import time
from typing import Any

import requests


class ArcadeDBError(RuntimeError):
    """Erro de integração levantado quando o ArcadeDB rejeita uma operação ou retorna uma resposta inválida."""
    pass


class ArcadeDBClient:
    """Cliente HTTP síncrono para administração, comandos, consultas e criação de registros no banco ArcadeDB do grupo."""
    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        database: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.database = database
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    @property
    def studio_url(self) -> str:
        """Retorna a URL base usada para abrir o ArcadeDB Studio no navegador."""
        return self.base_url

    def wait_until_ready(self, attempts: int = 15, delay_seconds: float = 1.0) -> None:
        """Aguarda o servidor ArcadeDB ficar disponível antes de iniciar uma etapa que depende do banco."""
        last_error: Exception | None = None
        for _ in range(max(1, attempts)):
            try:
                response = self.session.get(f"{self.base_url}/api/v1/ready", timeout=3)
                if response.status_code in (200, 204):
                    return
                if response.status_code == 404:
                    self.server_info()
                    return
            except Exception as exc:  # pragma: no cover - network dependent
                last_error = exc
            time.sleep(delay_seconds)
        raise ArcadeDBError(
            f"ArcadeDB não respondeu em {self.base_url}. "
            "Inicie o servidor local antes de executar o pipeline."
        ) from last_error

    def server_info(self) -> dict[str, Any]:
        """Obtém os metadados expostos pelo endpoint administrativo do servidor ArcadeDB."""
        response = self.session.get(f"{self.base_url}/api/v1/server", timeout=self.timeout_seconds)
        return self._decode(response)

    def list_databases(self) -> list[str]:
        """Lista os nomes dos bancos conhecidos pelo servidor, normalizando diferentes formatos de resposta."""
        info = self.server_info()
        databases = info.get("databases")
        result: list[str] = []
        if isinstance(databases, dict):
            result.extend(str(key) for key in databases)
        elif isinstance(databases, list):
            for item in databases:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("database")
                    if name:
                        result.append(str(name))
        return sorted(set(result))

    def database_exists(self) -> bool:
        """Verifica se o banco configurado existe, com fallback para uma consulta direta ao schema."""
        try:
            listed = self.list_databases()
            if listed:
                return self.database in listed
        except ArcadeDBError:
            pass
        try:
            self.query("SELECT FROM schema:types LIMIT 1")
            return True
        except ArcadeDBError:
            return False

    def recreate_database(self, *, drop_existing: bool = True) -> None:
        """Remove opcionalmente o banco existente e garante a criação de um banco vazio para a nova execução."""
        if drop_existing and self.database_exists():
            self.server_command(f"drop database {self.database}")
        elif drop_existing:
            try:
                self.server_command(f"drop database {self.database}")
            except ArcadeDBError as exc:
                message = str(exc).lower()
                if "not exist" not in message and "not found" not in message and "does not exist" not in message:
                    raise
        if not self.database_exists():
            self.server_command(f"create database {self.database}")

    def server_command(self, command: str) -> dict[str, Any]:
        """Executa um comando administrativo no nível do servidor, como criar ou remover um banco."""
        response = self.session.post(
            f"{self.base_url}/api/v1/server",
            json={"command": command},
            timeout=self.timeout_seconds,
        )
        return self._decode(response)

    def command(self, command: str, *, params: dict[str, Any] | None = None, language: str = "sql") -> dict[str, Any]:
        """Executa um comando mutável no banco configurado usando a linguagem indicada."""
        payload: dict[str, Any] = {"language": language, "command": command}
        if params:
            payload["params"] = params
        response = self.session.post(
            f"{self.base_url}/api/v1/command/{self.database}",
            json=payload,
            timeout=self.timeout_seconds,
        )
        return self._decode(response)

    def query(self, command: str, *, params: dict[str, Any] | None = None, language: str = "sql") -> list[dict[str, Any]]:
        """Executa uma consulta no banco configurado e devolve os registros como uma lista de dicionários."""
        payload: dict[str, Any] = {"language": language, "command": command}
        if params:
            payload["params"] = params
        response = self.session.post(
            f"{self.base_url}/api/v1/query/{self.database}",
            json=payload,
            timeout=self.timeout_seconds,
        )
        data = self._decode(response)
        return self.rows(data)

    def create_vertex(self, type_name: str, properties: dict[str, Any]) -> str:
        """
        Cria um vértice no ArcadeDB e retorna seu RID.

        Importante: Embora o ArcadeDB possua o comando específico ``CREATE VERTEX``,
        algumas versões do parser SQL não aceitam a cláusula ``RETURN``
        nesse comando.

        Como todos os tipos recebidos por este método são previamente
        definidos como VERTEX TYPE no schema, podemos usar ``INSERT INTO``.
        O ArcadeDB preserva o tipo do registro e cria um vértice real,
        permitindo que ele seja posteriormente utilizado como origem ou
        destino de arestas.

        A cláusula ``RETURN @rid`` permite recuperar diretamente o
        Record ID criado, evitando uma consulta adicional ao banco.
        """

        assignments = ", ".join(
            f"{key} = :p_{index}"
            for index, key in enumerate(properties)
        )

        params = {
            f"p_{index}": value
            for index, value in enumerate(properties.values())
        }

        command = (
            f"INSERT INTO {type_name} "
            f"SET {assignments} "
            f"RETURN @rid"
        )

        data = self.command(
            command,
            params=params,
        )

        return self.extract_rid(data)

    def create_document(self, type_name: str, properties: dict[str, Any]) -> str:
        """Cria um documento parametrizado e retorna o RID atribuído pelo ArcadeDB."""
        assignments = ", ".join(f"{key} = :p_{index}" for index, key in enumerate(properties))
        params = {f"p_{index}": value for index, value in enumerate(properties.values())}
        data = self.command(f"INSERT INTO {type_name} SET {assignments}", params=params)
        return self.extract_rid(data)

    def create_edge(self, type_name: str, from_rid: str, to_rid: str, properties: dict[str, Any] | None = None) -> str:
        """Cria uma aresta entre dois RIDs, incluindo propriedades opcionais de evidência ou agregação."""
        command = f"CREATE EDGE {type_name} FROM {from_rid} TO {to_rid}"
        params: dict[str, Any] = {}
        if properties:
            assignments = ", ".join(f"{key} = :p_{index}" for index, key in enumerate(properties))
            params = {f"p_{index}": value for index, value in enumerate(properties.values())}
            command += f" SET {assignments}"
        data = self.command(command, params=params)
        return self.extract_rid(data)

    def update(self, type_name: str, key_field: str, key_value: Any, properties: dict[str, Any]) -> None:
        """Atualiza propriedades de registros encontrados por uma chave lógica."""
        assignments = ", ".join(f"{key} = :p_{index}" for index, key in enumerate(properties))
        params = {f"p_{index}": value for index, value in enumerate(properties.values())}
        params["key_value"] = key_value
        self.command(f"UPDATE {type_name} SET {assignments} WHERE {key_field} = :key_value", params=params)

    @staticmethod
    def rows(payload: Any) -> list[dict[str, Any]]:
        """Normaliza diferentes envelopes de resposta do ArcadeDB para uma lista de registros."""
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("result", "records", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @classmethod
    def extract_rid(cls, payload: Any) -> str:
        """Extrai o RID de uma resposta de criação e falha explicitamente quando ele não está presente."""
        rows = cls.rows(payload)
        candidates: list[Any] = rows if rows else ([payload] if isinstance(payload, dict) else [])
        for item in candidates:
            if not isinstance(item, dict):
                continue
            for key in ("@rid", "rid", "recordId"):
                if item.get(key):
                    return str(item[key])
            record = item.get("record")
            if isinstance(record, dict) and record.get("@rid"):
                return str(record["@rid"])
        raise ArcadeDBError(f"ArcadeDB não retornou RID para o registro criado: {payload}")

    @staticmethod
    def _decode(response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            data = {"text": response.text}
        if not response.ok:
            detail = data.get("detail") or data.get("error") or data.get("text") or response.text
            raise ArcadeDBError(f"HTTP {response.status_code}: {detail}")
        return data if isinstance(data, dict) else {"result": data}
