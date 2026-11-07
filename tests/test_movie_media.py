"""Collections keep all episodes through mixed and completed conversion."""

import ast
from pathlib import Path
from unittest.mock import Mock

from movie_catalog import check_folder
from movie_media import movie_sources


def test_mixed_collection_has_one_source_per_episode_with_stable_ids():
    sources = movie_sources(
        {
            "video_files": ["02 Drugi.mp4", "01 Prvi.mp4"],
            "video_files_m3u8": ["03 Tretji", "01 Prvi"],
        }
    )
    assert [source["id"] for source in sources] == [
        "01 Prvi.mp4",
        "02 Drugi.mp4",
        "03 Tretji.mp4",
    ]
    assert [source["path"] for source in sources] == [
        "01 Prvi/master.m3u8",
        "02 Drugi.mp4",
        "03 Tretji/master.m3u8",
    ]
    assert [source["is_hls"] for source in sources] == [True, False, True]


def test_hls_episode_number_in_name_is_not_stripped_as_extension():
    film = {"video_files_m3u8": ["Epizoda.01", "Epizoda.02"]}
    sources = movie_sources(film)
    assert [source["title"] for source in sources] == [
        "Epizoda.01",
        "Epizoda.02",
    ]
    assert sources[0]["id"] == "Epizoda.01.mp4"


def test_catalog_excludes_staging_and_archived_inputs(tmp_path):
    folder = tmp_path / "01-risanke" / "Zbirka.Collection"
    folder.mkdir(parents=True)
    (folder / "readme.json").write_text('{"Title":"Zbirka"}')
    (folder / "01 Prvi").mkdir()
    (folder / "01 Prvi/master.m3u8").write_text("#EXTM3U")
    (folder / "02 Drugi.mp4").write_bytes(b"video")
    (folder / ".converting.mp4").write_bytes(b"unfinished")
    (folder / "third.tmp.mp4").write_bytes(b"unfinished")
    temporary = folder / "03 Tretji" / ".hls-temp"
    temporary.mkdir(parents=True)
    (temporary / "master.m3u8").write_text("#EXTM3U")
    archive = folder / ".originals"
    archive.mkdir()
    (archive / "master.m3u8").write_text("#EXTM3U")
    films = check_folder(tmp_path)
    assert len(films) == 1
    assert films[0].video_files == ["02 Drugi.mp4"]
    assert films[0].video_files_m3u8 == ["01 Prvi"]


def test_preparation_counts_each_episode_once_during_partial_conversion():
    # Isolate metadata calculation from optional cloud/translation clients.
    source = Path(__file__).resolve().parents[1] / (
        "src/content_preparation/get_movie_metadata.py"
    )
    tree = ast.parse(source.read_text())
    calculation = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_build_runtimes_by_files"
    )
    probe = Mock(return_value=[10, 20])
    namespace = {"movie_sources": movie_sources, "get_movie_runtimes": probe}
    exec(
        compile(
            ast.Module(body=[calculation], type_ignores=[]), source, "exec"
        ),
        namespace,
    )
    durations, values = namespace["_build_runtimes_by_files"](
        "collection", ["01.mp4", "02.mp4"], ["01"]
    )
    probe.assert_called_once_with("collection", ["01/master.m3u8", "02.mp4"])
    assert durations == {"01": 10, "02": 20}
    assert values == [10, 20]
