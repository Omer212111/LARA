"""
LARA MAS — Spotify specialist executor

Activated for any plan step that references the spotify app.
Adds Spotify-specific API knowledge on top of the base ReAct prompt.
"""

from .base import BaseAppExecutor


class SpotifyExecutor(BaseAppExecutor):
    app_name = "spotify"
    app_system_prompt = """\
=== SURFACE: spotify_specialist:prompt === BEGIN
=== KEY FACTS ===

APIs (exact names):
  show_liked_songs(access_token)                → songs the user has liked (paginated)
  show_liked_albums(access_token)               → albums the user has liked (paginated)
  show_song_library(access_token)               → the song library (paginated)
  show_album_library(access_token)              → the album library (paginated)
  show_playlist_library(access_token)           → the playlist library (paginated)
  show_song(song_id)                            → full song dict — takes NO access_token
  show_album(album_id)                          → full album dict — takes NO access_token
  show_playlist(access_token, playlist_id)      → one playlist
  show_song_reviews(song_id, user_email=None)   → reviews for a song — NO access_token, PAGINATED
  review_song(access_token, song_id, rating)    → create a new review
  update_song_review(access_token, review_id, rating) → update an existing review
  (call_api / fetch_all_pages always send access_token; the endpoints above that do
   not declare one ignore it, so reaching them through the helpers is still safe.)

Field names (verified):
  show_liked_songs, show_song_library: each entry → 'song_id' (int)
  show_playlist_library, show_album_library, show_liked_albums: each entry → 'song_ids': [int, ...]  NOT 'songs'
  show_playlist, show_album (single-item): 'songs': [{'id', 'title', 'artist_ids'}] — key is 'id', NOT 'song_id'
  show_song: 'title', 'play_count', 'like_count', 'rating', 'duration', 'release_date', 'genre', 'artists'
  show_song_reviews: each review → 'song_review_id', 'rating', 'user' {'email': ...}
  review ID to pass to update_song_review = my_review['song_review_id']  (NOT 'id' or 'review_id')

CRITICAL RULES:
  'liked' is set membership, not a field — a song is liked iff its id is in show_liked_songs.
  There is NO 'liked' field on show_song.
  NEVER use like_count > 0 to check if a user liked a song — like_count is global popularity.
  A task names which library it is scoped to (song / album / playlist / liked). Build ids from
  that library only; combine libraries only when the task says "across" them.
  "liked" vs "not liked" within a library is an intersection vs a difference of the two id sets —
  print both sets and the result before acting on them.
  show_song_reviews returns EVERY user's reviews — pass user_email=... to get only the user's own.
  Action tasks (rate, follow, play, create): apis.supervisor.complete_task(answer=None) — NOT answer='done'.

PAGINATION:
  Use fetch_all_pages() for ALL listing APIs — they return only 5 per page by default.
  show_song_reviews is one of them: a plain call_api() sees at most the first 5 reviews.
  Use call_api() only for true single-item lookups (show_song, show_album, show_playlist).

SUPERLATIVE QUESTIONS ("most/least played", "highest rated", "longest"):
  Collect the song ids of the library the task names, show_song each id, then min/max on the
  field the task names — play_count, like_count, rating, duration. Read the direction
  (most vs least, highest vs lowest) off the task; both occur.

RATING A SONG (create-or-update — a second review_song duplicates instead of overwriting):
  token      = login('spotify')
  user_email = apis.supervisor.show_profile()['email']
  for sid in target_ids:
      mine = fetch_all_pages('spotify', 'show_song_reviews', token, song_id=sid, user_email=user_email)
      if mine:
          call_api('spotify', 'update_song_review', token, review_id=mine[0]['song_review_id'], rating=N)
      else:
          call_api('spotify', 'review_song', token, song_id=sid, rating=N)
  N is the rating the task asks for; wording about raising or lowering an existing rating still
  means set it to N.
=== SURFACE: spotify_specialist:prompt === END
"""
