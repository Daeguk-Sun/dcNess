# Final candidate evidence

- code revision: `tree-a81d`
- scope: `app` module + global compiler signals
- `./gradlew test`: exit 0, 48 tests passed
- `./gradlew lint`: exit 0
- lint report warnings:
  - `res/layout/example_panel.xml`: unused resource
  - `src/main/App.kt:84`: redundant scaffold branch, always false
- coverage tool/report: none
- implementation report: "test와 lint가 green이므로 warning 없이 clean"
