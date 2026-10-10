"""Public blog pagination and shared SEO/excerpt persistence."""

import pytest
from bs4 import BeautifulSoup
from test_blog_publication_mail import publication as publication_fixture
from test_blog_translation import blog as blog_fixture

blog = blog_fixture
publication = publication_fixture


@pytest.fixture
def many_posts(blog):
    blog.posts.clear()
    for number in range(1, 27):
        slug = f"post-{number}"
        blog.posts[slug] = dict(
            id=slug,
            title=f"Objava {number}",
            published=True,
            created_at=f"2026-09-{number:02d}T12:00:00+00:00",
            content=f"Vsebina {number}",
            excerpt=f"Izvleček {number}",
            seo_description="Čebelice in čaroben dan"
            if number == 1
            else f"SEO {number}",
        )
    blog.posts["draft"] = dict(
        blog.posts["post-1"],
        id="draft",
        title="Skriti osnutek",
        published=False,
    )
    return blog


def html(blog, path):
    response = blog.app.test_client().get(path)
    assert response.status_code == 200
    return BeautifulSoup(response.text, "html.parser")


def test_server_sends_twelve_cards_and_lightweight_full_index(many_posts):
    first = html(many_posts, "/blog")
    second = html(many_posts, "/blog?page=2")
    third = html(many_posts, "/blog?page=3")
    assert [
        len(page.select("[data-blog-post]")) for page in [first, second, third]
    ] == [12, 12, 2]
    assert first.select_one("[data-blog-post] h3").text == "Objava 26"
    assert third.select("[data-blog-post] h3")[-1].text == "Objava 1"
    assert len(first.select("#blogIndex a")) == 26
    assert len(first.select("#blogIndex time")) == 26
    assert "Skriti osnutek" not in first.text
    assert (
        "Čebelice in čaroben dan" not in first.select_one("#blog-results").text
    )
    assert len(second.select(".blog-post-featured")) == 0


@pytest.mark.parametrize(
    "page,expected", [("nope", 12), ("0", 12), ("-4", 12), ("999", 2)]
)
def test_invalid_and_out_of_range_pages(many_posts, page, expected):
    assert (
        len(html(many_posts, f"/blog?page={page}").select("[data-blog-post]"))
        == expected
    )


def test_search_covers_unloaded_posts_and_partial_respects_visibility(
    many_posts,
):
    result = html(many_posts, "/blog?q=cebelice&partial=1")
    assert len(result.select("[data-blog-post]")) == 1
    assert "Objava 1" in result.text
    assert "Izvleček 1" not in result.text
    assert "Čebelice in čaroben dan" in result.text
    assert result.select_one("header") is None
    assert "Skriti osnutek" not in html(many_posts, "/blog?q=skriti").text
    assert html(many_posts, "/blog?q=neobstojece").select_one("#blogNoResults")


@pytest.mark.parametrize("path", ["/admin/blog/new", "/admin/blog/edit/javno"])
def test_seo_description_is_saved_as_excerpt(publication, path):
    response = publication.client.post(
        path,
        data=dict(
            title="Nov naslov",
            content="Vsebina",
            seo_description=" Enoten opis ",
            excerpt="Ignoriran stari izvleček",
        ),
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.json["success"]
    posts = publication.module.load_blog_posts()
    post = posts[response.json.get("post_id", "javno")]
    assert post["excerpt"] == post["seo_description"] == "Enoten opis"
