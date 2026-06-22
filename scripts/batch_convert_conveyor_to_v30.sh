#!/usr/bin/env bash
set -euo pipefail

LEROBOT_ROOT="/data/SJJ/UBT/lerobot_0.5.1"
DATASET_PREFIX="/data/SJJ/UBT/lerobot_0.5.1/datasets/Conveyor_Sorting"
CONVERTER="${LEROBOT_ROOT}/src/lerobot/datasets/v30/convert_dataset_v21_to_v30.py"

episodes=(
  episode_1
  episode_1_2
  episode_1_3
  episode_1_4
  episode_1_5
  episode_2
  episode_2_2
  episode_2_3
  episode_3
  episode_3_2
  episode_3_3
  episode_3_4
  episode_4
  episode_4_2
  episode_4_3
  episode_4_4
  episode_5
  episode_5_2
  episode_7
  episode_8
  episode_11
  episode_13
  episode_24
  episode_29
  episode_50
)

cd "${LEROBOT_ROOT}"

for ep in "${episodes[@]}"; do
  root="${DATASET_PREFIX}/${ep}"

  echo "========================================"
  echo "Converting ${root}"
  echo "========================================"

  if [[ ! -d "${root}" ]]; then
    echo "[SKIP] not found: ${root}"
    continue
  fi

  # 已经是 v3.0 的跳过，避免重复转换时报错
  version="$(python - <<PY
import json, pathlib
p = pathlib.Path("${root}") / "meta" / "info.json"
if not p.exists():
    print("missing")
else:
    print(json.loads(p.read_text()).get("codebase_version", "unknown"))
PY
)"

  if [[ "${version}" == "v3.0" ]]; then
    echo "[SKIP] already v3.0: ${ep}"
    continue
  fi

  if [[ "${version}" != "v2.1" ]]; then
    echo "[SKIP] ${ep}: codebase_version=${version}, expected v2.1"
    continue
  fi

  python "${CONVERTER}" \
    --repo-id="local/${ep}" \
    --root="${root}" \
    --push-to-hub=false

  echo "[DONE] ${ep}"
done

echo "All requested episodes processed."