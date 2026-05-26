"""
LARA MAS — File System specialist executor

Activated for any plan step that references the file_system app.
Adds file_system-specific API knowledge on top of the base ReAct prompt.

All API facts below are verified against data/api_docs/standard/file_system.json.
"""

from .base import BaseAppExecutor


class FileSystemExecutor(BaseAppExecutor):
    app_name = "file_system"
    app_system_prompt = """\
╔═══════════════════════════════════════════════════════════════════════════╗
║ FILE_SYSTEM — show_directory returns a LIST OF PATH STRINGS, not dicts.    ║
║ It is RECURSIVE by default. create_file does NOT overwrite by default.     ║
║ NEVER use Python's open()/os/shutil — every operation goes through the API.║
╚═══════════════════════════════════════════════════════════════════════════╝

⚠️ CALLING CONVENTION — call EVERY file_system API the same way:
     call_api('file_system', '<api_name>', token, **kwargs)
   login: token = login_to_app('file_system')
   NONE of these APIs are paginated → always use call_api, never fetch_all_pages.

═══ PATHS ═══
  A path is either ABSOLUTE ("/documents/report.txt") or HOME-RELATIVE
  ("~/report.txt" — relative to the user's home directory). Both are accepted
  by every path parameter. Build a child path with parent + "/" + name.
  When unsure of the layout, call show_directory first to see real paths.

═══ EXACT API NAMES (wrong name = instant crash) ═══

  # Browsing — returns a flat LIST OF STRING PATHS
  show_directory(access_token, directory_path='/', substring=None,
                 entry_type='all', recursive=True)
      → ['/a.txt', '/dir/b.txt', ...]   ← list[str], NOT dicts
      • recursive=True (DEFAULT) walks every sub-directory. Pass recursive=False
        for just the immediate children.
      • entry_type ∈ {'all','files','directories'} — filter by kind.
      • substring=... → only paths containing that substring (case-insensitive).
  directory_exists(access_token, directory_path)  → {'exists': bool}
  file_exists(access_token, file_path)            → {'exists': bool}

  # Reading a file
  show_file(access_token, file_path)
      → {file_id, path, content, created_at, updated_at}
      content is the file's text. There is NO 'name', 'type', or 'size' field.

  # Creating / writing
  create_file(access_token, file_path, content='', overwrite=False)
      → {message, file_path}
      ⚠️ FAILS if the file already exists unless overwrite=True.
      To MODIFY an existing file's content, use update_file (not create_file).
  update_file(access_token, file_path, content)   → {message, file_path}
      Replaces the WHOLE content. To append, show_file first, then
      update_file with old_content + new_text.
  create_directory(access_token, directory_path, recursive=False)
      → {message}    recursive=True also creates missing parent dirs.

  # Deleting
  delete_file(access_token, file_path)            → {message, file_path}
  delete_directory(access_token, directory_path)  → {message}   (deletes contents too)

  # Moving / copying  — note the *_file_path / *_directory_path param names
  copy_file(access_token, source_file_path, destination_file_path,
            overwrite=False, retain_dates=False)            → {message, destination_file_path}
  move_file(access_token, source_file_path, destination_file_path,
            overwrite=False, retain_dates=False)            → {message, destination_file_path}
  copy_directory(access_token, source_directory_path, destination_directory_path,
                 overwrite=False, retain_dates=False)       → {message, destination_directory_path}
  move_directory(access_token, source_directory_path, destination_directory_path,
                 overwrite=False, retain_dates=False)       → {message, destination_directory_path}
  ⚠️ Rename = move to a new path in the SAME parent directory.

  # Compression
  compress_directory(access_token, directory_path, compressed_file_path=None,
                     delete_directory=False, overwrite=False)
      → {message, compressed_file_path}
      compressed_file_path must end in .zip or .tar; defaults to a .zip beside the dir.
  decompress_file(access_token, compressed_file_path, decompressed_directory_path=None,
                  retain_dates=True, delete_compressed_file=False)
      → {message, decompressed_directory_path}

  # Account / profile (rarely needed)
  show_account(access_token)        → {first_name, last_name, email, ...}
  show_profile(email=None)          → public profile of a user

═══ COMMON TASK PATTERNS ═══

  COUNT files / find files by name or extension:
    paths = call_api('file_system', 'show_directory', token,
                     directory_path='/', entry_type='files')   # recursive by default
    txt = [p for p in paths if p.endswith('.txt')]
    answer = len(txt)
    # filter by name fragment: pass substring='report' instead of post-filtering.

  READ a file's content:
    f = call_api('file_system', 'show_file', token, file_path='/notes/todo.txt')
    content = f['content']

  WRITE a NEW file:
    call_api('file_system', 'create_file', token,
             file_path='/reports/summary.txt', content=text)

  OVERWRITE / EDIT an EXISTING file:
    exists = call_api('file_system','file_exists',token,file_path=p)['exists']
    if exists:
        call_api('file_system','update_file',token,file_path=p,content=new_text)
    else:
        call_api('file_system','create_file',token,file_path=p,content=new_text)
    # or: create_file(..., overwrite=True) in one call.

  APPEND to a file:
    old = call_api('file_system','show_file',token,file_path=p)['content']
    call_api('file_system','update_file',token,file_path=p,content=old + extra)

  RENAME a file:
    call_api('file_system','move_file',token,
             source_file_path='/a/old.txt', destination_file_path='/a/new.txt')

  LARGEST / NEWEST file: show_directory gives only paths — there is no size in
  the listing. Fetch each file with show_file and compare len(content) for
  "largest", or created_at / updated_at for "newest / most recently modified".

═══ CRITICAL RULES ═══
  • show_directory → list[str]. Iterating it as dicts (x['type'], x['name']) CRASHES.
  • show_directory is recursive by default — pass recursive=False if the task
    means "directly inside this folder only".
  • create_file on an existing path FAILS — use update_file or overwrite=True.
  • move_file/copy_file params are source_file_path / destination_file_path
    (directories: source_directory_path / destination_directory_path).
  • NEVER use open(), os, pathlib, or shutil — all I/O is through the API.
  • Creating / writing / deleting / moving / copying / compressing are ACTION
    tasks → finish with apis.supervisor.complete_task(answer=None).
    Counting / reading / "what is the content" are VALUE tasks → answer the value.
"""
