import re
import tkinter as tk
from argparse import Namespace
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Generic, TypeVar, Any, Callable, Iterable

import ttkbootstrap as ttkb
from ttkbootstrap.tableview import Tableview
from yaspin.core import Yaspin

import secret_fills

T = TypeVar("T")


class CEntry(ttkb.Entry, Generic[T]):
    def __init__(self, master: Any, text: str = "", *args: Any, converter: Callable[[str], T] = str,
                 validator: Callable[[T], bool] = lambda _: True, **kwargs: Any) -> None:
        self._var = tk.StringVar(master, text)
        super().__init__(master, *args, textvariable=self._var, **kwargs)

        self.converter = converter
        self.validator = validator

        self.hint_text = text
        self.initial_fg = self.cget("foreground")
        self.entered = False
        self.config(foreground="grey")
        self.bind("<FocusIn>", self.on_focus)
        self.bind("<FocusOut>", self.on_unfocus)

    @property
    def text(self) -> str:
        return self._var.get()

    @text.setter
    def text(self, text: str) -> None:
        self._var.set(text)

    @property
    def value(self) -> T:
        return self.converter(self.text)

    def validate(self) -> bool:
        """Determine whether the input value is "valid", according to the entry's validator function."""
        try:
            return self.validator(self.value)
        except (ValueError, TypeError):
            return False

    def on_focus(self, _: tk.Event):
        self.config(foreground=self.initial_fg)
        if not self.entered:
            # this is the first time the user has focused this textbox,
            # so the hint text is what should still be in there
            self.entered = True
            self.text = ""

    def on_unfocus(self, _: tk.Event):
        if not self.text:
            # user has left this textbox empty, so return to starting state
            self.text = self.hint_text
            self.entered = False
            self.config(foreground="grey")

        if not self.validate():
            # resulting value is invalid
            self.config(foreground="red")


class CDropdown(ttkb.OptionMenu, Generic[T]):
    def __init__(self, master: Any, options: Iterable[T], mapfunc: Callable[[str], T] = str, **kwargs: Any):
        self._var = ttkb.StringVar(master)
        self.options = tuple(str(x) for x in options)
        self.mapfunc = mapfunc
        super().__init__(master, self._var, self.options[0], *self.options, **kwargs)

    @property
    def value(self) -> T:
        return self.mapfunc(self._var.get())

    @value.setter
    def value(self, val: T) -> None:
        self._var.set(str(val))


class App(ttkb.Window):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        grid_kw = dict(sticky="nsew", padx=10, pady=5)

        # --number ...
        ttkb.Label(self, text="Number of search results", justify="right").grid(row=0, column=0, **grid_kw)
        self.search_results_number_entry: CEntry[int] = CEntry(self, width=80, text="20", converter=int)
        self.search_results_number_entry.grid(row=0, column=1, columnspan=2, **grid_kw)

        # --search-terms ...
        ttkb.Label(self, text="Search Terms (ex: term1, term2)", justify="right").grid(row=1, column=0, **grid_kw)
        self.search_terms_entry = CEntry(self, width=80)
        self.search_terms_entry.grid(row=1, column=1, columnspan=2, **grid_kw)

        # --file ...
        ttkb.Label(self, text="Search Term File", justify="right").grid(row=2, column=0, **grid_kw)
        self.search_term_file_entry: CEntry[Path] = CEntry(self, width=80, converter=Path)
        self.search_term_file_entry.grid(row=2, column=1, columnspan=2, **grid_kw)

        # --ignore-uploaders ...
        ttkb.Label(self, text="Channel Names to Ignore", justify="right").grid(row=3, column=0, **grid_kw)
        self.ignore_uploaders_entry = CEntry(self, width=80)
        self.ignore_uploaders_entry.grid(row=3, column=1, columnspan=2, **grid_kw)

        # --playlist-url / --known-ids
        ttkb.Label(self, text="Source of Video IDs to Ignore", justify="right").grid(row=4, column=0, **grid_kw)
        self.known_ids_entry = CEntry(self, width=80, text="known_ids.pkl")
        self.known_ids_entry.grid(row=4, column=1, **grid_kw)
        self.known_ids_source_type_selector = CDropdown(self, options=("File", "Playlist URL"))
        self.known_ids_source_type_selector.grid(row=4, column=2, **grid_kw)

        # Run button
        self.run_button = ttkb.Button(self, text="Run", command=self.run)
        self.run_button.grid(row=5, column=0, columnspan=3, **grid_kw)

        # Results table
        columns = ["Date", "Similarity", "Title", "Uploader", "URL"]
        self.results_table = Tableview(self, coldata=columns, paginated=True, searchable=True)
        self.results_table.grid(row=6, column=0, columnspan=3, **grid_kw)

    def consume_results(self, results: Queue, sp: Yaspin, quiet: bool = False):
        while True:
            result: secret_fills.SearchResult = results.get()
            row = result.display.split(" | ")
            row[2] = " | ".join(row[2:-2])
            row[3] = row[-2]
            row[4] = row[-1]
            self.results_table.insert_row("end", row)
            results.task_done()

    def run(self) -> None:
        number = self.search_results_number_entry.value

        # handle search terms as comma-separated values
        search_terms = [s for s in re.split(r",\s*", self.search_terms_entry.value) if s]

        if self.search_term_file_entry.text:
            file = self.search_term_file_entry.value
        else:
            file = None

        # handle ignored uploaders as comma-separated values
        ignore_uploaders = [s for s in re.split(r",\s*", self.ignore_uploaders_entry.value) if s]

        # handle known IDs
        known_ids = self.known_ids_entry.value
        known_ids_type = self.known_ids_source_type_selector.value

        playlist_url, known_ids_file = None, None
        if known_ids and known_ids_type == "Playlist URL":
            playlist_url = known_ids
        if known_ids and known_ids_type == "File":
            known_ids_file = known_ids

        args = Namespace(number=number, search_terms=search_terms, file=file, ignore_uploaders=ignore_uploaders,
                         playlist_url=playlist_url, known_ids=known_ids_file, quiet=False, min_similarity=0)

        thread = Thread(target=secret_fills.run, kwargs=dict(args=args, consumer=self.consume_results))
        thread.start()

        thread.join()
        self.results_table.load_table_data()

        sort_ascending = 0
        sort_descending = 1
        self.results_table.sort_column_data(cid=1, sort=sort_descending)  # sort=1 => descending
        self.update()


def main():
    app = App("secret-fills", themename="darkly")
    app.mainloop()


if __name__ == "__main__":
    main()
