"""Release URLs stay immutable and reference the assets packaged for Nginx."""

import gzip
import importlib.util
from pathlib import Path

import pytest
from flask import Flask, render_template_string, url_for

from static_assets import init_static_assets

SPEC = importlib.util.spec_from_file_location(
    "package_static",
    Path(__file__).resolve().parents[1] / "scripts/package_static.py",
)
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


def test_changed_asset_gets_new_release_without_changing_old_bytes(tmp_path):
    static = tmp_path / "static"
    (static / "css").mkdir(parents=True)
    (static / "css/site.css").write_text("body { color: black; }\n" * 100)
    manifest = tmp_path / "static-version"
    first = package.package_static(static, manifest)
    old_file = static / "v" / first / "css/site.css"
    assert (
        gzip.decompress(old_file.with_suffix(".css.gz").read_bytes())
        == old_file.read_bytes()
    )
    assert package.package_static(static, manifest) == first
    (static / "css/site.css").write_text("body { color: green; }\n" * 100)
    second = package.package_static(static, manifest)
    assert first != second
    assert b"black" in old_file.read_bytes()
    assert b"green" in (static / "v" / second / "css/site.css").read_bytes()
    assert manifest.read_text().strip() == second


def test_packaging_refuses_file_symlink(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    private = tmp_path / "secret"
    private.write_text("secret")
    (static / "public.txt").symlink_to(private)
    with pytest.raises(ValueError, match="symlinks"):
        package.package_static(static, tmp_path / "static-version")


def test_generated_urls_resolve_to_packaged_release_and_keep_query(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "site.js").write_text("console.log('release');")
    version = package.package_static(static, tmp_path / "static-version")
    app = Flask(__name__, static_folder=str(static), static_url_path="/static")
    init_static_assets(app)
    with app.test_request_context():
        url = url_for("static", filename="site.js", mode="test")
        assert url == f"/static/v/{version}/site.js?mode=test"
        assert (
            render_template_string("{{ asset_url('site.js') }}")
            == url.split("?")[0]
        )
    assert app.test_client().get(url).data == b"console.log('release');"


def test_checkout_without_build_manifest_uses_normal_static_urls(tmp_path):
    app = Flask(
        __name__,
        static_folder=str(tmp_path / "static"),
        static_url_path="/static",
    )
    init_static_assets(app)
    with app.test_request_context():
        assert url_for("static", filename="site.js") == "/static/site.js"
