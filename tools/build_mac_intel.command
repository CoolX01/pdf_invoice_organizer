#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="PDF发票自动整理归纳工具"
HOST_ARCH="$(uname -m)"
VENV_DIR=".venv_intel"
PYTHON_BIN="${VENV_DIR}/bin/python3"
DIST_DIR="app/mac_intel"
WORK_DIR="build/mac_intel"
RELEASE_DIR="release/mac/intel"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
ZIP_PATH="${RELEASE_DIR}/${APP_NAME}_mac_intel_${TIMESTAMP}.zip"
APP_PATH="${DIST_DIR}/${APP_NAME}.app"

if [ "${HOST_ARCH}" = "x86_64" ]; then
  BOOTSTRAP_CMD=(python3)
  RUN_PREFIX=()
else
  if arch -x86_64 /usr/bin/python3 -V >/dev/null 2>&1; then
    BOOTSTRAP_CMD=(arch -x86_64 /usr/bin/python3)
    RUN_PREFIX=(arch -x86_64)
  else
    echo "An x86_64 Python runtime is not available on this Mac."
    echo "Please install Rosetta 2 or run this script on an Intel Mac."
    exit 1
  fi
fi

if ! command -v python3 >/dev/null 2>&1 && [ "${HOST_ARCH}" = "x86_64" ]; then
  echo "python3 was not found. Please install Python 3.9+ first."
  exit 1
fi

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "[1/5] Creating Intel virtual environment..."
  "${BOOTSTRAP_CMD[@]}" -m venv "${VENV_DIR}"
fi

echo "[2/5] Checking pip..."
"${RUN_PREFIX[@]}" "${PYTHON_BIN}" -m pip --version >/dev/null

echo "[3/5] Installing dependencies..."
"${RUN_PREFIX[@]}" "${PYTHON_BIN}" -m pip install --disable-pip-version-check --upgrade pip
"${RUN_PREFIX[@]}" "${PYTHON_BIN}" -m pip install --disable-pip-version-check --no-warn-script-location -r source/requirements.txt pyinstaller

echo "[4/5] Building Intel Mac app..."
rm -rf "${APP_PATH}" "${WORK_DIR}"
mkdir -p "${DIST_DIR}" "${RELEASE_DIR}"
"${RUN_PREFIX[@]}" "${PYTHON_BIN}" -m PyInstaller tools/invoice_organizer.spec --noconfirm --distpath "${DIST_DIR}" --workpath "${WORK_DIR}"

echo "[5/5] Packaging release zip..."
rm -f "${ZIP_PATH}"
ditto -c -k --sequesterRsrc --keepParent "${APP_PATH}" "${ZIP_PATH}"

echo
echo "Intel Mac build completed."
echo "Host architecture: ${HOST_ARCH}"
echo "App: $(pwd)/${APP_PATH}"
echo "Zip: $(pwd)/${ZIP_PATH}"
