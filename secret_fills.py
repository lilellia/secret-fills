from __future__ import annotations

import csv
import json
import pickle
import subprocess
import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Container
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from subprocess import CREATE_NO_WINDOW, PIPE, Popen
from sys import platform
from threading import Thread
from typing import Any, Callable, Iterator, Literal, NamedTuple, TypeAlias, TypeVar

import colorama
from termcolor import colored
from thefuzz import fuzz

# Windows compatibility
colorama.init()

VideoData: TypeAlias = dict[str, Any]
T = TypeVar("T")

YT_DLP = ".\yt-dlp.exe" if platform == "win32" else "yt-dlp"

def check_ytdlp_install() -> bool:
    """Determine whether yt-dlp is installed. Return True if installed and on PATH; False, otherwise."""
    try:
        subprocess.run([YT_DLP, "--version"], capture_output=True)
        return True
    except FileNotFoundError:
        return False


class SearchResult(NamedTuple):
    colored_display: str
    display: str
    search_term: str
    similarity: int


def ytdlp_results(arg: str) -> Iterator[VideoData]:
    cmd = (YT_DLP, "-j", arg)
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE, creationflags=CREATE_NO_WINDOW)

    assert proc.stdout is not None
    while line := proc.stdout.readline():
        yield json.loads(line)


def get_ids_from_playlist(playlist_url: str) -> set[str]:
    """Get a set of video IDs from the given playlist."""
    cmd = ("yt-dlp", "--flat-playlist", "--print", "id", playlist_url)
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE, creationflags=CREATE_NO_WINDOW)

    assert proc.stdout is not None
    return set(line.decode().strip() for line in proc.stdout.readlines())


def format_search_result(raw: VideoData, similarity: int) -> tuple[str, str]:
    title = raw["title"]
    uploader = raw["uploader"]
    upload_date = datetime.strptime(raw["upload_date"], "%Y%m%d").strftime("%Y-%m-%d")
    url = raw["original_url"]

    sim_color: Literal["red", "yellow", "white"]
    if similarity >= 80:
        sim_color = "red"
    elif similarity >= 50:
        sim_color = "yellow"
    else:
        sim_color = "white"

    similarity_str = colored(format(similarity, "03"), sim_color)

    colored_display = f"""{colored(upload_date, "white")} | {similarity_str} | {colored(title, "green")} | {colored(uploader, "yellow")} | {url}"""
    display = f"""{upload_date} | {similarity} | {title} | {uploader} | {url}"""
    return colored_display, display


def do_search(search_string: str, ignore_before: datetime | None, results: Queue[SearchResult], store: Queue[SearchResult], number: int, ignore_uploaders: Container[str], ignore_ids: Container[str]):
    for result in search(search_string, number, ignore_uploaders=ignore_uploaders, ignore_ids=ignore_ids, ignore_before=ignore_before):
        results.put(result)
        store.put(result)


def search(search_string: str, number: int, *, ignore_uploaders: Container[str],
           ignore_ids: Container[str], ignore_before: datetime | None) -> Iterator[SearchResult]:
    """Perform a search for the given string, and return the given number of results."""
    for result in ytdlp_results(arg=f"ytsearch{number}:{search_string}"):
        if result["uploader"] in ignore_uploaders:
            continue

        if result["display_id"] in ignore_ids:
            continue

        uploaded = datetime.strptime(result["upload_date"], "%Y%m%d")
        if ignore_before is not None and uploaded < ignore_before:
            continue

        similarity = fuzz.partial_ratio(result["title"], search_string)
        colored_display, display = format_search_result(result, similarity)

        yield SearchResult(colored_display, display, search_term=search_string, similarity=similarity)


def print_results(results: Queue[SearchResult], quiet: bool = False):
    with open("results.txt", "w", encoding="utf-8") as f:
        while True:
            result: SearchResult = results.get()

            if not quiet:
                print(result.colored_display)
            f.write(f"{result.display}\n")
            results.task_done()


def parse_argv() -> Namespace:
    parser = ArgumentParser()
    parser.add_argument("-n", "--number", type=int, default=10, help="the number of results to return (default: 10)")
    parser.add_argument("-s", "--search-terms", nargs="+", help="the strings to search")
    parser.add_argument("-f", "--file", type=Path, help="path to file with search terms to search for")
    parser.add_argument("-i", "--ignore-uploaders", nargs="+",
                        help="channels to ignore uploads for (they will not appear in the results)")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("-m", "--min-similarity", type=int, default=0,
                        help="the minimum similarity for a result to be printed in final results")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--playlist-url", help="url of a playlist - ignore these videos")
    group.add_argument("--known-ids", type=Path, help="path to a file containing known ids - ignore these videos")

    return parser.parse_args()


def main():
    args = parse_argv()

    if not check_ytdlp_install():
        sys.exit("Requirement: yt-dlp is not installed.")

    results = run(args, consumer=print_results)
    show_results(results=results, min_similarity=args.min_similarity)


def queue_into_list(q: Queue[T], lst: list[T]) -> None:
    while True:
        try:
            element = q.get_nowait()
            lst.append(element)
        except Empty:
            return
    

def run(args: Namespace, consumer: Callable[[Queue[SearchResult], bool], None]) -> list[SearchResult]:
    # handle known IDs for filtering
    known_ids: set[str]
    if args.playlist_url:
        known_ids = get_ids_from_playlist(args.playlist_url)
        with open("known_ids.pkl", "wb") as f:
            pickle.dump(known_ids, f)
    elif args.known_ids:
        with open(args.known_ids, "rb") as f:
            known_ids = pickle.load(f)
    else:
        known_ids = set()

    # add titles to search strings as necessary
    search_terms: list[str] = []
    ignore_dates: list[datetime | None] = []

    if args.search_terms:
        for term in args.search_terms:
            search_terms.append(term)
            ignore_dates.append(None)

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = datetime.strptime(row["Date"], "%Y-%m-%d")
                search_terms.append(row["Title"])
                ignore_dates.append(date)

    # handle ignored uploaders
    ignored_channels: list[str] = []
    if args.ignore_uploaders:
        ignored_channels.extend(args.ignore_uploaders)

    # run in parallel
    results: Queue[SearchResult] = Queue()
    store: Queue[SearchResult] = Queue()

    kwargs = dict(number=args.number, ignore_uploaders=ignored_channels, ignore_ids=known_ids)
    workers = [
        Thread(target=do_search, args=(search_term, ignore_before, results, store), kwargs=kwargs, daemon=True)
        for search_term, ignore_before in zip(search_terms, ignore_dates)
    ]

    for worker in workers:
        worker.start()

    consumer = Thread(target=consumer, args=(results,), kwargs=dict(quiet=args.quiet), daemon=True)
    consumer.start()

    for worker in workers:
        worker.join()

    results.join()

    q: list[SearchResult] = []
    queue_into_list(store, q)
    return q


def parse_results_file(filepath: Path = Path("results.txt")) -> Iterator[SearchResult]:
    """Convert the results file back into a list of search results."""
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]

    # each line has the format
    # date | similiarity | title | uploader | url
    for line in lines:
        date, similarity, *title, uploader, url = line.split(" | ")


        title = " | ".join(title)
        similarity = int(similarity)

        colored_display = f"""{colored(date, "white")} | {similarity} | {colored(title, "green")} | {colored(uploader, "yellow")} | {url}"""
        display = f"""{date} | {similarity} | {title} | {uploader} | {url}"""
        search_term = ""  # we can't figure this out from here since it's not rendered
        
        yield SearchResult(colored_display, display, search_term, similarity)


def show_results(min_similarity: float, results: list[SearchResult] | None = None):
    if not results:
        results = list(parse_results_file())

    results = sorted(results, key=lambda r: r.similarity, reverse=False)
    for result in results:
        if result.similarity >= min_similarity:
            print(result.colored_display)
    

if __name__ == "__main__":
    main()
