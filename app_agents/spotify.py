"""
LARA MAS — Spotify specialist executor

Activated for any plan step that references the spotify app.
Adds Spotify-specific API knowledge on top of the base ReAct prompt.
"""

from .base import BaseAppExecutor


class SpotifyExecutor(BaseAppExecutor):
    app_name = "spotify"
    app_system_prompt = """\
=== READY-TO-USE CODE TEMPLATES (use verbatim — do not explore APIs first) ===

TASK: "rate/give N-star rating to liked songs in my playlists"
→ PUT ALL OF THIS IN YOUR VERY FIRST CODE BLOCK. Do NOT split into multiple steps.
→ IGNORE the Explorer plan for this task type. Use exactly this code:

  token      = login_to_app('spotify')
  user_email = apis.supervisor.show_profile()['email']
  liked_ids  = set(s['song_id'] for s in fetch_all_pages('spotify', 'show_liked_songs', token))
  all_pl_ids = set()
  for pl in fetch_all_pages('spotify', 'show_playlist_library', token):
      all_pl_ids.update(pl['song_ids'])
  target_ids = liked_ids & all_pl_ids    # ← INTERSECTION: only songs that are BOTH liked AND in a playlist
  print(f"Liked: {liked_ids}, Playlist: {all_pl_ids}, Target: {target_ids}")
  for sid in target_ids:                 # ← loop over target_ids, NOT liked_ids
      reviews   = call_api('spotify', 'show_song_reviews', token, song_id=sid)
      my_review = next((r for r in reviews if r.get('user',{}).get('email')==user_email), None)
      if my_review:
          call_api('spotify', 'update_song_review', token, review_id=my_review['song_review_id'], rating=5)
      else:
          call_api('spotify', 'review_song', token, song_id=sid, rating=5)
  apis.supervisor.complete_task(answer=None)

TASK: "most-liked/most-played song across all playlists" → COPY THIS EXACTLY:
  token    = login_to_app('spotify')
  all_ids  = set()
  for pl in fetch_all_pages('spotify', 'show_playlist_library', token):
      all_ids.update(pl['song_ids'])
  songs = [call_api('spotify', 'show_song', token, song_id=sid) for sid in all_ids]
  top   = max(songs, key=lambda s: s.get('like_count', 0))   # or play_count
  apis.supervisor.complete_task(answer=top['title'])

=== KEY FACTS (only if deviating from templates above) ===

APIs (exact names):
  show_liked_songs(access_token)                → songs user liked (paginated — use fetch_all_pages)
  show_playlist_library(access_token)           → playlists (paginated — use fetch_all_pages)
  show_song(access_token, song_id)              → full song dict
  show_song_reviews(access_token, song_id)      → ALL users' reviews for this song
  review_song(access_token, song_id, rating)    → create a new review
  update_song_review(access_token, review_id, rating) → update existing review

Field names (verified):
  show_playlist_library: each playlist → 'song_ids': [int, ...]  NOT 'songs'
  show_liked_songs: each entry → 'song_id' (int)
  show_song_reviews: each review → 'song_review_id', 'rating', 'user' {'email': ...}
  review ID to pass to update_song_review = my_review['song_review_id']  (NOT 'id' or 'review_id')

CRITICAL RULES:
  'liked songs' = songs in show_liked_songs — there is NO 'liked' field on show_song.
  NEVER use like_count > 0 to check if a user liked a song — like_count is global popularity.
  show_song_reviews returns ALL users' reviews — always filter by user_email to find your own.
  Action tasks (rate, send, create): apis.supervisor.complete_task(answer=None) — NOT answer='done'.

PAGINATION:
  Use fetch_all_pages() for ALL listing APIs — they return only 5 per page by default.
  Use call_api() only for single-item lookups (show_song, show_playlist, show_song_reviews).

SONG RATING (if template above doesn't fit):
  user_email = apis.supervisor.show_profile()['email']
  for sid in target_ids:
      reviews   = call_api('spotify', 'show_song_reviews', token, song_id=sid)
      my_review = next((r for r in reviews if r.get('user',{}).get('email')==user_email), None)
      if my_review:
          call_api('spotify', 'update_song_review', token, review_id=my_review['song_review_id'], rating=N)
      else:
          call_api('spotify', 'review_song', token, song_id=sid, rating=N)
"""
