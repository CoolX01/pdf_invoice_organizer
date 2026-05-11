#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")"
exec "./tools/build_mac_intel.command"
