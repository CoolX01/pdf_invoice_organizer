#!/bin/bash

set -u

cd "$(dirname "$0")"

APP_NAME="PDF发票自动整理归纳工具"
LOG_DIR="${HOME}/Library/Logs/${APP_NAME}"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/launcher.log"

unset QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH DYLD_FRAMEWORK_PATH DYLD_LIBRARY_PATH

ARCH="$(uname -m)"
if [ "${ARCH}" = "x86_64" ]; then
  APP_BUNDLES=(
    "app/mac_intel/PDF发票自动整理归纳工具.app"
  )
else
  APP_BUNDLES=(
    "app/mac/PDF发票自动整理归纳工具.app"
    "app/mac_intel/PDF发票自动整理归纳工具.app"
  )
fi

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting app"
  echo "ARCH=${ARCH}"
  echo "QT_PLUGIN_PATH=${QT_PLUGIN_PATH:-}"
  echo "QT_QPA_PLATFORM_PLUGIN_PATH=${QT_QPA_PLATFORM_PLUGIN_PATH:-}"
  echo "DYLD_FRAMEWORK_PATH=${DYLD_FRAMEWORK_PATH:-}"
} >> "${LOG_FILE}"

STATUS=1

for APP_BUNDLE in "${APP_BUNDLES[@]}"; do
  if [ -d "${APP_BUNDLE}" ]; then
    open "${APP_BUNDLE}" >> "${LOG_FILE}" 2>&1
    STATUS=$?
    break
  fi
done

if [ "${STATUS}" -ne 0 ]; then
  echo "打包后的 .app 不存在，回退到源码启动。" >> "${LOG_FILE}"

  PYTHON_CANDIDATES=(
    "./.venv_intel/bin/python"
    "./.venv/bin/python"
  )

  for PYTHON_BIN in "${PYTHON_CANDIDATES[@]}"; do
    if [ -x "${PYTHON_BIN}" ]; then
      "${PYTHON_BIN}" main.py >> "${LOG_FILE}" 2>&1
      STATUS=$?
      break
    fi
  done
fi

if [ "${STATUS}" -ne 0 ]; then
  echo
  echo "程序启动失败，已把错误日志写入：${LOG_FILE}"
  echo "按回车键关闭窗口。"
  read -r _
fi

exit "${STATUS}"
