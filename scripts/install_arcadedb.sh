#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# WebSensors Science Metrics
# Instalador local do ArcadeDB
#
# Este script instala o ArcadeDB dentro do próprio diretório do projeto:
#
#   .runtime/arcadedb/
#
# IMPORTANTE
# ----------
# O ArcadeDB possui diferentes distribuições:
#
#   full      -> inclui todos os módulos, inclusive o ArcadeDB Studio
#   minimal   -> inclui o Studio, mas remove alguns módulos opcionais
#   headless  -> NÃO inclui o Studio
#   base      -> NÃO inclui o Studio
#
# Para este projeto usamos preferencialmente a distribuição "full",
# pois queremos acessar visualmente o Knowledge Graph pelo ArcadeDB Studio.
#
# A versão é descoberta automaticamente pela API de releases do GitHub.
#
# Também é possível fornecer manualmente:
#
#   ARCADEDB_ARCHIVE=/caminho/arcadedb-x.y.z-full.tar.gz \
#       ./scripts/install_arcadedb.sh
#
# ou:
#
#   ARCADEDB_DOWNLOAD_URL=https://.../arcadedb-x.y.z-full.tar.gz \
#       ./scripts/install_arcadedb.sh
#
# Requisito:
#   Java 21 ou superior
# =============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RUNTIME_DIR="$ROOT_DIR/.runtime"
INSTALL_DIR="$RUNTIME_DIR/arcadedb"
DOWNLOAD_DIR="$RUNTIME_DIR/downloads"

mkdir -p "$RUNTIME_DIR" "$DOWNLOAD_DIR"


# -----------------------------------------------------------------------------
# 1. Verifica se Java está instalado
# -----------------------------------------------------------------------------

if ! command -v java >/dev/null 2>&1; then
  echo "Erro: Java 21+ não encontrado no PATH." >&2
  echo
  echo "Instale Java 21 antes de continuar."
  exit 1
fi


# -----------------------------------------------------------------------------
# 2. Verifica a versão do Java
# -----------------------------------------------------------------------------

JAVA_MAJOR="$(
  java -version 2>&1 |
  awk -F'[\".]' '/version/ {print $2; exit}'
)"

if [[ -z "$JAVA_MAJOR" || "$JAVA_MAJOR" -lt 21 ]]; then
  echo "Erro: ArcadeDB requer Java 21+." >&2
  echo "Versão detectada: ${JAVA_MAJOR:-desconhecida}" >&2
  exit 1
fi

echo "Java detectado:"
java -version 2>&1 | head -n 1
echo


# -----------------------------------------------------------------------------
# 3. Download e instalação do ArcadeDB
#
# A lógica abaixo é executada em Python apenas para facilitar:
#
#   - consulta à API do GitHub;
#   - seleção correta do pacote;
#   - download;
#   - extração de ZIP/TAR.GZ;
#   - substituição segura da instalação anterior.
# -----------------------------------------------------------------------------

python3 - \
  "$DOWNLOAD_DIR" \
  "$INSTALL_DIR" \
  "${ARCADEDB_ARCHIVE:-}" \
  "${ARCADEDB_DOWNLOAD_URL:-}" <<'PY'

import json
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile

from pathlib import Path


DOWNLOAD_DIR = Path(sys.argv[1])
INSTALL_DIR = Path(sys.argv[2])

ARCHIVE_OVERRIDE = sys.argv[3].strip()
DOWNLOAD_URL_OVERRIDE = sys.argv[4].strip()

GITHUB_RELEASE_API = (
    "https://api.github.com/repos/ArcadeData/arcadedb/releases/latest"
)


# =============================================================================
# Utilitários
# =============================================================================


def is_archive(name: str) -> bool:
    """
    Retorna True quando o nome corresponde a um arquivo compactado
    suportado pelo instalador.
    """

    name = name.lower()

    return name.endswith(
        (
            ".tar.gz",
            ".tgz",
            ".zip",
        )
    )


def package_variant(name: str) -> str | None:
    """
    Identifica a variante de uma distribuição ArcadeDB pelo nome.

    As variantes relevantes são:

    - full
    - minimal
    - headless
    - base
    """

    name = name.lower()

    for variant in (
        "full",
        "minimal",
        "headless",
        "base",
    ):
        marker = f"-{variant}."

        if marker in name:
            return variant

    return None


def validate_studio_distribution(filename: str) -> None:
    """
    Impede silenciosamente a instalação de uma distribuição conhecida
    por não possuir o ArcadeDB Studio.

    Isto evita a situação em que a API REST funciona normalmente,
    mas http://localhost:2480 retorna apenas "Not Found".
    """

    variant = package_variant(filename)

    if variant in {"base", "headless"}:
        raise SystemExit(
            "\n"
            "ERRO: o pacote selecionado não contém o ArcadeDB Studio.\n"
            "\n"
            f"Pacote: {filename}\n"
            f"Variante detectada: {variant}\n"
            "\n"
            "Use a distribuição 'full' ou 'minimal'.\n"
        )


# =============================================================================
# Download automático da release mais recente
# =============================================================================


def download_latest() -> Path:
    """
    Consulta a última release oficial do ArcadeDB no GitHub.

    A seleção do pacote segue esta prioridade:

        1. full
        2. minimal

    As variantes 'base' e 'headless' são deliberadamente ignoradas,
    pois não incluem o ArcadeDB Studio necessário para visualizar e
    auditar o Knowledge Graph deste projeto.
    """

    print("Consultando a release mais recente do ArcadeDB...")

    try:
        request = urllib.request.Request(
            GITHUB_RELEASE_API,
            headers={
                "User-Agent":
                    "websensors-science-metrics-installer"
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=60,
        ) as response:
            release = json.load(response)

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ) as exc:

        raise SystemExit(
            "\n"
            "Não foi possível consultar o GitHub para instalar "
            "o ArcadeDB.\n"
            "\n"
            "Verifique a conexão com a Internet ou execute:\n"
            "\n"
            "  ARCADEDB_ARCHIVE=/caminho/"
            "arcadedb-<versao>-full.tar.gz "
            "./scripts/install_arcadedb.sh\n"
            "\n"
            f"Detalhe: {exc}"
        )

    version = release.get("tag_name", "desconhecida")

    print(f"Release encontrada: {version}")

    assets = release.get("assets") or []


    # -------------------------------------------------------------------------
    # Mantemos somente arquivos binários ArcadeDB compactados.
    #
    # Arquivos .sha256 e source code são descartados.
    # -------------------------------------------------------------------------

    candidates = []

    for asset in assets:

        name = str(
            asset.get("name") or ""
        )

        lower_name = name.lower()

        if not lower_name.startswith("arcadedb-"):
            continue

        if lower_name.endswith(".sha256"):
            continue

        if "source" in lower_name:
            continue

        if not is_archive(lower_name):
            continue

        candidates.append(asset)


    # -------------------------------------------------------------------------
    # Seleção explícita da distribuição.
    #
    # O erro anterior ocorria porque simplesmente selecionávamos o primeiro
    # asset retornado pela API. Nas releases recentes o primeiro pacote pode
    # ser o "base", que não possui o Studio.
    #
    # Agora:
    #
    #   1. procura FULL
    #   2. se não existir, procura MINIMAL
    #
    # Nunca fazemos fallback para BASE ou HEADLESS.
    # -------------------------------------------------------------------------

    chosen = None

    for preferred_variant in (
        "full",
        "minimal",
    ):

        for asset in candidates:

            name = str(
                asset.get("name") or ""
            )

            if package_variant(name) == preferred_variant:
                chosen = asset
                break

        if chosen:
            break


    if not chosen:

        available = "\n".join(
            f"  - {asset.get('name')}"
            for asset in candidates
        )

        raise SystemExit(
            "\n"
            "Não foi encontrada uma distribuição ArcadeDB "
            "com suporte ao Studio.\n"
            "\n"
            "Esperava encontrar uma variante:\n"
            "\n"
            "  - full\n"
            "  - minimal\n"
            "\n"
            "Pacotes disponíveis na release:\n"
            f"{available or '  nenhum'}\n"
        )


    filename = chosen["name"]

    validate_studio_distribution(filename)

    url = chosen["browser_download_url"]

    archive = DOWNLOAD_DIR / filename


    print()
    print("Distribuição ArcadeDB selecionada:")
    print(f"  arquivo : {filename}")
    print(f"  variante: {package_variant(filename)}")
    print()


    # -------------------------------------------------------------------------
    # Reutiliza o download se ele já existir.
    # -------------------------------------------------------------------------

    if archive.exists() and archive.stat().st_size > 0:

        print(
            "Arquivo já encontrado no cache local:"
        )

        print(
            f"  {archive}"
        )

        return archive


    print(
        f"Baixando ArcadeDB {version}..."
    )


    try:

        urllib.request.urlretrieve(
            url,
            archive,
        )

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ) as exc:

        if archive.exists():
            archive.unlink()

        raise SystemExit(
            "\n"
            "Falha no download do ArcadeDB.\n"
            "\n"
            "Você pode baixar manualmente a distribuição FULL "
            "e executar:\n"
            "\n"
            "  ARCADEDB_ARCHIVE=/caminho/do/arquivo "
            "./scripts/install_arcadedb.sh\n"
            "\n"
            f"Detalhe: {exc}"
        )


    return archive


# =============================================================================
# Download a partir de URL fornecida pelo usuário
# =============================================================================


def download_url(url: str) -> Path:
    """
    Faz download de um pacote ArcadeDB informado explicitamente por URL.
    """

    filename = (
        url
        .rstrip("/")
        .split("/")[-1]
        or "arcadedb-package.tar.gz"
    )

    validate_studio_distribution(
        filename
    )

    archive = DOWNLOAD_DIR / filename

    print(
        "Baixando ArcadeDB de URL configurada:"
    )

    print(
        f"  {url}"
    )


    try:

        urllib.request.urlretrieve(
            url,
            archive,
        )

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ) as exc:

        if archive.exists():
            archive.unlink()

        raise SystemExit(
            "Falha no download de "
            f"ARCADEDB_DOWNLOAD_URL: {exc}"
        )


    return archive


# =============================================================================
# Escolha da origem do pacote
# =============================================================================


if ARCHIVE_OVERRIDE:

    archive = (
        Path(ARCHIVE_OVERRIDE)
        .expanduser()
        .resolve()
    )

    if not archive.exists():

        raise SystemExit(
            "ARCADEDB_ARCHIVE não existe: "
            f"{archive}"
        )

    validate_studio_distribution(
        archive.name
    )

    print(
        "Usando pacote ArcadeDB local:"
    )

    print(
        f"  {archive}"
    )


elif DOWNLOAD_URL_OVERRIDE:

    archive = download_url(
        DOWNLOAD_URL_OVERRIDE
    )


else:

    archive = download_latest()


# =============================================================================
# Extração
# =============================================================================


print()
print(
    f"Extraindo {archive.name}..."
)


with tempfile.TemporaryDirectory(
    prefix="arcadedb-extract-",
    dir=DOWNLOAD_DIR,
) as temp:

    temp_path = Path(temp)

    name = archive.name.lower()


    if name.endswith(".zip"):

        with zipfile.ZipFile(
            archive
        ) as zf:

            zf.extractall(
                temp_path
            )


    elif name.endswith(
        (
            ".tar.gz",
            ".tgz",
        )
    ):

        with tarfile.open(
            archive
        ) as tf:

            tf.extractall(
                temp_path
            )


    else:

        raise SystemExit(
            "Formato de pacote não suportado: "
            f"{archive.name}"
        )


    # -------------------------------------------------------------------------
    # Localiza automaticamente a raiz do ArcadeDB.
    # -------------------------------------------------------------------------

    server_scripts = list(
        temp_path.rglob(
            "bin/server.sh"
        )
    )


    if not server_scripts:

        raise SystemExit(
            "Pacote baixado não contém "
            "bin/server.sh."
        )


    source_root = (
        server_scripts[0]
        .parent
        .parent
    )


    # -------------------------------------------------------------------------
    # Remove instalação anterior.
    #
    # Os dados dos bancos ficam em:
    #
    #   .runtime/arcadedb-data/
    #
    # portanto não são apagados nesta operação.
    # -------------------------------------------------------------------------

    if (
        INSTALL_DIR.exists()
        or INSTALL_DIR.is_symlink()
    ):

        print(
            "Removendo instalação anterior "
            "do ArcadeDB..."
        )


        if (
            INSTALL_DIR.is_symlink()
            or INSTALL_DIR.is_file()
        ):

            INSTALL_DIR.unlink()

        else:

            shutil.rmtree(
                INSTALL_DIR
            )


    # -------------------------------------------------------------------------
    # Instala a nova distribuição.
    # -------------------------------------------------------------------------

    shutil.copytree(
        source_root,
        INSTALL_DIR,
    )


print()
print(
    "ArcadeDB instalado com sucesso."
)

print(
    f"Diretório: {INSTALL_DIR}"
)

print(
    f"Pacote:    {archive.name}"
)

print(
    f"Variante:  {package_variant(archive.name) or 'personalizada'}"
)

PY


# -----------------------------------------------------------------------------
# 4. Garante permissão de execução
# -----------------------------------------------------------------------------

chmod +x \
  "$INSTALL_DIR/bin/server.sh" \
  2>/dev/null \
  || true


# -----------------------------------------------------------------------------
# 5. Mensagem final
# -----------------------------------------------------------------------------

echo
echo "============================================================"
echo " Instalação do ArcadeDB concluída"
echo "============================================================"
echo
echo "Para iniciar:"
echo
echo "  ./scripts/start_arcadedb.sh"
echo
echo "Depois abra no navegador:"
echo
echo "  http://127.0.0.1:2480"
echo
echo "Login padrão do projeto:"
echo
echo "  usuário: root"
echo "  senha:   playwithdata"
echo