import re
from collections.abc import Iterator
from csv import DictWriter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Self
from zipfile import ZipFile

from argvns import argvns, Arg


@dataclass
class ScriptData:
    title: str
    tags: list[str]
    is_public: bool
    format: str
    created: datetime
    updated: datetime | None
    summary: str

    @classmethod
    def from_scriptbin_export(cls, content: str) -> Self:
        lines = iter(content.split("\r\n"))

        title_and_tags = next(lines)
        title = re.sub(r"\s*\[.*?]\s*", "", title_and_tags)
        tags = re.findall(r"\[.*?]", title_and_tags)

        next(lines)  # divider line: ####
        next(lines)  # empty line

        publicity = next(lines)
        is_public = (publicity == "Publicly listed")

        # Format: Reddit-compatible Markdown
        fmt = next(lines).split(": ")[1]

        # Created: 1970-01-01 00:00:00 UTC
        created_dt_str = next(lines).split()[1]
        created_dt = datetime.strptime(created_dt_str, "%Y-%m-%d")

        # Updated: 1970-01-01 00:00:00 UTC
        updated = next(lines)
        if updated.startswith("Updated:"):
            updated_dt_str = updated.split()[1]
            updated_dt = datetime.strptime(updated_dt_str, "%Y-%m-%d")

            summary_line = next(lines)
        else:
            updated_dt = None
            summary_line = updated

        # Summary: ...
        summary = summary_line.split(": ")[1]

        return cls(title, tags, is_public, fmt, created_dt, updated_dt, summary)


def read_all_scriptbin_exports(z: ZipFile) -> Iterator[ScriptData]:
    for file in z.infolist():
        with z.open(file) as f:
            yield ScriptData.from_scriptbin_export(f.read().decode())


@argvns
class Config:
    infile: Path = Arg(short=("-i", "-z"), long="--infile", type=Path,
                       help="the zipfile containing the scriptbin export", required=True)
    export: Path = Arg(short=("-e", "-o"), long="--export", type=Path, help="the file to output the query file to",
                       required=True)


def main():
    config = Config()

    with ZipFile(config.infile) as z, open(config.export, "w", encoding="utf-8") as out:
        writer = DictWriter(out, fieldnames=["Date", "Title"])
        writer.writeheader()

        for s in read_all_scriptbin_exports(z):
            if not s.is_public:
                continue

            writer.writerow({"Date": (s.updated or s.created).strftime("%Y-%m-%d"), "Title": s.title})


if __name__ == "__main__":
    main()
