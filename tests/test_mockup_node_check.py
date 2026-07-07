"""mockup_node_check — 확정 목업 data-node-id 대조 helper 검증 (#989)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.mockup_node_check import check_mockup_nodes


class MockupNodeCheckTests(unittest.TestCase):
    def test_reports_missing_node_ids_from_impl_design_reference(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mockup_dir = root / "docs" / "design-variants"
            mockup_dir.mkdir(parents=True)
            (mockup_dir / "checkout.html").write_text(
                """
                <main data-node-id="checkout.root">
                  <button data-node-id='checkout.pay'>Pay</button>
                </main>
                """,
                encoding="utf-8",
            )
            impl = root / "docs" / "epics" / "epic-1" / "impl" / "01-pay.md"
            impl.parent.mkdir(parents=True)
            impl.write_text(
                """
## 디자인 참조

- 확정 목업 경로: `docs/design-variants/checkout.html`
- 핵심 `data-node-id` → 구현 컴포넌트/상태:
  - `checkout.root` → CheckoutScreen
  - `checkout.missing` → MissingState

## Scope
""",
                encoding="utf-8",
            )

            payload = check_mockup_nodes([str(impl)], mockup_dir=mockup_dir)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["missing_node_ids"], ["checkout.missing"])
        self.assertEqual(payload["files"][0]["existing_node_ids"], ["checkout.root"])
        self.assertEqual(payload["files"][0]["missing_node_ids"], ["checkout.missing"])

    def test_confirmed_mockup_scan_ignores_canvas_and_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mockup_dir = root / "docs" / "design-variants"
            (mockup_dir / "drafts").mkdir(parents=True)
            (mockup_dir / "canvas.html").write_text(
                '<div data-node-id="checkout.missing"></div>',
                encoding="utf-8",
            )
            (mockup_dir / "drafts" / "checkout-draft1.html").write_text(
                '<main data-node-id="checkout.missing"></main>',
                encoding="utf-8",
            )
            (mockup_dir / "checkout.html").write_text(
                '<main data-node-id="checkout.root"></main>',
                encoding="utf-8",
            )
            impl = root / "impl" / "01-pay.md"
            impl.parent.mkdir()
            impl.write_text(
                """
## 디자인 참조

- 핵심 `data-node-id` → 구현 컴포넌트/상태:
  - `checkout.missing` → MissingState

## Scope
""",
                encoding="utf-8",
            )

            payload = check_mockup_nodes([str(impl.parent)], mockup_dir=mockup_dir)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["mockup_files"], [str(mockup_dir / "checkout.html")])
        self.assertEqual(payload["missing_node_ids"], ["checkout.missing"])

    def test_right_side_backticked_component_name_is_not_treated_as_node_id(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mockup_dir = root / "docs" / "design-variants"
            mockup_dir.mkdir(parents=True)
            (mockup_dir / "checkout.html").write_text(
                '<button data-node-id="checkout.pay">Pay</button>',
                encoding="utf-8",
            )
            impl = root / "impl" / "01-pay.md"
            impl.parent.mkdir()
            impl.write_text(
                """
## 디자인 참조

- 핵심 `data-node-id` → 구현 컴포넌트/상태:
  - `checkout.pay` → `PayButton`

## Scope
""",
                encoding="utf-8",
            )

            payload = check_mockup_nodes([str(impl)], mockup_dir=mockup_dir)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["cited_node_ids"], ["checkout.pay"])
        self.assertEqual(payload["missing_node_ids"], [])

    def test_data_node_id_label_without_arrow_is_supported(self) -> None:
        text = """
## 디자인 참조

- data-node-id: `checkout.pay`

## Scope
"""
        from harness.mockup_node_check import extract_design_reference_node_ids

        self.assertEqual(extract_design_reference_node_ids(text), ["checkout.pay"])

    def test_missing_impl_input_reports_error_instead_of_empty_success(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mockup_dir = root / "docs" / "design-variants"
            mockup_dir.mkdir(parents=True)
            (mockup_dir / "checkout.html").write_text(
                '<main data-node-id="checkout.root"></main>',
                encoding="utf-8",
            )

            payload = check_mockup_nodes(
                [str(root / "docs" / "epics" / "missing" / "impl")],
                mockup_dir=mockup_dir,
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["files"], [])
        self.assertEqual(
            payload["input_errors"],
            [
                {
                    "path": str(root / "docs" / "epics" / "missing" / "impl"),
                    "reason": "not_found_or_no_markdown",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
