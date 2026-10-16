from .config import FILMS_ROOT  # noqa: F401


def process_audio_folders(*args, **kwargs):
    from .audio_preparation import process_audio_folders as process

    return process(*args, **kwargs)


def is_ffmpeg_installed():
    from .helpers import is_ffmpeg_installed as check

    return check()


def check_folder(*args, **kwargs):
    from .main import check_folder as check

    return check(*args, **kwargs)
