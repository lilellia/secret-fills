# secret-fills

Designed for script writers to be able to search YouTube with the hopes of finding fills of their scripts they were not
informed about.

## Installation

This project requires Python 3. It was tested in Python 3.11, but any version >= 3.9 should work.

```bash
python3 -m pip install termcolor colorama loguru yaspin thefuzz
```

## Usage

This is a terminal application. The following options are supported:

- `-n` / `--number NUMBER`: The number of search results to parse for each term. (Default: 10)
- `-s` / `--search-terms SEARCH_TERMS...`: custom terms to be searched.

  Example: `python3 secret-fills.py -s girlfriend "summer picnic"`
- `-f` / `--file FILE`: path to a file containing a list of search terms to use. It is recommended that this be a list
  of script titles.
- `-i` / `--ignore-uploaders CHANNEL_NAMES...`: a list of channel names to ignore in results.
- `-q` / `--quiet`: Pass this flag to suppress output during the search.
- `-m` / `--min-similarity VALUE`: In the final results, this is the threshold for a result to be shown. Should be a
  value
  between 0 and 100. (Default: 0)

In addition, filtering out known video IDs can be done, using one of the two following arguments:

- `--playlist-url URL`: url to a playlist of known videos to exclude. These IDs are also cached to file, so that
  subsequent runs can use `--known-ids`.
- `--known-ids PATH`: path to a file (likely `known_ids.pkl`) containing the known IDs.

Thus, example usages might be:

```bash
# Search for a list of titles while ignoring any videos in the given playlist
python3 secret-fills.py -f titles.txt --playlist-url https://www.youtube.com/playlist?list=PLAYLIST_ID -q

# The same search, but using an IDs file
python3 secret-fills.py -f titles.txt --known-ids known_ids.pkl -q

# Also include a search for the writer's username, but exclude their own videos as well
python3 secret-fills.py -s lilellia -i lilellia -f titles.txt --known-ids known_ids.pkl -q
```