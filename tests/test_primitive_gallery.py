import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from morphea.cli import main
from morphea.primitive_gallery import write_primitive_gallery_site


class PrimitiveGalleryTests(unittest.TestCase):
    def test_gallery_generator_writes_report_artifacts_and_html(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "site" / "assets" / "primitive-quality" / "report.json"
            output_dir = root / "site" / "assets" / "primitive-quality" / "cases"
            markdown = root / "site" / "assets" / "primitive-quality" / "report.md"
            html = root / "site" / "primitive-quality" / "index.html"

            report = write_primitive_gallery_site(
                output=output,
                output_dir=output_dir,
                markdown=markdown,
                html_output=html,
                homepage=None,
                cases=("filled_square", "cutout_horizontal_gap_center"),
            )

            self.assertTrue(report["ok"])
            self.assertEqual(report["case_count"], 2)
            html_text = html.read_text(encoding="utf-8")
            self.assertEqual(html_text.count('class="case-card"'), 2)
            self.assertIn("filled_square", html_text)
            self.assertIn("cutout_horizontal_gap", html_text)
            self.assertIn('<option value="filled_square">', html_text)
            for case in report["cases"]:
                artifacts = case["artifacts"]
                for key in ("input", "output_svg", "manifest", "preview"):
                    self.assertTrue(Path(artifacts[key]).exists(), key)
            cutout = [
                case
                for case in report["cases"]
                if case["id"] == "cutout_horizontal_gap_center"
            ][0]
            self.assertTrue(cutout["export_comparison"]["ok"])
            self.assertTrue(Path(cutout["artifacts"]["negative_mask_svg"]).exists())

    def test_gallery_generator_refreshes_homepage_teaser_markers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            homepage = root / "site" / "index.html"
            homepage.parent.mkdir(parents=True)
            homepage.write_text(
                "\n".join(
                    [
                        "<section>",
                        "<!-- primitive-gallery-teaser:start -->",
                        "old",
                        "<!-- primitive-gallery-teaser:end -->",
                        "</section>",
                    ]
                ),
                encoding="utf-8",
            )

            write_primitive_gallery_site(
                output=root / "site" / "assets" / "primitive-quality" / "report.json",
                output_dir=root / "site" / "assets" / "primitive-quality" / "cases",
                markdown=root / "site" / "assets" / "primitive-quality" / "report.md",
                html_output=root / "site" / "primitive-quality" / "index.html",
                homepage=homepage,
                cases=("filled_square",),
            )

            updated = homepage.read_text(encoding="utf-8")
            self.assertNotIn("old", updated)
            self.assertIn("Primitive quality gallery: 1 passing cases", updated)
            self.assertIn("filled_square/input.png", updated)

    def test_gallery_generator_refreshes_homepage_hero_markers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            homepage = root / "site" / "index.html"
            homepage.parent.mkdir(parents=True)
            homepage.write_text(
                "\n".join(
                    [
                        "<section>",
                        "<!-- primitive-gallery-hero:start -->",
                        "old hero",
                        "<!-- primitive-gallery-hero:end -->",
                        "<!-- primitive-gallery-teaser:start -->",
                        "old teaser",
                        "<!-- primitive-gallery-teaser:end -->",
                        "</section>",
                    ]
                ),
                encoding="utf-8",
            )

            write_primitive_gallery_site(
                output=root / "site" / "assets" / "primitive-quality" / "report.json",
                output_dir=root / "site" / "assets" / "primitive-quality" / "cases",
                markdown=root / "site" / "assets" / "primitive-quality" / "report.md",
                html_output=root / "site" / "primitive-quality" / "index.html",
                homepage=homepage,
                cases=("filled_square",),
            )

            updated = homepage.read_text(encoding="utf-8")
            self.assertNotIn("old hero", updated)
            self.assertIn("hero-proof-panel", updated)
            self.assertIn("Bitmap and exported SVG, same canvas.", updated)
            self.assertIn("filled_square/output.svg", updated)

    def test_primitive_gallery_cli_writes_static_site(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "report.json"
            output_dir = root / "cases"
            markdown = root / "report.md"
            html = root / "index.html"

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "primitive-gallery",
                        "-o",
                        str(output),
                        "--output-dir",
                        str(output_dir),
                        "--markdown",
                        str(markdown),
                        "--html",
                        str(html),
                        "--no-homepage",
                        "--case",
                        "filled_square",
                    ]
                )

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["case_count"], 1)
            self.assertTrue(html.exists())
            self.assertTrue((output_dir / "filled_square" / "output.svg").exists())
            self.assertIn("wrote primitive gallery with 1 cases", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
