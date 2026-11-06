"""Use the same content-addressed static release as the Nginx image."""

from pathlib import Path

from flask import url_for


def asset_url(filename, **values):
    return url_for("static", filename=filename, **values)


def init_static_assets(app):
    manifest = Path(app.static_folder).parent / "static-version"
    version = (
        manifest.read_text(encoding="ascii").strip()
        if manifest.exists()
        else ""
    )
    app.config["STATIC_ASSET_VERSION"] = version
    app.jinja_env.globals["asset_url"] = asset_url

    @app.url_defaults
    def version_static_url(endpoint, values):
        filename = values.get("filename")
        if (
            endpoint == "static"
            and version
            and filename
            and not filename.startswith("v/")
        ):
            values["filename"] = f"v/{version}/{filename}"
