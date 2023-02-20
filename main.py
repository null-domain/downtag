import os
import typing
import time
import music_tag
import pathlib
import re

import mutagen.oggopus
import requests
from tqdm import tqdm


path: pathlib.Path = pathlib.Path(__file__).parent.absolute()

FILE_NAME_REGEX = re.compile(
    r"^(?P<artist>.+?)\s+-\s+(?P<title>.+?)(?:\s+\((?P<remix>.+?)\s*(?:Remix|\(.*?Remix.*?\))\)|\s+\((?:feat\.?|ft\.?|w/|w⧸)\s*(?P<featured>.+?)\)|\s+(?:&|and)\s+([^(&|and)]+))?$"  # noqa: E501
)

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_URL_TRACK_INFO = (
    "https://ws.audioscrobbler.com/2.0/"
    "?method=track.getInfo"
    "&api_key={api_key}"
    "&artist={artist}"
    "&track={track}"
    "&format=json"
)
HEADERS = {"User-Agent": "downtag"}

tracks = []

tag_comment = "Tagged for null:radio"


def oxfordize(artists: typing.Sequence[str]):
    return ", ".join(artists[:-2] + [", and ".join(artists[-2:])])


audio_files = [f for f in path.iterdir() if f.is_file() and f.suffix == ".opus"]

for audio_file in tqdm(audio_files):
    tagged_file = music_tag.load_file(audio_file)

    if tagged_file["comment"].value == tag_comment:
        continue

    # get capture groups from file name
    match = FILE_NAME_REGEX.match(audio_file.stem)
    if match:
        artist = match.group("artist").split(" & ")
        title = match.group("title")
        remix = match.group("remix")
        featured = match.group("featured")
    else:
        print(f"Could not parse file name: {audio_file.name}")
        continue

    if remix:
        artist.append(remix)

    if featured:
        artist.append(featured)

        # get track cover art from last.fm
    if isinstance(artist, list):
        get_artist = artist[0]
    else:
        get_artist = artist
    response = requests.get(
        LASTFM_API_URL_TRACK_INFO.format(
            api_key=LASTFM_API_KEY, artist=get_artist, track=title
        ),
        headers=HEADERS,
    )

    if response.status_code != 200:
        tqdm.write(f"Could not get track info from last.fm: {audio_file.name}")
        continue

    album_art = None
    try:
        album_art = (
            response.json()
            .get("track")
            .get("album", {})
            .get("image", [])[2]
            .get("#text", None)
            or None
        )
    except IndexError:
        tqdm.write(f"last.fm has no track art for: {audio_file.name}")
    except AttributeError:
        tqdm.write(f"last.fm does not have any information for: {audio_file.name}")

    tracks.append({"title": title, "artist": artist, "album_art": album_art})

    for tag in [
        "album",
        "albumartist",
        "artist",
        "artwork",
        "comment",
        "compilation",
        "composer",
        "discnumber",
        "genre",
        "lyrics",
        "totaldiscs",
        "totaltracks",
        "tracknumber",
        "tracktitle",
        "year",
        "isrc",
    ]:
        tagged_file.remove_tag(tag)

    tagged_file["title"] = title
    tagged_file["artist"] = ", ".join(artist)
    tagged_file["comment"] = tag_comment

    if album_art:
        album_art = requests.get(album_art, stream=True)
        if album_art.status_code == 200:
            aa_bytes = b""
            for chunk in album_art.iter_content(1024):
                aa_bytes += chunk

            tagged_file["artwork"] = aa_bytes

    try:
        tagged_file.save()
        tqdm.write(f"Tagged '{title}' by {oxfordize(artist)}")
    except mutagen.oggopus.OggOpusHeaderError:
        tqdm.write(f"Could not tag file: {audio_file.name}")

    time.sleep(.25)
