# secret-fills

Designed for script writers to be able to search YouTube with the hopes of finding fills of their scripts they were not
informed about.

## Installation

**Prerequisites:**

- Python>=3.9
- YouTube Data API v3 credentials, as `./credentials.json`.  
  See [Step 1](https://developers.google.com/youtube/v3/quickstart/python#step_1_set_up_your_project_and_credentials) in
  Google's quickstart guide.

The following packages are also required:

```bash
python3 -m pip install termcolor colorama loguru thefuzz tabulate[widechars] google-api-python-client google-auth-httplib2 google-auth-oauthlib argvns
```

## Usage

`secret_fills.py` is a terminal application. The following options are supported:

- `-n` / `--number NUMBER`: The number of search results to parse for each term. (Default: 25)
- `-s` / `--search-terms SEARCH_TERMS...`: custom terms to be searched.

  Example: `python3 secret-fills.py -s girlfriend "summer picnic"`
- `-f` / `--file FILE`: path to a file containing a list of dates and search terms to use. It should be a .csv file
  with "Date" and "Title" headers; dates should be in ISO format (YYYY-MM-DD). Any search results uploaded before these
  dates will be ignored.
- `-i` / `--ignore-uploaders CHANNEL_NAMES...`: a list of channel names to ignore in results.
- `-m` / `--min-similarity VALUE`: In the final results, this is the threshold for a result to be shown. Should be a
  value
  between 0 and 100. (Default: 0)

In addition, filtering out known video IDs can be done, using the following argument:

- `--playlist-id PLAYLIST_ID`: id of a playlist of known videos to exclude.

Thus, example usages might be:

```bash
# Search for a list of titles while ignoring any videos in the given playlist
python3 secret_fills.py -f queries.csv --playlist-id $PLAYLIST_ID

# Also include a search for the writer's username, but exclude their own videos as well
python3 secret_fills.py -s lilellia -i lilellia -f queries.csv
```