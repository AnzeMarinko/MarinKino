"""Start the same bounded workers for development and production servers."""


def start_background_workers(app):
    from mail_jobs import deliver_blog_mail_job, deliver_mail_job
    from movie_downloads import build_archive_job

    return app.extensions["jobs"].start_worker(
        {
            "mail": deliver_mail_job,
            "blog_mail": deliver_blog_mail_job,
            "archive": build_archive_job,
        }
    )
