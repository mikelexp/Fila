#!/bin/bash
set -euo pipefail

exec make package-release "$@"
