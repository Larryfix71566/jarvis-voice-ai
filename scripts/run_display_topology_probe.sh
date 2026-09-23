#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
probe="$repo_root/docs/acceptance/command-console/probes/DisplayTopologyProbe.swift"
binary=$(mktemp -t mortimer-display-topology-probe)
module_cache=$(mktemp -d "${TMPDIR:-/tmp}/mortimer-display-topology-modules.XXXXXX")
trap 'rm -f "$binary"; rm -rf "$module_cache"' EXIT

swiftc -O -module-cache-path "$module_cache" -framework AppKit -framework CoreGraphics -framework Foundation "$probe" -o "$binary"
exec "$binary"
