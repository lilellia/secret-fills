from __future__ import annotations

import csv
from collections.abc import Container
from datetime import datetime
from pathlib import Path
from typing import Iterator, Literal, NamedTuple

import colorama
from argvns import argvns, Arg
from termcolor import colored
from thefuzz import fuzz

from yt import YouTubeClient, VideoData, alert_if_exceeded_quota

# Windows compatibility
colorama.init()


class SearchResult(NamedTuple):
    colored_display: str
    display: str
    search_term: str
    similarity: int


def get_ids_from_playlist(client: YouTubeClient, *, playlist_id: str) -> set[str]:
    """Get a set of video IDs from the given playlist."""
    with alert_if_exceeded_quota():
        return set(video.id for video in client.videos_in_playlist(playlist_id))


def format_search_result(video: VideoData, similarity: int) -> tuple[str, str]:
    sim_color: Literal["red", "yellow", "white"]
    if similarity >= 80:
        sim_color = "red"
    elif similarity >= 50:
        sim_color = "yellow"
    else:
        sim_color = "white"

    similarity_str = colored(format(similarity, "03"), sim_color)
    uploaded_str = video.uploaded.strftime("%d %b %Y")

    colored_display = f"""{colored(uploaded_str, "white")} | {similarity_str} | {colored(video.title, "green")} | {colored(video.channel, "yellow")} | {video.url}"""
    display = f"""{uploaded_str} | {similarity} | {video.title} | {video.channel} | {video.url}"""
    return colored_display, display


def search(client: YouTubeClient, search_string: str, number: int, *, ignore_uploaders: Container[str],
           ignore_ids: Container[str], ignore_before: datetime | None) -> Iterator[SearchResult]:
    """Perform a search for the given string, and return the given number of results."""
    with alert_if_exceeded_quota():
        for result in client.search(query=search_string, max_results=number, after=ignore_before):
            if result.channel in ignore_uploaders:
                continue

            if result.id in ignore_ids:
                continue

            similarity = fuzz.partial_ratio(result.title, search_string)
            colored_display, display = format_search_result(result, similarity)

            yield SearchResult(colored_display, display, search_term=search_string, similarity=similarity)


def get_all_results(*query_date_pairs: tuple[str, datetime | None], max_results: int, playlist_id: str | None = None,
                    known_ids: set[str] | None = None, ignored_channels: set[str] | None = None) -> list[SearchResult]:
    client = YouTubeClient()

    # handle known IDs for filtering
    if not known_ids:
        known_ids = set()

    if playlist_id:
        known_ids |= get_ids_from_playlist(client, playlist_id=playlist_id)

    results: list[SearchResult] = []
    for query, dt in query_date_pairs:
        found = search(client, query, max_results, ignore_uploaders=ignored_channels, ignore_ids=known_ids,
                       ignore_before=dt)
        results.extend(found)

    return results


@argvns
class Config:
    max_results: int = Arg(short="-n", long="--max-results", type=int, default=25,
                           help="the number of results to return (default: 25)")
    search_terms: list[str] = Arg(short="-s", long="--search-terms", nargs="+", help="additional strings to search")
    queries_filepath: Path | None = Arg(short="-f", long="--queries-filepath", type=Path,
                                        help="path to file with search terms and dates to search for")
    ignored_channels: list[str] = Arg(short="-i", long="--ignored-channels", nargs="+",
                                      help="channels to ignore uploads for")
    min_similarity: int = Arg(short="-m", long="--min-similarity", type=int, default=0,
                              help="the minimum similarity for a result to be printed")
    playlist_id: str | None = Arg(long="--playlist-id", help="the id of a playlist whose videos will be ignored")


def read_search_terms_file(filepath: Path) -> Iterator[tuple[str, datetime]]:
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = datetime.strptime(row["Date"], "%Y-%m-%d")
            query = row["Title"]

            yield query, dt


def main():
    config = Config()

    query_date_pairs: list[tuple[str, datetime | None]] = []

    if config.queries_filepath:
        query_date_pairs.extend(read_search_terms_file(config.queries_filepath))

    for query in config.search_terms:
        query_date_pairs.append((query, None))

    results = get_all_results(*query_date_pairs, playlist_id=config.playlist_id, known_ids=None,
                              ignored_channels=set(config.ignored_channels), max_results=config.max_results)

    show_results(results=results, min_similarity=config.min_similarity)


def show_results(min_similarity: float, results: list[SearchResult] | None = None):
    results = sorted(results, key=lambda r: r.similarity, reverse=False)
    for result in results:
        if result.similarity >= min_similarity:
            print(result.colored_display)


if __name__ == "__main__":
    main()
