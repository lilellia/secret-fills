from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


@dataclass
class VideoData:
    title: str
    channel: str
    id: str
    uploaded: datetime
    thumbnail: str | None = None

    @property
    def url(self) -> str:
        return f"https://youtu.be/{self.id}"

    @classmethod
    def from_json(cls, data: dict[str, Any]):
        title = data["snippet"]["title"]
        channel = data["snippet"]["channelTitle"]
        try:
            video_id = data["snippet"]["resourceId"]["videoId"]
        except KeyError:
            video_id = data["id"]["videoId"]
        uploaded = datetime.strptime(data["snippet"]["publishedAt"], "%Y-%m-%dT%H:%M:%S%z")
        thumbnail = data["snippet"]["thumbnails"].get("high", {}).get("high", None)

        return cls(title=title, channel=channel, id=video_id, uploaded=uploaded, thumbnail=thumbnail)


class YouTubeClient:
    def __init__(self):
        credentials = self._get_credentials(scopes=SCOPES)
        self._service = build("youtube", "v3", credentials=credentials)

    def search(self, query: str, *, max_results: int = 25, after: date | None = None) -> Iterator[VideoData]:
        kwargs = {"part": "snippet", "q": query, "maxResults": max_results}
        if after:
            kwargs["publishedAfter"] = after.strftime("%Y-%m-%dT%H:%M:%SZ")

        request = self._service.search().list(**kwargs)
        results = request.execute()

        for obj in results["items"]:
            if obj["id"]["kind"] == "youtube#video":
                yield VideoData.from_json(data=obj)

    def videos_in_playlist(self, playlist_id: str) -> Iterator[VideoData]:
        """Return an iterator over the videos in the given playlist."""

        kwargs = {"part": "snippet", "playlistId": playlist_id, "maxResults": 50}
        next_page_token: str | None = None

        while True:
            if next_page_token:
                kwargs["pageToken"] = next_page_token

            request = self._service.playlistItems().list(**kwargs)
            results = request.execute()

            for obj in results["items"]:
                yield VideoData.from_json(data=obj)

            if not (next_page_token := results.get("nextPageToken")):
                return

    @staticmethod
    def _get_credentials(scopes: list[str]) -> Credentials:
        """Read the credentials from file, or generate them if necessary."""
        creds = None

        # token.json stores the user's access & refresh tokens, and is created automatically
        # when the auth flow completes for the first time
        root = Path(__file__).parent.resolve()
        token_file = root / "token.json"
        credentials_file = root / "credentials.json"

        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), scopes)

        # if there are no valid credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), scopes)
                creds = flow.run_local_server(port=0)

            token_file.write_text(creds.to_json(), encoding="utf-8")

        return creds
