"""User auth and per-user workspace (experimental; txt file, may switch to DB later)."""

from pathlib import Path

from nanobot.utils.helpers import ensure_dir, safe_filename, sync_workspace_templates


def allowed_users_path(override: str | Path | None = None) -> Path:
    """Path to allowed users file. override from config.auth.allowed_users_path, else ~/.nanobot/allowed_users.txt."""
    if override and str(override).strip():
        return Path(override).expanduser()
    return Path.home() / ".nanobot" / "allowed_users.txt"


def validate_user(user_id: str, password: str, path: Path) -> tuple[bool, bool]:
    """
    Check user_id and password against the allowed users file.
    Format per line: user_id:password or user_id:password:admin.
    Returns (ok, is_admin). Third segment 'admin' marks admin.
    """
    if not path.exists():
        return False, False
    user_id = (user_id or "").strip()
    password = (password or "").strip()
    if not user_id:
        return False, False
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False, False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":", 2)
        if len(parts) < 2:
            continue
        fid, fpass = parts[0].strip(), parts[1].strip()
        is_admin = len(parts) > 2 and parts[2].strip().lower() == "admin"
        if fid == user_id and fpass == password:
            return True, is_admin
    return False, False


def get_user_root(user_id: str) -> Path:
    """Return .nanobot/<user_id> for a given user. Raises ValueError if user_id is empty (would resolve to global root)."""
    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("user_id must be non-empty (empty would resolve to global ~/.nanobot)")
    return Path.home() / ".nanobot" / safe_filename(uid)


def get_global_root() -> Path:
    """Return ~/.nanobot for admin global mode."""
    return Path.home() / ".nanobot"


def ensure_user_workspace(user_id: str, silent: bool = False) -> Path:
    """
    Create user root and subdirs (cron, history, media, workspace) if missing.
    Syncs workspace templates into workspace/. Returns user_root.
    """
    root = get_user_root(user_id)
    for name in ("cron", "history", "media", "workspace"):
        ensure_dir(root / name)
    sync_workspace_templates(root / "workspace", silent=silent)
    return root
