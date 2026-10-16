"""Administrator preview changes require CSRF and cannot redirect off-site."""

import pytest
from bs4 import BeautifulSoup
from test_blog_images import ui as image_ui_fixture

ui = image_ui_fixture


def csrf(ui):
    ui.app.config["WTF_CSRF_ENABLED"] = True
    html = ui.client.get("/admin/blog/new").text
    return BeautifulSoup(html, "html.parser").select_one(
        "input[name=csrf_token]"
    )["value"]


@pytest.mark.parametrize(
    "path", ["/admin/set-view-as/user", "/admin/clear-view-as"]
)
def test_preview_changes_refuse_get_and_unprotected_post(ui, path):
    csrf(ui)
    assert ui.client.get(path).status_code == 405
    assert ui.client.post(path).status_code == 400


def test_preview_change_accepts_csrf_and_stores_selected_mode(ui):
    token = csrf(ui)
    assert (
        ui.client.post(
            "/admin/set-view-as/user", data={"csrf_token": token}
        ).status_code
        == 302
    )
    with ui.client.session_transaction() as session:
        assert session["view_as"] == "user"


@pytest.mark.parametrize(
    "referrer,expected",
    [
        ("https://attacker.invalid/phishing", "/admin"),
        ("http://localhost/movies?sort=title_asc", "/movies?sort=title_asc"),
    ],
)
def test_return_from_preview_only_redirects_to_local_origin(
    ui, referrer, expected
):
    token = csrf(ui)
    response = ui.client.post(
        "/admin/clear-view-as",
        data={"csrf_token": token},
        headers={"Referer": referrer},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == expected
