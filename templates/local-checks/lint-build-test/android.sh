#!/bin/sh
# lint, build, unit test — git pre-push hook 이 push 직전에 실행한다.
# 비공개 저장소에서 GitHub Actions 사용량을 쓰지 않으려고 workflow 대신 로컬에서 실행한다.
# 명령은 프로젝트 모듈 구성에 맞게 수정해도 된다.
set -e
cd "$(git rev-parse --show-toplevel)"

./gradlew :app:lintDebug
./gradlew :app:assembleDebug
./gradlew :app:testDebugUnitTest
