#!/usr/bin/env bash
set -euo pipefail

profile=$1
expected_sha=$2
expected_tree=$3
expected_build=$4
output=$5
shift 5

runner=IAmGodTranslator_Render_Deploy/tools/verify_release.py
identity=(--expect-sha "$expected_sha" --expect-tree "$expected_tree" --expect-build-id "$expected_build")
status=0
python "$runner" run --profile "$profile" "${identity[@]}" --output "$output" "$@" || status=$?
# Check failed evidence too. A valid failed archive still blocks qualification.
python "$runner" check-evidence "$output.zip" "${identity[@]}" --expect-profile "$profile" --require-pass || {
  if (( status == 0 )); then status=1; fi
}
exit "$status"
