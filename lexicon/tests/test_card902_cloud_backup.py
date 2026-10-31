"""雲端備份 (card #902, 問題回報 #1173): one backup per account, replaced atomically, gone with the account."""

import pytest

from app import accounts, config

BACKUP = b"ENGLISH-CARD-BACKUP 1\n{}\n"


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    return tmp_path


def test_backup_roundtrip_and_replace(session, media):
    user, _ = accounts.register_email(session, "b@x.com", "password1", "Bo", "zh-TW", "B1")
    assert accounts.backup_info(user) == {"exists": False, "size": 0, "updated_at": None}
    with pytest.raises(accounts.AccountError) as e:
        accounts.load_backup(user)
    assert e.value.status == 404
    info = accounts.save_backup(user, BACKUP)
    assert info["exists"] and info["size"] == len(BACKUP)
    accounts.save_backup(user, BACKUP + b"more")
    assert accounts.load_backup(user) == BACKUP + b"more"
    assert not list((media / "user_backups").glob("*.tmp"))


def test_backup_rejects_other_files_and_is_per_user(session, media):
    a, _ = accounts.register_email(session, "a@x.com", "password1", "A", "zh-TW", "B1")
    b, _ = accounts.register_email(session, "b@x.com", "password1", "B", "zh-TW", "B1")
    with pytest.raises(accounts.AccountError) as e:
        accounts.save_backup(a, b"not a backup")
    assert e.value.status == 422
    accounts.save_backup(a, BACKUP)
    assert accounts.backup_info(b)["exists"] is False


def test_delete_account_removes_backup(session, media):
    user, _ = accounts.register_email(session, "c@x.com", "password1", "C", "zh-TW", "B1")
    accounts.save_backup(user, BACKUP)
    path = accounts._backup_path(user)
    assert path.exists()
    accounts.delete_account(session, user)
    assert not path.exists()
