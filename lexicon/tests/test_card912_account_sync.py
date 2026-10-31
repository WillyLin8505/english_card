"""跨裝置自動同步 (card #912): newest record wins, repeats count once, deletions reach every device."""

import pytest

from app import accounts, account_sync, config


class User:
    def __init__(self, id):
        self.id = id


@pytest.fixture
def user(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    return User(1)


def rec(key, stamp, data="x", deleted=False):
    return {"key": key, "stamp": stamp, "deleted": deleted, "data": None if deleted else data}


def keys(result):
    return [r["key"] for r in result["records"]]


def test_two_devices_merge_by_record_and_keep_both_reviews(user):
    account_sync.push(user, "a", [rec("en/entries/apple", 10, "from a"), rec("en/logs/apple|1|good", 10)])
    account_sync.push(user, "b", [rec("en/entries/apple", 20, "from b"), rec("en/logs/apple|2|hard", 20),
                                  rec("en/entries/pear", 5)])
    data = {r["key"]: r["data"] for r in account_sync.pull(user, 0)["records"]}
    assert data["en/entries/apple"] == "from b"
    assert {"en/logs/apple|1|good", "en/logs/apple|2|hard", "en/entries/pear"} <= set(data)


def test_older_write_loses_even_if_it_arrives_last(user):
    account_sync.push(user, "b", [rec("en/entries/apple", 20, "new")])
    out = account_sync.push(user, "a", [rec("en/entries/apple", 10, "old")])
    assert (out["accepted"], out["ignored"]) == (0, 1)
    assert account_sync.pull(user, 0)["records"][0]["data"] == "new"


def test_repeated_upload_counts_once(user):
    batch = [rec("en/logs/apple|1|good", 10), rec("en/entries/apple", 10)]
    first = account_sync.push(user, "a", batch)
    again = account_sync.push(user, "a", batch)
    assert (first["accepted"], again["accepted"], again["ignored"]) == (2, 0, 2)
    assert first["seq"] == again["seq"]
    assert len(account_sync.pull(user, 0)["records"]) == 2


def test_tombstone_beats_older_edit_and_loses_to_newer_one(user):
    account_sync.push(user, "a", [rec("en/entries/apple", 10)])
    account_sync.push(user, "a", [rec("en/entries/apple", 20, deleted=True)])
    account_sync.push(user, "b", [rec("en/entries/apple", 15, "offline edit")])
    assert account_sync.pull(user, 0)["records"][0]["deleted"] is True
    account_sync.push(user, "b", [rec("en/entries/apple", 30, "added again")])
    r = account_sync.pull(user, 0)["records"][0]
    assert (r["deleted"], r["data"]) == (False, "added again")


def test_pull_pages_by_seq_and_skips_own_device(user):
    account_sync.push(user, "a", [rec(f"en/entries/w{i}", 10) for i in range(5)])
    account_sync.push(user, "b", [rec("en/entries/z", 10)])
    page = account_sync.pull(user, 0, limit=3)
    assert page["more"] and len(page["records"]) == 3
    rest = account_sync.pull(user, page["next"], limit=3)
    assert not rest["more"] and keys(rest) == ["en/entries/w3", "en/entries/w4", "en/entries/z"]
    assert keys(account_sync.pull(user, 0, device="a")) == ["en/entries/z"]
    assert account_sync.pull(user, 0, device="a", limit=5)["next"] == 5    # past a's own records too


def test_blob_roundtrip_deleted_with_its_photo(user):
    account_sync.put_blob(user, "photo-1-0", b"jpeg")
    account_sync.put_blob(user, "photo-1-0", b"jpeg2")
    assert account_sync.load_blob(user, "photo-1-0") == b"jpeg2"
    account_sync.push(user, "a", [rec("en/photos/photo-1-0", 10, deleted=True)])
    with pytest.raises(accounts.AccountError) as e:
        account_sync.load_blob(user, "photo-1-0")
    assert e.value.status == 404


def test_blob_id_cannot_leave_the_folder_and_quota_holds(user, monkeypatch):
    with pytest.raises(accounts.AccountError):
        account_sync.put_blob(user, "../../evil", b"x")
    monkeypatch.setattr(account_sync, "ACCOUNT_BLOBS_MAX_BYTES", 5)
    account_sync.put_blob(user, "a", b"1234")
    account_sync.put_blob(user, "a", b"12345")      # replacing does not count twice
    with pytest.raises(accounts.AccountError) as e:
        account_sync.put_blob(user, "b", b"1")
    assert e.value.status == 507


def test_accounts_do_not_see_each_other(user):
    account_sync.push(user, "a", [rec("en/entries/apple", 10)])
    assert account_sync.pull(User(2), 0)["records"] == []


def test_delete_account_removes_records_and_photos(session, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    user, _ = accounts.register_email(session, "s912@x.com", "password1", "S", "zh-TW", "B1")
    account_sync.push(user, "a", [rec("en/entries/apple", 10)])
    account_sync.put_blob(user, "p1", b"x")
    accounts.delete_account(session, user)
    assert list((tmp_path / "user_sync").iterdir()) == []
