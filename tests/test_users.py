from app.services.users import DAY_SECONDS, UserStore

NOW = 1_800_000_000


def test_record_counts_activity_and_commands(tmp_path):
    store = UserStore(str(tmp_path / "users.db"))
    store.record(1, "Ann", "ann", private=True, command="bulletin", now=NOW - 20 * DAY_SECONDS)
    store.record(1, "Ann", "ann", private=True, command="bulletin", now=NOW)
    store.record(2, "Ben", None, private=False, command="outline", now=NOW - 3 * DAY_SECONDS)

    stats = store.stats(now=NOW)
    assert (stats["total"], stats["active_1d"], stats["active_7d"], stats["active_30d"]) == (2, 1, 2, 2)
    assert stats["new_7d"] == 1  # Ann first came 20 days ago
    assert stats["top_commands_7d"] == [("bulletin", 1), ("outline", 1)]
    assert store.recipients() == [1]  # Ben only used the bot in a group


def test_known_users_import_and_blocking(tmp_path):
    store = UserStore(str(tmp_path / "users.db"))
    store.record(1, "Ann", None, private=True, now=NOW)
    assert store.import_known([1, 2, 3]) == 2
    assert store.import_known([1, 2, 3]) == 0
    assert store.stats(now=NOW)["never_seen"] == 2

    store.mark_blocked(2)
    assert sorted(store.recipients()) == [1, 3]
    store.record(2, "Cy", None, private=True, now=NOW)  # messaging the bot again unblocks
    assert sorted(store.recipients()) == [1, 2, 3]
