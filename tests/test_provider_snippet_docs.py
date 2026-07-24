"""Provider wrapper snippet documentation regression tests."""
from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PROVIDER_WRAPPER_PATTERN = re.compile(
    r'"\$PLUGIN_ROOT/scripts/(?:dcness-codex-validator|dcness-implementation-chain)"'
)

PLUGIN_ROOT_PRELUDE = '''PLUGIN_ROOT=""
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT/scripts" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(ls -d "$HOME/.claude/plugins/cache/dcness/dcness/"* 2>/dev/null | sort -V | tail -1)"
fi
[ -n "$PLUGIN_ROOT" ] || { echo "[dcness] plugin root not found" >&2; exit 1; }
HELPER="$PLUGIN_ROOT/scripts/dcness-helper"'''


class ProviderSnippetDocsTests(unittest.TestCase):
    """Published provider snippets must resolve the active plugin root first."""

    def _published_docs(self):
        for base in (ROOT / "docs" / "plugin", ROOT / "skills"):
            yield from base.rglob("*.md")

    def test_provider_wrapper_snippets_define_plugin_root_recipe(self) -> None:
        """Provider snippets should work from an activated external project shell."""
        docs_with_wrappers: list[Path] = []
        for path in self._published_docs():
            text = path.read_text(encoding="utf-8")
            wrappers = list(PROVIDER_WRAPPER_PATTERN.finditer(text))
            if not wrappers:
                continue

            docs_with_wrappers.append(path.relative_to(ROOT))
            prelude_index = text.find(PLUGIN_ROOT_PRELUDE)
            self.assertNotEqual(
                prelude_index,
                -1,
                f"{path.relative_to(ROOT)} lacks the shared PLUGIN_ROOT prelude",
            )
            self.assertLess(
                prelude_index,
                min(match.start() for match in wrappers),
                f"{path.relative_to(ROOT)} resolves PLUGIN_ROOT after wrapper use",
            )

        expected = {
            Path("docs/plugin/loop-procedure.md"),
            Path("skills/design/SKILL.md"),
            Path("skills/impl-loop/SKILL.md"),
        }
        self.assertTrue(
            expected.issubset(set(docs_with_wrappers)),
            f"provider docs missing from scan: {expected - set(docs_with_wrappers)}",
        )

    def test_plugin_root_prelude_prefers_active_env_then_latest_cache(self) -> None:
        """The shared prelude should avoid stale cache versions."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cache = home / ".claude" / "plugins" / "cache" / "dcness" / "dcness"
            for version in ("0.2.0", "0.10.0"):
                (cache / version / "scripts").mkdir(parents=True)

            script = f"{PLUGIN_ROOT_PRELUDE}\nprintf '%s\\n' \"$PLUGIN_ROOT\"\n"
            env = {"HOME": str(home), "CLAUDE_PLUGIN_ROOT": ""}
            result = subprocess.run(
                ["bash", "-c", script],
                check=True,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), str(cache / "0.10.0"))

            active = home / "active-plugin"
            (active / "scripts").mkdir(parents=True)
            env["CLAUDE_PLUGIN_ROOT"] = str(active)
            result = subprocess.run(
                ["bash", "-c", script],
                check=True,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), str(active))


if __name__ == "__main__":
    unittest.main()
