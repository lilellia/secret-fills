import json
import pickle
from argparse import ArgumentParser, Namespace
from collections.abc import Container
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from queue import Queue
from subprocess import Popen, PIPE
from threading import Thread
from typing import Any, TypeAlias, Iterator, NamedTuple, Literal, Callable

import colorama
from termcolor import colored
from thefuzz import fuzz
from yaspin import yaspin
from yaspin.core import Yaspin
from yaspin.spinners import Spinners

# Windows compatibility
colorama.init()

VideoData: TypeAlias = dict[str, Any]


class SearchResult(NamedTuple):
    colored_display: str
    display: str
    search_term: str
    similarity: int


def ytdlp_results(arg: str) -> Iterator[VideoData]:
    cmd = ("yt-dlp", "-j", arg)
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE)

    while line := proc.stdout.readline():
        yield json.loads(line)


@contextmanager
def spinner(text: str):
    with yaspin(Spinners.arc, text=text) as s:
        try:
            yield s
        finally:
            s.text = colored(text, "green")
            s.ok(colored("✓", "green"))


def get_known_ids(playlist_url: str) -> set[str]:
    """Get a set of video IDs from the given playlist."""
    known_ids: set[str] = set()

    with spinner("Getting known IDs from playlist..."):
        for result in ytdlp_results(arg=playlist_url):
            id_ = result["display_id"]
            known_ids.add(id_)

    return known_ids


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


def do_search(search_string: str, results: Queue, **kwargs):
    for result in search(search_string, **kwargs):
        results.put(result)


def search(search_string: str, number: int, *, ignore_uploaders: Container[str],
           ignore_ids: Container[str]) -> Iterator[SearchResult]:
    """Perform a search for the given string, and return the given number of results."""
    for result in ytdlp_results(arg=f"ytsearch{number}:{search_string}"):
        if result["uploader"] in ignore_uploaders:
            continue

        if result["display_id"] in ignore_ids:
            continue

        similarity = fuzz.partial_ratio(result["title"], search_string)
        colored_display, display = format_search_result(result, similarity)

        yield SearchResult(colored_display, display, search_term=search_string, similarity=similarity)


def print_results(results: Queue, sp: Yaspin, quiet: bool = False):
    with open("results.txt", "w", encoding="utf-8") as f:
        while True:
            result: SearchResult = results.get()

            if not quiet:
                sp.write(result.colored_display)
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
    run(args, consumer=print_results)
    show_results(args.min_similarity)


def run(args: Namespace, consumer: Callable[[Queue, Yaspin, bool], None]):
    # handle known IDs for filtering
    known_ids: set[str]
    if args.playlist_url:
        known_ids = get_known_ids(args.playlist_url)
        with open("known_ids.pkl", "wb") as f:
            pickle.dump(known_ids, f)
    elif args.known_ids:
        with spinner("Getting known IDs from file..."), open(args.known_ids, "rb") as f:
            known_ids = pickle.load(f)
    else:
        known_ids = set()

    # add titles to search strings as necessary
    if args.file:
        titles = args.file.read_text().splitlines()
        args.search_terms.extend(titles)

    # run in parallel
    results = Queue()

    kwargs = dict(number=args.number, ignore_uploaders=args.ignore_uploaders, ignore_ids=known_ids)
    workers = [
        Thread(target=do_search, args=(search_term, results), kwargs=kwargs, daemon=True)
        for search_term in args.search_terms
    ]

    with spinner("Searching videos...") as s:
        for worker in workers:
            worker.start()

        consumer = Thread(target=consumer, args=(results, s), kwargs=dict(quiet=args.quiet), daemon=True)
        consumer.start()

        for worker in workers:
            worker.join()

        results.join()


def show_results(min_similarity: int):
    with open("results.txt", "r", encoding="utf-8") as f:
        data = [line.rstrip().split(" | ") for line in f.readlines()]

    data.sort(key=lambda line: int(line[1]))
    for line in data:
        if int(line[1]) >= min_similarity:
            print(" | ".join(line))


if __name__ == "__main__":
    main()
