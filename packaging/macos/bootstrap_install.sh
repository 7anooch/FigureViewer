#!/usr/bin/env bash
# Bootstrap Figure Gallery on this Mac: conda env + editable install + thin .app.
#
# Prerequisites: conda (Miniconda / Anaconda / Mambaforge) on PATH, or
#                installable via the usual conda.sh location.
#
# Usage (from anywhere after cloning):
#   ./packaging/macos/bootstrap_install.sh
#   ./packaging/macos/bootstrap_install.sh --icon path/to/logo_1024.png
#   ./packaging/macos/bootstrap_install.sh --update-env   # also refresh deps from environment.yaml
#   ./packaging/macos/bootstrap_install.sh --prefix ~/Applications
#
# Extra flags are forwarded to packaging/macos/install_app.sh (--icon, --prefix, --python, --env).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_NAME="figviewer"
ENV_FILE="${ROOT}/environment.yaml"
UPDATE_ENV=0
FORWARD_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --update-env)
      UPDATE_ENV=1
      shift
      ;;
    --env)
      ENV_NAME="$2"
      FORWARD_ARGS+=(--env "$2")
      shift 2
      ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      FORWARD_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: this bootstrap builds a macOS .app (Darwin only)." >&2
  echo "       On other OSes: conda env create -f environment.yaml && pip install -e ." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "error: missing ${ENV_FILE}" >&2
  exit 1
fi

find_conda() {
  if command -v conda >/dev/null 2>&1; then
    command -v conda
    return
  fi
  local candidate
  for candidate in \
    "${HOME}/miniconda3/etc/profile.d/conda.sh" \
    "${HOME}/anaconda3/etc/profile.d/conda.sh" \
    "${HOME}/mambaforge/etc/profile.d/conda.sh" \
    "${HOME}/miniforge3/etc/profile.d/conda.sh" \
    "/opt/homebrew/anaconda3/etc/profile.d/conda.sh" \
    "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
  do
    if [[ -f "${candidate}" ]]; then
      # shellcheck source=/dev/null
      source "${candidate}"
      if command -v conda >/dev/null 2>&1; then
        command -v conda
        return
      fi
    fi
  done
  return 1
}

if ! CONDA_BIN="$(find_conda)"; then
  echo "error: conda not found." >&2
  echo "       Install Miniconda or Anaconda, then re-run this script." >&2
  echo "       https://docs.conda.io/en/latest/miniconda.html" >&2
  exit 1
fi

echo "==> Using conda: ${CONDA_BIN}"

env_exists() {
  # Quiet check: can we run something in the named env?
  conda run -n "${ENV_NAME}" true >/dev/null 2>&1
}

if env_exists; then
  echo "==> Conda env '${ENV_NAME}' already exists"
  if [[ "${UPDATE_ENV}" -eq 1 ]]; then
    echo "==> Updating env from environment.yaml (--update-env)"
    conda env update -n "${ENV_NAME}" -f "${ENV_FILE}" --prune
  else
    echo "    (pass --update-env to refresh dependencies from environment.yaml)"
  fi
else
  echo "==> Creating conda env from environment.yaml (name: ${ENV_NAME})"
  # Honor the name in the yaml by default; if --env overrides, create with -n.
  if [[ "${ENV_NAME}" == "figviewer" ]]; then
    conda env create -f "${ENV_FILE}"
  else
    conda env create -n "${ENV_NAME}" -f "${ENV_FILE}"
  fi
fi

echo "==> Editable install of this repo into '${ENV_NAME}'"
conda run -n "${ENV_NAME}" python -m pip install -e "${ROOT}"

echo "==> Building thin Figure Gallery.app"
"${ROOT}/packaging/macos/install_app.sh" --env "${ENV_NAME}" "${FORWARD_ARGS[@]+"${FORWARD_ARGS[@]}"}"

echo
echo "Done. CLI (optional):"
echo "  conda activate ${ENV_NAME}"
echo "  figuregallery"
echo
echo "After pulling new commits, either re-run this script or:"
echo "  conda activate ${ENV_NAME} && pip install -e . && ./packaging/macos/install_app.sh"
echo "Use --update-env when environment.yaml dependencies change."
