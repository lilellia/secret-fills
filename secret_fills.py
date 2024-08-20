from __future__ import annotations

import csv
from bisect import bisect
from collections.abc import Container
from datetime import datetime
from pathlib import Path
from typing import Iterator, NamedTuple

import colorama
from argvns import argvns, Arg
from tabulate import tabulate
from termcolor import colored
from thefuzz import fuzz

from yt import YouTubeClient, VideoData, alert_if_exceeded_quota

# Windows compatibility
colorama.init()


class SearchResult(NamedTuple):
    video: VideoData
    query: str
    similarity: int


def get_ids_from_playlist(client: YouTubeClient, *, playlist_id: str) -> set[str]:
    """Get a set of video IDs from the given playlist."""
    with alert_if_exceeded_quota():
        return set(video.id for video in client.videos_in_playlist(playlist_id))


def search(client: YouTubeClient, search_string: str, number: int, *, ignore_uploaders: Container[str],
           ignore_ids: Container[str], ignore_before: datetime | None) -> Iterator[SearchResult]:
    """Perform a search for the given string, and return the given number of results."""
    with alert_if_exceeded_quota():
        for result in client.search(query=search_string, max_results=number, after=ignore_before):
            if result.channel in ignore_uploaders:
                continue

            if result.id in ignore_ids:
                continue

            similarity = max(
                fuzz.partial_ratio(result.title, search_string),
                fuzz.partial_ratio(result.description, search_string),
            )

            yield SearchResult(video=result, query=search_string, similarity=similarity)


def get_all_results(*query_date_pairs: tuple[str, datetime | None], max_results: int, playlist_id: str | None = None,
                    known_ids: set[str] | None = None, ignored_channels: set[str] | None = None) -> list[SearchResult]:
    client = YouTubeClient()

    # handle known IDs for filtering
    if not known_ids:
        known_ids = set()

    if playlist_id:
        known_ids |= get_ids_from_playlist(client, playlist_id=playlist_id)

    results: dict[str, SearchResult] = {}

    def _should_add(r: SearchResult) -> bool:
        if r.video.id not in results:
            # first time we've seen this video
            return True

        if r.similarity > results[r.video.id].similarity:
            # we've found the video with a higher similarity score, so we'll replace it with that one
            return True

        return False

    for query, dt in query_date_pairs:
        for result in search(client, query, max_results, ignore_uploaders=ignored_channels, ignore_ids=known_ids,
                             ignore_before=dt):
            if _should_add(result):
                results[result.video.id] = result

    return list(results.values())


@argvns
class Config:
    max_results: int = Arg(short="-n", long="--max-results", type=int, default=25,
                           help="the number of results to return (default: 25)")
    search_terms: list[str] = Arg(short="-s", long="--search-terms", nargs="+", help="additional strings to search")
    queries_filepath: Path | None = Arg(short="-f", long="--queries-filepath", type=Path,
                                        help="path to file with search terms and dates to search for")
    ignored_channels: list[str] = Arg(short="-i", long="--ignored-channels", nargs="+", default=[],
                                      help="channels to ignore uploads for")
    min_similarity: int = Arg(short="-m", long="--min-similarity", type=int, default=0,
                              help="the minimum similarity for a result to be printed")
    playlist_id: str | None = Arg(long="--playlist-id", help="the id of a playlist whose videos will be ignored")
    table_format: str = Arg(long="--table-format", default="rounded-grid",
                            help="the display style for the results table; see https://pypi.org/project/tabulate for options")


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

    show_results(results=results, min_similarity=config.min_similarity, reverse_sort=True,
                 table_format=config.table_format)


def colour_similarity(similarity: int, thresholds: tuple[int, int] = (50, 80)) -> str:
    i = bisect(thresholds, similarity)
    colour = ["red", "yellow", "green"][i]

    return colored(format(similarity, "03d"), colour)  # type: ignore


def show_results(min_similarity: float, results: list[SearchResult], reverse_sort: bool, table_format: str):
    results = sorted(results, key=lambda r: r.similarity, reverse=reverse_sort)

    rows: list[list[str]] = []

    for result in results:
        if result.similarity < min_similarity:
            continue

        rows.append([
            colour_similarity(result.similarity),
            result.video.uploaded.strftime("%Y-%m-%d"),
            result.video.title,
            result.video.channel,
            result.video.url
        ])

    headers = ["sim", "published", "title", "channel", "url"]
    table = tabulate(rows, headers=headers, tablefmt=table_format)
    print(table)


if __name__ == "__main__":
    main()
