import json
import logging
import os
from datetime import date, datetime, timezone

import pandas as pd
from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from movies_preparation.config import LOG_FILENAME
from utils import is_current_admin_view, redis_client

log = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__)

users = {}

BLOG_DATA_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "blog_posts.json"
)
BLOG_IMAGES_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "blog_images")


def save_blog_image(file):
    if not file:
        return None
    filename = secure_filename(file.filename)
    if not filename:
        return None
    os.makedirs(BLOG_IMAGES_DIR, exist_ok=True)
    filepath = os.path.join(BLOG_IMAGES_DIR, filename)
    file.save(filepath)
    return f"/static/blog_images/{filename}"


def init_admin_bp(_users):
    """Initialize blueprint with app context"""
    global users
    users = _users


def load_blog_posts():
    if os.path.exists(BLOG_DATA_FILE):
        with open(BLOG_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_blog_posts(posts):
    os.makedirs(os.path.dirname(BLOG_DATA_FILE), exist_ok=True)
    with open(BLOG_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


@admin_bp.route("/admin")
@login_required
def admin_panel():
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))

    access_stats_users = {}
    access_stats_routes = {}

    user_counter = {}

    for key in redis_client.scan_iter("stats:daily:*"):
        parts = key.split(":")
        if len(parts) < 5:
            continue

        log_date = parts[2]
        user_id = parts[3]
        status = parts[4][0] + "xx"

        routes_data = redis_client.hgetall(key)

        access_stats_routes.setdefault(log_date, {})
        access_stats_users.setdefault(status, {})
        access_stats_users[status].setdefault(log_date, {})
        access_stats_users[status][log_date].setdefault(user_id, {})

        for route_method, count in routes_data.items():
            access_stats_users[status][log_date][user_id].setdefault("routes", {})
            access_stats_users[status][log_date][user_id]["routes"].setdefault(
                route_method, 0
            )
            access_stats_users[status][log_date][user_id]["routes"][route_method] += (
                int(count)
            )
            access_stats_users[status][log_date][user_id].setdefault("count", 0)
            access_stats_users[status][log_date][user_id]["count"] += int(count)
            if status.startswith("2") or status.startswith("3"):
                user_counter.setdefault(user_id, 0)
                user_counter[user_id] += int(count)
                route = "/" + "/".join(route_method.split("/")[1:2])
                access_stats_routes[log_date].setdefault(route, 0)
                access_stats_routes[log_date][route] += int(count)

    if access_stats_users:
        for k1, v1 in access_stats_users.items():
            for k2, v2 in v1.items():
                for k3, v3 in v2.items():
                    access_stats_users[k1][k2][k3]["routes"] = "\n".join(
                        [
                            v[1]
                            for v in sorted(
                                [
                                    (int(count), f"{count}x {route_method}")
                                    for route_method, count in v3["routes"].items()
                                ],
                                reverse=True,
                            )[:10]
                        ]
                    )
                access_stats_users[k1][k2] = {
                    k: v
                    for k, v in sorted(
                        list(access_stats_users[k1][k2].items()),
                        key=lambda x: -user_counter[x[0]],
                    )
                    if v
                }
            access_stats_users[k1] = {
                k: v for k, v in sorted(list(access_stats_users[k1].items())) if v
            }
        access_stats_users = {
            k: v for k, v in sorted(list(access_stats_users.items())) if v
        }

    if access_stats_routes:
        df_routes = pd.DataFrame(access_stats_routes).T
        access_stats_routes = df_routes.fillna(0).astype(int)
        access_stats_routes = access_stats_routes[
            sorted(access_stats_routes.columns, reverse=True)
        ].T
        access_stats_routes["total"] = access_stats_routes.sum(axis=1)
        access_stats_routes = (
            access_stats_routes.sort_values(by="total", ascending=False)
            .drop(columns=["total"])
            .head(10)
        )
        access_stats_routes = access_stats_routes.to_dict()

    access_stats_monthly = {}

    for key in redis_client.scan_iter("stats:monthly:*"):
        month_label = key.split(":")[-1]
        monthly_data = redis_client.hgetall(key)
        access_stats_monthly[month_label] = {}
        for route_method, count in monthly_data.items():
            route = "/" + "/".join(route_method.split("/")[1:3])
            access_stats_monthly[month_label][route] = access_stats_monthly[
                month_label
            ].get(route, 0) + int(count)

    if access_stats_monthly:
        df_monthly = pd.DataFrame(access_stats_monthly).T.fillna(0).astype(int)
        df_monthly = df_monthly[sorted(df_monthly.columns, reverse=True)].T
        df_monthly["total"] = df_monthly.sum(axis=1)
        df_monthly = (
            df_monthly.sort_values(by="total", ascending=False)
            .drop(columns=["total"])
            .head(20)
            .T
        )
        access_stats_monthly_dict = df_monthly.to_dict(orient="index")
        monthly_columns = df_monthly.columns
    else:
        access_stats_monthly_dict = {}
        monthly_columns = []

    users_stats = {}
    user_prog_keys = redis_client.keys("prog:*")

    for key in user_prog_keys:
        user_id = key.split(":")[1]
        user_data_raw = redis_client.hgetall(key)

        total_watch_time = 0
        watch_ratios = []
        watched_count = 0
        starting_count = 0
        last_start_time = "-"

        for video_file, progress_json in user_data_raw.items():
            progress = json.loads(progress_json)

            watch_time = progress.get("total_play_time", 0)
            duration = progress.get("duration", 0)
            current_max_start = progress.get("last_start_time")

            if watch_time and duration:
                ratio = (watch_time / duration) * 100
                if ratio < 5:
                    continue
                watch_ratios.append(ratio)
                starting_count += 1
                if ratio >= 70:
                    watched_count += 1

                if current_max_start:
                    if last_start_time == "-" or current_max_start > last_start_time:
                        last_start_time = current_max_start

                total_watch_time += watch_time

        def seconds_to_str(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes:02}m"

        users_stats[user_id] = {
            "Skupen čas": seconds_to_str(total_watch_time),
            "Število začetih": starting_count,
            "Število ogledanih": watched_count,
            "Povprečen delež ogleda": f"{round(sum(watch_ratios) / len(watch_ratios), 1) if watch_ratios else 0} %",
            "Zadnji začetek ogleda": last_start_time,
        }

    if users_stats:
        df_users = pd.DataFrame(users_stats).T.sort_values(
            by=["Število ogledanih", "Skupen čas"], ascending=False
        )
        users_stats_dict = df_users.to_dict(orient="index")
        users_stats_columns = df_users.columns
    else:
        users_stats_dict = {}
        users_stats_columns = []

    if os.path.exists(LOG_FILENAME):
        with open(
            LOG_FILENAME,
            "r",
            encoding="utf-8",
        ) as f:
            lines = [l.split(" - ") for l in f.read().split("\n")]
            new_lines = []
            last_line = lines[0]
            for line in lines[1:]:
                if (
                    len(last_line) < 4
                    or len(line) < 4
                    or line[3] != last_line[3]
                    or line[2] != last_line[2]
                ):
                    new_lines.append(" - ".join(last_line))
                    last_line = line
                else:
                    last_line[0] = last_line[0].split(" <-> ")[0] + " <-> " + line[0]
                    last_line[1] = (
                        str(int(last_line[1].replace("x", "")) + int(line[1])) + "x"
                    )
            new_lines.append(" - ".join(last_line))

            system_log = "\n".join(new_lines[-500:])
        with open(
            LOG_FILENAME,
            "w",
            encoding="utf-8",
        ) as f:
            f.write("\n".join(new_lines))
    else:
        system_log = "Missing log file!"

    # Calculate top 20 movies by total watch ratio
    movies_watch_stats = {}

    for key in user_prog_keys:
        # Decode key if it's bytes
        if isinstance(key, bytes):
            key = key.decode("utf-8")

        user_id = key.split(":")[1]
        user_data_raw = redis_client.hgetall(key)

        for video_file, progress_json in user_data_raw.items():
            # Decode if bytes
            if isinstance(video_file, bytes):
                video_file = video_file.decode("utf-8")
            if isinstance(progress_json, bytes):
                progress_json = progress_json.decode("utf-8")

            progress = json.loads(progress_json)
            watch_time = progress.get("total_play_time", 0)
            duration = progress.get("duration", 0)

            if watch_time and duration:
                ratio = (watch_time / duration) * 100
                if ratio < 5:
                    continue

                # Extract movie folder path from video file path
                # video_file is like: "path/to/movie/video.mp4"
                # We need to extract the folder part (everything except the filename)
                parts = video_file.split(os.sep)
                if len(parts) >= 2:
                    # Remove the last part (video filename) to get the movie folder
                    movie_folder = os.sep.join(parts[:-1])

                    if movie_folder not in movies_watch_stats:
                        movies_watch_stats[movie_folder] = {
                            "total_ratio": 0,
                            "count": 0,
                            "users": set(),
                            "total_duration": 0,
                        }

                    movies_watch_stats[movie_folder]["total_ratio"] += ratio
                    movies_watch_stats[movie_folder]["count"] += 1
                    movies_watch_stats[movie_folder]["users"].add(user_id)
                    movies_watch_stats[movie_folder]["total_duration"] += duration

    # Calculate averages and sort
    top_movies = []
    for movie_folder, stats in movies_watch_stats.items():
        avg_ratio = stats["total_ratio"] / stats["count"] if stats["count"] > 0 else 0
        total_watch_hours = stats["total_duration"] / 3600

        top_movies.append(
            {
                "folder": movie_folder,
                "total_ratio": round(stats["total_ratio"], 1),
                "avg_ratio": round(avg_ratio, 1),
                "watch_count": stats["count"],
                "unique_users": len(stats["users"]),
                "total_watch_hours": round(total_watch_hours, 1),
            }
        )

    # Sort by total_ratio (highest first) and get top 20
    top_movies_sorted = sorted(
        top_movies, key=lambda x: x["total_ratio"], reverse=True
    )[:20]

    # Blog statistics
    blog_views_daily = {}
    total_views = 0
    blog_total_hash = redis_client.hgetall("blog:views:total")
    for date, views in blog_total_hash.items():
        blog_views_daily[date] = int(views)
        total_views += int(views)

    blog_posts = load_blog_posts()
    blog_stats = []
    total_reading_time = 0
    for post_id, post in blog_posts.items():
        views_key = f"blog:views:{post_id}"
        post_views = sum(int(v) for v in redis_client.hvals(views_key))
        reading_time = 0
        for key in redis_client.scan_iter(f"blog:reading:{post_id}:*"):
            parts = key.split(":")
            if len(parts) >= 4:
                reading_data = redis_client.hgetall(key)
                for time_str in reading_data.values():
                    time_seconds = int(time_str)
                    total_reading_time += time_seconds
                    reading_time += time_seconds
        blog_stats.append(
            {
                "id": post_id,
                "title": post["title"],
                "views": post_views,
                "created_at": post["created_at"],
                "reading_time": reading_time,
            }
        )

    # Referrer statistics
    referrer_stats = {}
    for key in redis_client.scan_iter("stats:referrer:*"):
        date_part = key.split(":")[-1]
        referrer_data = redis_client.hgetall(key)
        for source, count in referrer_data.items():
            referrer_stats.setdefault(source, {})
            referrer_stats[source][date_part] = int(count)

    # Geolocation statistics
    geo_stats = {}
    geo_stats_cities = {}
    for key in redis_client.scan_iter("stats:geo:*"):
        date_part = key.split(":")[-1]
        geo_data = redis_client.hgetall(key)
        for ip, location_json in geo_data.items():
            try:
                location = json.loads(location_json)
                country = location.get("country", "Unknown")
                city = location.get("city", "Unknown")
                city_key = f"{city} ({country})"
                city = city_key if country == "SI" else country
                geolocation = location.get("geolocation", "").split(",")

                geo_stats.setdefault(city, 0)
                geo_stats[city] += 1
                geo_stats_cities.setdefault(city_key, {"count": 0})
                geo_stats_cities[city_key]["count"] += 1
                if len(geolocation) == 2:
                    geo_stats_cities[city_key]["geolocation"] = (
                        float(geolocation[0]),
                        float(geolocation[1]),
                    )
            except:
                continue
    geo_stats = dict(sorted(geo_stats.items(), key=lambda x: -x[1]))

    return render_template(
        "admin.html",
        pagetitle="MarinKino - Nadzorna plošča",
        system_log=system_log,
        access_stats_users=access_stats_users,
        users=list(sorted(user_counter.keys(), key=lambda x: -user_counter[x])),
        emails=", ".join([e for u in users for e in users[u].get("emails", [])]),
        users_count=len(users),
        access_stats_routes=access_stats_routes,
        users_stats=users_stats_dict,
        users_stats_columns=users_stats_columns,
        access_stats_monthly=access_stats_monthly_dict,
        monthly_columns=monthly_columns,
        top_movies=top_movies_sorted,
        blog_views_daily=blog_views_daily,
        blog_stats=blog_stats,
        total_blog_views=total_views,
        referrer_stats=referrer_stats,
        geo_stats=geo_stats,
        geo_stats_cities=geo_stats_cities,
        total_reading_time=total_reading_time,
    )


@admin_bp.route("/admin/set-view-as/<view_mode>")
@login_required
def set_view_as(view_mode):
    """Set the view mode for admin preview (anonymous, user, admin)"""
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for("home"))

    if view_mode in ["anonymous", "user", "admin"]:
        session["view_as"] = view_mode
    else:
        session.pop("view_as", None)

    return redirect(url_for("home"))


@admin_bp.route("/admin/clear-view-as")
@login_required
def clear_view_as():
    """Clear the view as mode"""
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for("home"))

    session.pop("view_as", None)
    return redirect(request.referrer or url_for("admin.admin_panel"))


@admin_bp.route("/admin/blog")
@login_required
def admin_blog():
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))

    posts = load_blog_posts()
    sorted_posts = sorted(
        posts.values(), key=lambda x: x.get("created_at", ""), reverse=True
    )

    # Get view stats for each post and format dates
    for post in sorted_posts:
        views_key = f"blog:views:{post['id']}"
        post["views"] = sum(int(v) for v in redis_client.hvals(views_key))
        # Format dates
        if post.get("created_at"):
            try:
                dt = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
                post["created_at_formatted"] = dt.strftime("%d.%m.%Y")
            except:
                post["created_at_formatted"] = post.get("created_at", "")
        if post.get("published_at"):
            try:
                dt = datetime.fromisoformat(post["published_at"].replace("Z", "+00:00"))
                post["published_at_formatted"] = dt.strftime("%d.%m.%Y")
            except:
                post["published_at_formatted"] = post.get("published_at", "")

    return render_template("admin_blog.html", posts=sorted_posts)


@admin_bp.route("/admin/blog/new", methods=["GET", "POST"])
@login_required
def admin_blog_new():
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))

    if request.method == "POST":
        title = request.form.get("title")
        subtitle = request.form.get("subtitle")
        content = request.form.get("content")
        image = request.form.get("image")
        excerpt = request.form.get("excerpt")
        image_desc = request.form.get("image_desc")
        published = request.form.get("published") == "1"
        image_file = request.files.get("image_file")

        if not title or not content:
            if (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or request.is_json
            ):
                return jsonify(
                    {"success": False, "message": "Naslov in vsebina sta obvezna."}
                )
            flash("Naslov in vsebina sta obvezna.", "error")
            return redirect(request.url)

        # Handle image upload
        if image_file and image_file.filename:
            uploaded_image = save_blog_image(image_file)
            if uploaded_image:
                image = uploaded_image

        posts = load_blog_posts()
        # post_id made out of title and current timestamp to avoid collisions
        # convert title to a slug-like format by replacing spaces with underscores and removing special characters (ščćž and their uppercase variants)
        slug_title = (
            "".join(c if c.isalnum() else "_" for c in title.lower())
            .strip("_")
            .replace("š", "s")
            .replace("č", "c")
            .replace("ć", "c")
            .replace("ž", "z")
        )
        post_id = f"{slug_title}_{date.today().isoformat()}"
        now = datetime.now(timezone.utc).isoformat()
        posts[post_id] = {
            "id": post_id,
            "title": title,
            "subtitle": subtitle,
            "content": content,
            "image": image,
            "image_desc": image_desc,
            "excerpt": excerpt,
            "published": published,
            "created_at": now,
            "published_at": now if published else None,
        }
        save_blog_posts(posts)

        # Vrni JSON če je AJAX zahtevek, drugače redirect
        if (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.is_json
        ):
            return jsonify(
                {
                    "success": True,
                    "message": "Blog objava ustvarjena.",
                    "post_id": post_id,
                }
            )

        flash("Blog objava ustvarjena.", "success")
        return redirect(url_for("admin.admin_blog"))
    return render_template("admin_blog_edit.html", post=None)


@admin_bp.route("/admin/blog/edit/<post_id>", methods=["GET", "POST"])
@login_required
def admin_blog_edit(post_id):
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))

    posts = load_blog_posts()
    post = posts.get(post_id)
    if not post:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title")
        subtitle = request.form.get("subtitle")
        content = request.form.get("content")
        excerpt = request.form.get("excerpt")
        image_desc = request.form.get("image_desc")
        published = request.form.get("published") == "1"
        image_file = request.files.get("image_file")
        remove_image = request.form.get("remove_image") == "1"

        if not title or not content:
            if (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or request.is_json
            ):
                return jsonify(
                    {"success": False, "message": "Naslov in vsebina sta obvezna."}
                )
            flash("Naslov in vsebina sta obvezna.", "error")
            return redirect(request.url)

        # Start with current image
        image = post.get("image")

        # Handle image removal and upload
        if remove_image:
            image = None
        elif image_file and image_file.filename:
            uploaded_image = save_blog_image(image_file)
            if uploaded_image:
                image = uploaded_image

        # Update published_at if just published
        published_at = post.get("published_at")
        if published and not published_at:
            published_at = datetime.now(timezone.utc).isoformat()
        elif not published:
            published_at = None

        posts[post_id] = {
            "id": post_id,
            "title": title,
            "subtitle": subtitle,
            "content": content,
            "image": image,
            "image_desc": image_desc,
            "excerpt": excerpt,
            "published": published,
            "created_at": post.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
            "published_at": published_at,
        }
        save_blog_posts(posts)

        # Vrni JSON če je AJAX zahtevek, drugače redirect
        if (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.is_json
        ):
            return jsonify({"success": True, "message": "Blog objava posodobljena."})

        flash("Blog objava posodobljena.", "success")
        return redirect(url_for("admin.admin_blog"))

    # Format dates for display
    if post:
        if post.get("created_at"):
            try:
                dt = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
                post["created_at_display"] = dt.strftime("%d.%m.%Y %H:%M")
            except:
                post["created_at_display"] = post.get("created_at", "")
        if post.get("published_at"):
            try:
                dt = datetime.fromisoformat(post["published_at"].replace("Z", "+00:00"))
                post["published_at_display"] = dt.strftime("%d.%m.%Y %H:%M")
            except:
                post["published_at_display"] = post.get("published_at", "")

    return render_template("admin_blog_edit.html", post=post)


@admin_bp.route("/admin/blog/delete/<post_id>", methods=["POST"])
@login_required
def admin_blog_delete(post_id):
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))

    posts = load_blog_posts()
    if post_id in posts:
        del posts[post_id]
        save_blog_posts(posts)
        # Delete view stats
        redis_client.delete(f"blog:views:{post_id}")
        flash("Blog objava izbrisana.", "success")
    return redirect(url_for("admin.admin_blog"))
