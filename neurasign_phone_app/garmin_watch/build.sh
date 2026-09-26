#!/usr/bin/env bash
set -euo pipefail
: "${CONNECT_IQ_SDK:?Set CONNECT_IQ_SDK to the installed Garmin SDK directory}"
: "${GARMIN_DEVELOPER_KEY:?Set GARMIN_DEVELOPER_KEY to your private DER signing key outside the repository}"
cd "$(dirname "$0")"
mkdir -p build
java -jar "$CONNECT_IQ_SDK/bin/monkeybrains.jar" -f monkey.jungle -d "${1:?Pass an installed Garmin device profile, e.g. venu3}" -y "$GARMIN_DEVELOPER_KEY" -o build/neurasign.prg -w
