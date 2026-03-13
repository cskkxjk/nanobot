"""User authentication and workspace (experimental, txt-based)."""

from nanobot.auth.user import (
    allowed_users_path,
    validate_user,
    get_user_root,
    get_global_root,
    ensure_user_workspace,
)

__all__ = [
    "allowed_users_path",
    "validate_user",
    "get_user_root",
    "get_global_root",
    "ensure_user_workspace",
]
