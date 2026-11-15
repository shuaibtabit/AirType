#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"
python_path=${AIRTYPE_PYTHON:-$(python3 -c 'import sys; print(sys.executable)')}
"$python_path" -B -c 'import sklearn, joblib'
swift build "$@"

staging_dir=$(mktemp -d "$repo_dir/.AirType-build.XXXXXX")
trap 'rm -rf "$staging_dir"' EXIT
bundle="$staging_dir/AirType.app"
mkdir -p "$bundle/Contents/MacOS"
cp .build/debug/airtype-overlay "$bundle/Contents/MacOS/airtype-overlay"
"$python_path" -B - "$bundle/Contents/Info.plist" "$python_path" <<'PY'
import os
import plistlib
import sys

plist = {
    "CFBundleDevelopmentRegion": "en",
    "CFBundleDisplayName": "AirType",
    "CFBundleExecutable": "airtype-overlay",
    "CFBundleIdentifier": "local.airtype.demo",
    "CFBundleName": "AirType",
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": "1.0",
    "CFBundleVersion": "1",
    "LSMinimumSystemVersion": "13.0",
    "NSBluetoothAlwaysUsageDescription": "AirType reads wrist motion from your WHOOP during a live session.",
    "AirTypePython": sys.argv[2],
}
device = os.environ.get("AIRTYPE_DEVICE_UUID", "")
if device:
    import uuid

    plist["AirTypeDeviceUUID"] = str(uuid.UUID(device)).upper()
with open(sys.argv[1], "wb") as output:
    plistlib.dump(plist, output)
PY
codesign --force --sign - "$bundle"
if [ -d AirType.app ]; then
    mv AirType.app "$staging_dir/previous.app"
fi
if ! mv "$bundle" AirType.app; then
    if [ -d "$staging_dir/previous.app" ]; then
        mv "$staging_dir/previous.app" AirType.app
    fi
    exit 1
fi
printf 'Open %s/AirType.app in Finder.\n' "$repo_dir"
