import json
import logging
import os

import pandas as pd
from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

from movies_preparation.config import LOG_FILENAME
from utils import is_current_admin_view, redis_client

log = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__)

users = {}


def init_admin_bp(_users):
    """Initialize blueprint with app context"""
    global users
    users = _users


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
