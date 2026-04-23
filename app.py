"""Flask dashboard למעקב תגבורים."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd
from flask import Flask, jsonify, render_template, request
from flask_caching import Cache

import config
from data_loader import (
    COL_DATE,
    COL_END,
    COL_NOTES,
    COL_RATING,
    COL_START,
    COL_STUDENTS,
    COL_TOPIC,
    COL_TUTOR,
    get_unique_students,
    get_unique_tutors,
    load_data,
)
from topic_matcher import build_topic_map, group_similar_topics


app = Flask(__name__)
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": config.CACHE_TTL_SECONDS})


# ---------- Helpers ----------

def _get_df() -> pd.DataFrame:
    cached = cache.get("df")
    if cached is not None:
        return cached
    df = load_data()
    if not df.empty and COL_TOPIC in df.columns:
        topic_map = build_topic_map(
            df[COL_TOPIC].dropna().tolist(),
            threshold=config.TOPIC_SIMILARITY_THRESHOLD,
        )
        df["_topic_normalized"] = df[COL_TOPIC].map(lambda t: topic_map.get(t, t))
    elif not df.empty:
        df["_topic_normalized"] = ""
    cache.set("df", df)
    return df


def _row_to_dict(row: pd.Series) -> dict[str, Any]:
    """ממיר שורה ל-dict ידידותי ל-Jinja."""
    d: dict[str, Any] = {}
    for k, v in row.items():
        if str(k).startswith("_"):
            continue
        if pd.isna(v):
            d[str(k)] = ""
        elif isinstance(v, pd.Timestamp):
            d[str(k)] = v.strftime("%d/%m/%Y")
        elif isinstance(v, datetime):
            d[str(k)] = v.strftime("%d/%m/%Y")
        else:
            d[str(k)] = v
    return d


def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [_row_to_dict(row) for _, row in df.iterrows()]


# ---------- Routes ----------

@app.route("/")
def index():
    df = _get_df()
    if df.empty:
        return render_template("empty.html")

    total_lessons = len(df)
    total_hours = float(df["משך (שעות)"].sum()) if "משך (שעות)" in df.columns else 0.0
    active_tutors = df[COL_TUTOR].nunique() if COL_TUTOR in df.columns else 0
    unique_students = len(get_unique_students(df))
    avg_rating = (
        float(df[COL_RATING].dropna().mean())
        if COL_RATING in df.columns and df[COL_RATING].notna().any()
        else None
    )

    # שיעורים לפי חודש
    monthly_labels: list[str] = []
    monthly_counts: list[int] = []
    if COL_DATE in df.columns and df[COL_DATE].notna().any():
        monthly = (
            df.dropna(subset=[COL_DATE])
            .assign(month=lambda d: d[COL_DATE].dt.to_period("M").astype(str))
            .groupby("month")
            .size()
            .sort_index()
        )
        monthly_labels = monthly.index.tolist()
        monthly_counts = [int(v) for v in monthly.values]

    # נושאים מובילים
    top_topics = df["_topic_normalized"].value_counts().head(8)
    top_topics_labels = top_topics.index.tolist()
    top_topics_counts = [int(v) for v in top_topics.values]

    # מתגברים מובילים
    if COL_TUTOR in df.columns:
        top_tutors = df[COL_TUTOR].value_counts()
        top_tutors_labels = top_tutors.index.tolist()
        top_tutors_counts = [int(v) for v in top_tutors.values]
    else:
        top_tutors_labels, top_tutors_counts = [], []

    # בונה רשימת מתגברים עם שעות + דירוג
    tutors_list: list[dict[str, Any]] = []
    if COL_TUTOR in df.columns:
        for tutor_name in top_tutors_labels:
            tutor_rows = df[df[COL_TUTOR] == tutor_name]
            hours = (
                float(tutor_rows["משך (שעות)"].sum())
                if "משך (שעות)" in tutor_rows.columns
                else 0.0
            )
            rating = (
                float(tutor_rows[COL_RATING].dropna().mean())
                if COL_RATING in tutor_rows.columns and tutor_rows[COL_RATING].notna().any()
                else None
            )
            tutors_list.append({
                "name": tutor_name,
                "lessons": int(len(tutor_rows)),
                "hours": round(hours, 1),
                "rating": round(rating, 2) if rating is not None else None,
            })

    recent = _df_to_records(df.head(8))

    return render_template(
        "index.html",
        total_lessons=total_lessons,
        total_hours=round(total_hours, 1),
        active_tutors=active_tutors,
        unique_students=unique_students,
        avg_rating=round(avg_rating, 2) if avg_rating is not None else None,
        monthly_labels=json.dumps(monthly_labels, ensure_ascii=False),
        monthly_counts=json.dumps(monthly_counts),
        top_topics_labels=json.dumps(top_topics_labels, ensure_ascii=False),
        top_topics_counts=json.dumps(top_topics_counts),
        tutors_list=tutors_list,
        recent_lessons=recent,
    )


@app.route("/tutors")
def tutors_page():
    df = _get_df()
    all_tutors = get_unique_tutors(df)
    selected = request.args.get("name") or (all_tutors[0] if all_tutors else "")
    tutor_df = df[df[COL_TUTOR] == selected].copy() if COL_TUTOR in df.columns and selected else pd.DataFrame()

    stats = {
        "lessons": len(tutor_df),
        "hours": round(float(tutor_df["משך (שעות)"].sum()), 1)
        if "משך (שעות)" in tutor_df.columns and not tutor_df.empty
        else 0.0,
        "avg_duration": round(float(tutor_df["משך (שעות)"].mean()), 2)
        if "משך (שעות)" in tutor_df.columns and not tutor_df.empty
        else 0.0,
        "avg_rating": round(float(tutor_df[COL_RATING].dropna().mean()), 2)
        if COL_RATING in tutor_df.columns and tutor_df[COL_RATING].notna().any()
        else None,
        "students_count": len({s for lst in tutor_df.get("_students_list", []) for s in lst}) if not tutor_df.empty else 0,
    }

    weekly_labels: list[str] = []
    weekly_hours: list[float] = []
    if not tutor_df.empty and COL_DATE in tutor_df.columns and "משך (שעות)" in tutor_df.columns:
        weekly = (
            tutor_df.dropna(subset=[COL_DATE])
            .assign(week=lambda d: d[COL_DATE].dt.to_period("W").astype(str))
            .groupby("week")["משך (שעות)"]
            .sum()
            .sort_index()
        )
        weekly_labels = weekly.index.tolist()
        weekly_hours = [round(float(v), 2) for v in weekly.values]

    if not tutor_df.empty and "_topic_normalized" in tutor_df.columns:
        topic_counts = tutor_df["_topic_normalized"].value_counts()
        topic_labels = topic_counts.index.tolist()
        topic_values = [int(v) for v in topic_counts.values]
    else:
        topic_labels, topic_values = [], []

    return render_template(
        "tutors.html",
        tutors=all_tutors,
        selected=selected,
        stats=stats,
        weekly_labels=json.dumps(weekly_labels, ensure_ascii=False),
        weekly_hours=json.dumps(weekly_hours),
        topic_labels=json.dumps(topic_labels, ensure_ascii=False),
        topic_values=json.dumps(topic_values),
        lessons=_df_to_records(tutor_df),
    )


@app.route("/topics")
def topics_page():
    df = _get_df()
    threshold = int(request.args.get("threshold", config.TOPIC_SIMILARITY_THRESHOLD))
    topics_list = df[COL_TOPIC].dropna().tolist() if COL_TOPIC in df.columns else []
    groups = group_similar_topics(topics_list, threshold=threshold)

    topic_map = {v: rep for rep, variants in groups.items() for v in variants}
    rows = []
    for rep, variants in groups.items():
        if COL_TOPIC in df.columns:
            mask = df[COL_TOPIC].map(lambda t: topic_map.get(t, t)) == rep
            count = int(mask.sum())
            tutors_list = df.loc[mask, COL_TUTOR].dropna().unique().tolist() if COL_TUTOR in df.columns else []
        else:
            count, tutors_list = 0, []
        rows.append({
            "topic": rep,
            "variants": [v for v in variants if v != rep],
            "lessons": count,
            "tutors": tutors_list,
        })
    rows.sort(key=lambda r: r["lessons"], reverse=True)

    chart_labels = [r["topic"] for r in rows[:15]]
    chart_values = [r["lessons"] for r in rows[:15]]

    return render_template(
        "topics.html",
        threshold=threshold,
        groups=rows,
        total_groups=len(rows),
        chart_labels=json.dumps(chart_labels, ensure_ascii=False),
        chart_values=json.dumps(chart_values),
    )


@app.route("/students")
def students_page():
    df = _get_df()
    students = get_unique_students(df)
    selected = request.args.get("name") or (students[0] if students else "")

    if selected and "_students_list" in df.columns:
        mask = df["_students_list"].apply(lambda lst: selected in lst)
        student_df = df[mask].copy()
    else:
        student_df = pd.DataFrame()

    stats = {
        "lessons": len(student_df),
        "hours": round(float(student_df["משך (שעות)"].sum()), 1)
        if "משך (שעות)" in student_df.columns and not student_df.empty
        else 0.0,
        "tutors_count": student_df[COL_TUTOR].nunique() if COL_TUTOR in student_df.columns and not student_df.empty else 0,
    }

    return render_template(
        "students.html",
        students=students,
        selected=selected,
        stats=stats,
        lessons=_df_to_records(student_df),
    )


@app.route("/refresh")
def refresh():
    cache.clear()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    import os
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(debug=debug, port=int(os.environ.get("PORT", 5003)))
