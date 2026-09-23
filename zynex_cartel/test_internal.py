"""
ZYNEX CARTEL — Internal test suite.
Runs offline against a temp DB + fake Bot; optional live getMe smoke.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Isolate DB before importing project modules
_TMP = Path(tempfile.mkdtemp(prefix="zynex_test_"))
os.environ["DATABASE_URL"] = str(_TMP / "test.db")
os.environ["LOG_LEVEL"] = "WARNING"

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Windows console is often cp1252 — force UTF-8 for PASS/FAIL prints
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        # ascii() keeps Windows cp1252 consoles from crashing on emoji/small-caps
        safe = ascii(detail) if detail else ""
        msg = f"{name}" + (f" — {safe}" if safe else "")
        FAILURES.append(msg)
        print(f"  FAIL  {msg}")


class FakeBot:
    """Minimal Bot stand-in for engine tests (no network)."""

    def __init__(self, channel_ok=True, group_ok=True, fail_api=False):
        self.channel_ok = channel_ok
        self.group_ok = group_ok
        self.fail_api = fail_api
        self.sent: list[dict] = []
        self.edited: list[dict] = []
        self._mid = 1000

    async def get_chat_member(self, chat_id, user_id):
        from telegram import ChatMember, ChatMemberUpdated  # noqa: F401
        from telegram.error import TelegramError

        if self.fail_api:
            raise TelegramError("simulated API failure")

        class M:
            pass

        m = M()
        if chat_id < -1000000000000:  # channel-ish (negative)
            status = "member" if self.channel_ok else "left"
        else:
            status = "member" if self.group_ok else "left"
        m.status = status
        return m

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        self._mid += 1
        self.sent.append(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                "message_id": self._mid,
            }
        )

        class Msg:
            pass

        msg = Msg()
        msg.message_id = self._mid
        return msg

    async def edit_message_text(self, chat_id, message_id, text, parse_mode=None, reply_markup=None, **kw):
        self.edited.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )

        class Msg:
            pass

        m = Msg()
        m.message_id = message_id
        return m

    async def copy_message(self, chat_id, from_chat_id, message_id, **kw):
        self._mid += 1

        class Job:
            pass

        j = Job()
        j.message_id = self._mid
        return j


async def test_emoji_and_utils():
    print("\n== emoji / utils ==")
    from emoji_packs import E, custom_emoji, CUSTOM_EMOJI_IDS
    from utils import (
        giveaway_type_emoji,
        giveaway_type_emoji_plain,
        status_emoji,
        parse_ist_datetime,
        format_ist,
        to_utc_iso,
        from_utc_iso,
        is_expired,
        time_remaining,
        chunk_text,
        is_valid_user_id,
    )
    from config import GiveawayType, GiveawayStatus

    for label, val in [
        ("E.CROSS", E.CROSS),
        ("E.CHECK", E.CHECK),
        ("E.WARNING", E.WARNING),
        ("E.SLOT", E.SLOT),
        ("E.VOTE", E.VOTE),
        ("E.PERSON", E.PERSON),
        ("giveaway_type_emoji(1)", giveaway_type_emoji(GiveawayType.VOTE)),
        ("giveaway_type_emoji(2)", giveaway_type_emoji(GiveawayType.RANDOM)),
        ("giveaway_type_emoji(3)", giveaway_type_emoji(GiveawayType.SLOT)),
        ("status_emoji(ACTIVE)", status_emoji(GiveawayStatus.ACTIVE)),
        ("status_emoji(ENDED)", status_emoji(GiveawayStatus.ENDED)),
    ]:
        check(f"premium {label} is <tg-emoji>", isinstance(val, str) and val.startswith('<tg-emoji emoji-id="'), repr(val)[:80])

    check("custom_emoji formats id", custom_emoji("X", "123") == '<tg-emoji emoji-id="123">X</tg-emoji>')
    check("17 custom emoji ids", len(CUSTOM_EMOJI_IDS) == 17, str(len(CUSTOM_EMOJI_IDS)))
    check("plain type emojis", giveaway_type_emoji_plain(1) == "🗳️" and giveaway_type_emoji_plain(2) == "🎲" and giveaway_type_emoji_plain(3) == "🎰")

    dt = parse_ist_datetime("24/09/2026 18:30")
    check("parse_ist_datetime", dt is not None and dt.tzinfo is not None)
    check("format_ist has IST", "IST" in format_ist(dt))
    iso = to_utc_iso(dt)
    check("to_utc_iso roundtrip", from_utc_iso(iso).year == 2026)

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    check("is_expired past", is_expired(past) is True)
    check("is_expired future", is_expired(future) is False)
    check("time_remaining future has h/m", "h" in time_remaining(future) or "m" in time_remaining(future))
    check("time_remaining past Ended", time_remaining(past) == "Ended")

    check("chunk_text short", chunk_text("hi") == ["hi"])
    long = ("line\n" * 1000)
    parts = chunk_text(long, 100)
    check("chunk_text splits", len(parts) > 1 and all(len(p) <= 100 for p in parts), str([len(p) for p in parts[:5]]))
    check("is_valid_user_id", is_valid_user_id("8301883098") and not is_valid_user_id("12"))


def _plain_emoji_in(s: str) -> bool:
    # Detect common unicode emojis in a string (exclude small caps / latin)
    return bool(re.search(
        r"[\U0001F300-\U0001FAFF☀-➿️‍⭐✦❤♻⚠❗▶◀⏹➕➖]",
        s,
    ))


async def run_keyboard_tests():
    from utils.keyboards import (
        btn_success, btn_primary, btn_danger, btn_default,
        btn_green, btn_blue, btn_red, btn_yellow, btn_purple, btn_orange,
        small_caps, giveaway_info_keyboard, vote_keyboard,
        active_giveaways_keyboard, admin_giveaway_keyboard,
        start_keyboard, verified_keyboard, cancel_keyboard,
        confirm_giveaway_keyboard, vote_confirm_keyboard, main_menu_keyboard,
    )

    b = btn_success("Vote", "cb1")
    check("btn_success style success", b.api_kwargs.get("style") == "success", str(b.api_kwargs))
    check("btn_primary style primary", btn_primary("X", "c").api_kwargs.get("style") == "primary")
    check("btn_danger style danger", btn_danger("X", "c").api_kwargs.get("style") == "danger")
    check("btn_green alias success", btn_green("X", "c").api_kwargs.get("style") == "success")
    check("btn_blue alias primary", btn_blue("X", "c").api_kwargs.get("style") == "primary")
    check("btn_red alias danger", btn_red("X", "c").api_kwargs.get("style") == "danger")
    check("btn_yellow default (no style)", "style" not in (btn_yellow("X", "c").api_kwargs or {}))
    check("btn_purple default", "style" not in (btn_purple("X", "c").api_kwargs or {}))
    check("btn_orange default", "style" not in (btn_orange("X", "c").api_kwargs or {}))

    sc = small_caps("Vote Now")
    # "Vote Now": lowercase → small caps (o/t/e/n/w), uppercase → bold caps (V, N)
    check("small_caps converts", sc != "Vote Now" and "ᴏ" in sc and "𝐍" in sc, ascii(sc))

    # giveaway_info: type 2 (random) must have NO participate/vote button
    kb2 = giveaway_info_keyboard(1, 2)
    rows2 = [r for row in kb2.inline_keyboard for r in row]
    data2 = [x.callback_data for x in rows2 if x.callback_data]
    check("type2 no vote_start", not any("vote_start" in d for d in data2), str(data2))
    check("type2 no info_slot", not any("info_slot" in d for d in data2), str(data2))
    check("type2 still has participants", any("participant_count" in d for d in data2), str(data2))

    kb1 = giveaway_info_keyboard(1, 1)
    d1 = [x.callback_data for row in kb1.inline_keyboard for x in row if x.callback_data]
    check("type1 has vote_start", any("vote_start" in d for d in d1), str(d1))

    kb3 = giveaway_info_keyboard(5, 3)
    d3 = [x.callback_data for row in kb3.inline_keyboard for x in row if x.callback_data]
    check("type3 has info_slot", any("info_slot" in d for d in d3), str(d3))

    # Buttons must not contain premium HTML
    all_texts = []
    for mk in (
        giveaway_info_keyboard(1, 1),
        vote_keyboard(1, [{"user_id": 1, "display_name": "A", "vote_count": 2}]),
        active_giveaways_keyboard([{"giveaway_id": 1, "name": "Test", "type": 1}]),
        admin_giveaway_keyboard(1),
        start_keyboard([{"id": -100, "name": "Ch", "url": "https://t.me/+x"}]),
        verified_keyboard(),
        cancel_keyboard(),
        confirm_giveaway_keyboard(1),
        vote_confirm_keyboard(1, 2),
        main_menu_keyboard(),
    ):
        for row in mk.inline_keyboard:
            for btn in row:
                all_texts.append(btn.text)
                check_text = btn.text
                if "<tg-emoji" in check_text or "<b>" in check_text:
                    check(f"no HTML in button: {check_text[:30]}", False, check_text)

    check("buttons built without HTML", all("<tg-emoji" not in t and "<b>" not in t for t in all_texts))
    # BE.VOTE plain unicode present in vote button
    check("vote button uses plain VOTE", any("🗳" in t for t in all_texts), str(all_texts))


async def test_engines():
    print("\n== engines ==")
    from engines.vote_giveaway_engine import validate_name, membership_messages, build_channel_message_text, build_vote_button
    from engines.slot_engine import SlotGiveawayEngine, WINNING_RESULT
    from engines.random_engine import RandomGiveawayEngine

    ok, name = validate_name("  Alice  ")
    check("validate_name ok", ok and name == "Alice", repr(name))
    ok, err = validate_name("")
    check("validate_name empty fails", not ok and "tg-emoji" in err, repr(err))
    ok, err = validate_name("x" * 33)
    check("validate_name too long fails", not ok and "tg-emoji" in err, repr(err))
    ok, err = validate_name("bad\x00name")
    check("validate_name control chars fails", not ok, repr(err))

    # membership messages — pure premium, no plain emoji outside tags
    m = {"channel": False, "group": True, "channel_error": False, "group_error": False}
    msgs = membership_messages(m)
    check("membership channel msg has E.CROSS", any("tg-emoji" in x for x in msgs) and len(msgs) == 1, str(msgs))
    m = {"channel": False, "group": False, "channel_error": False, "group_error": False}
    msgs = membership_messages(m)
    check("membership both → single combined msg", len(msgs) == 1 and "both" in msgs[0], str(msgs))
    m = {"channel": True, "group": True, "channel_error": True, "group_error": False}
    msgs = membership_messages(m)
    check("channel_error message", len(msgs) == 1 and "Could not verify" in msgs[0], str(msgs))

    text = build_channel_message_text("Bob <script>", 5)
    check("channel msg escapes HTML", "&lt;script&gt;" in text and "tg-emoji" in text, text)
    check("channel msg has code tag", "<code>5</code>" in text, text)

    kb = build_vote_button(7, 3)
    row = kb.inline_keyboard[0][0]
    check("vote button success style", row.api_kwargs.get("style") == "success")
    check("vote button callback", row.callback_data == "vgvote:3:7", row.callback_data)
    check("vote button no premium HTML", "<tg-emoji" not in row.text and "<b>" not in row.text, row.text)

    # Slot parser
    eng = SlotGiveawayEngine(None)
    check("slot plain 777", eng.parse_slot_result("7 7 7")[0] is True)
    check("slot emoji 7s", eng.parse_slot_result("7️⃣ 7️⃣ 7️⃣")[0] is True)
    check("slot combined 777", eng.parse_slot_result("777")[0] is True)
    check("slot non-win", eng.parse_slot_result("🍒 🍋 🍊")[0] is False)
    check("slot empty", eng.parse_slot_result("")[0] is False)
    check("is_slot_message 🎰", eng.is_slot_message("🎰") is True)
    check("is_slot_message text", eng.is_slot_message("hello") is False)
    check("WINNING_RESULT triple 7", WINNING_RESULT == "7️⃣ 7️⃣ 7️⃣")


async def test_db_and_vote_flow():
    print("\n== database + vote engine flow ==")
    import database as db
    from engines.vote_giveaway_engine import select_vote_winners, process_vote, admin_adjust
    from engines.random_engine import RandomGiveawayEngine

    await db.init_db()

    # Create + activate a vote giveaway
    start = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    gid = await db.create_giveaway("TestVote", 1, 3, start, end, -1003777955255, -1004484790002, 8301883098)
    await db.update_giveaway_status(gid, "ACTIVE")
    g = await db.get_giveaway(gid)
    check("create giveaway ACTIVE", g is not None and g["status"] == "ACTIVE")

    # Participants with telegram IDs
    p1 = await db.create_vote_participant(gid, "Alice", telegram_user_id=111, owner_registered=True)
    p2 = await db.create_vote_participant(gid, "Bob", telegram_user_id=222, owner_registered=True)
    p3 = await db.create_vote_participant(gid, "Cara", telegram_user_id=333, owner_registered=True)
    check("3 participants created", all(x is not None for x in (p1, p2, p3)), f"{p1},{p2},{p3}")

    # Duplicate name
    dup = await db.create_vote_participant(gid, "Alice", telegram_user_id=999, owner_registered=True)
    check("duplicate name rejected", dup is None, str(dup))

    # Cast votes: Alice 5, Bob 3, Cara 1 (use admin_add_votes + cast_vote)
    # Direct cast_vote from voters 1001.. etc — one vote each per voter
    # Use admin_add_votes for bulk
    await db.admin_add_votes(p1, admin_id=8301883098, giveaway_id=gid, amount=5)
    await db.admin_add_votes(p2, admin_id=8301883098, giveaway_id=gid, amount=3)
    await db.admin_add_votes(p3, admin_id=8301883098, giveaway_id=gid, amount=1)

    t1 = await db.get_vote_total(p1)
    t2 = await db.get_vote_total(p2)
    t3 = await db.get_vote_total(p3)
    check("vote totals 5/3/1", (t1, t2, t3) == (5, 3, 1), f"{t1},{t2},{t3}")

    winners = await select_vote_winners(gid, 3)
    check("select_vote_winners count", len(winners) == 3, str(winners))
    if winners:
        check("winner order strict 5>3>1", winners[0]["votes"] == 5 and winners[1]["votes"] == 3 and winners[2]["votes"] == 1, str(winners))
        check("winner positions 1,2,3", [w["position"] for w in winners] == [1, 2, 3])
        check("winner user_ids", [w["user_id"] for w in winners] == [111, 222, 333], str([w["user_id"] for w in winners]))
        check("no equal-vote winners adjacent", all(winners[i]["votes"] > winners[i + 1]["votes"] for i in range(len(winners) - 1)))

    # Tie case: add equal votes on fresh giveaway
    gid2 = await db.create_giveaway("TieVote", 1, 2, start, end, -1003777955255, -1004484790002, 8301883098)
    await db.update_giveaway_status(gid2, "ACTIVE")
    q1 = await db.create_vote_participant(gid2, "TieA", telegram_user_id=444, owner_registered=True)
    q2 = await db.create_vote_participant(gid2, "TieB", telegram_user_id=555, owner_registered=True)
    await db.admin_add_votes(q1, 8301883098, gid2, 4)
    await db.admin_add_votes(q2, 8301883098, gid2, 4)
    # Only one tied top can win first position; next must have fewer — so second winner skipped
    tw = await select_vote_winners(gid2, 2)
    check("tie: only one winner at same count", len(tw) == 1 and tw[0]["votes"] == 4, str(tw))
    if tw:
        check("tie broken by earliest registration", tw[0]["user_id"] == 444, str(tw[0]))

    # process_vote with FakeBot — membership fail-open via API error
    class FB:
        async def get_chat_member(self, chat_id, user_id):
            from telegram.error import TelegramError
            raise TelegramError("no perm")

        async def edit_message_text(self, **kw):
            class M:
                message_id = 1
            return M()

        async def send_message(self, **kw):
            class M:
                message_id = 1
            return M()

    # Need active vote giveaway as THE active one — deactivate others first
    await db.update_giveaway_status(gid, "ENDED")
    await db.update_giveaway_status(gid2, "ENDED")
    gid3 = await db.create_giveaway("LiveVote", 1, 1, start, end, -1003777955255, -1004484790002, 8301883098)
    await db.update_giveaway_status(gid3, "ACTIVE")
    la = await db.create_vote_participant(gid3, "LiveA", telegram_user_id=777, owner_registered=True)
    await db.set_vote_channel_message(la, 42)

    bot = FB()
    # Fresh voter — no history
    res = await process_vote(bot, gid3, la, 900001)
    check("process_vote success", res.get("status") == "success", str(res))
    check("process_vote plain popup", res.get("message") == "Vote recorded." and not _plain_emoji_in(res.get("message", "")), str(res))

    res2 = await process_vote(bot, gid3, la, 900001)
    check("second vote blocked", res2.get("status") == "already_voted", str(res2))
    check("already_voted no emoji", not _plain_emoji_in(res2.get("message", "")), res2.get("message", ""))

    # Revoke then re-vote SAME participant allowed
    pid_rev = await db.revoke_vote_by_voter(gid3, 900001)
    check("revoke vote returns pid", pid_rev == la, str(pid_rev))
    res3 = await process_vote(bot, gid3, la, 900001)
    check("re-vote same participant allowed", res3.get("status") == "success", str(res3))

    # Revoke then try OTHER participant → blocked
    lb = await db.create_vote_participant(gid3, "LiveB", telegram_user_id=888, owner_registered=True)
    await db.set_vote_channel_message(lb, 43)
    await db.revoke_vote_by_voter(gid3, 900001)
    res4 = await process_vote(bot, gid3, lb, 900001)
    check("re-vote different participant blocked", res4.get("status") == "wrong_participant", str(res4))

    # Random engine
    reng = RandomGiveawayEngine(None)
    # add participants via add_participant
    for uid in (2001, 2002, 2003):
        await db.add_participant(gid3, uid)
    # end active so we can... actually random select uses get_giveaway only
    wins = await reng.select_winners(gid3)
    check("random winners unique", len(wins) >= 1 and len({w["user_id"] for w in wins}) == len(wins), str(wins))
    check("random positions sequential", [w["position"] for w in wins] == list(range(1, len(wins) + 1)), str(wins))
    check("random method RANDOM", all(w["selection_method"] == "RANDOM" for w in wins))

    # admin_adjust errors use premium
    bad = await admin_adjust(None, gid3, 123456789, 5, 8301883098, "add")
    check("admin_adjust missing participant", bad.get("success") is False and "tg-emoji" in bad.get("error", ""), str(bad))
    # LiveA linked to 777
    # need bot for channel update — use FB
    good = await admin_adjust(bot, gid3, 777, 2, 8301883098, "add")
    check("admin_adjust add ok", good.get("success") is True and good.get("amount") == 2, str(good))
    zero = await admin_adjust(bot, gid3, 777, 0, 8301883098, "add")
    check("admin_adjust amount>0 required", zero.get("success") is False and "tg-emoji" in zero.get("error", ""), str(zero))


async def test_participant_commands():
    print("\n== participant commands (rank/leaderboard/link) ==")
    import database as db
    from engines.vote_giveaway_engine import (
        build_participant_message_link,
        get_leaderboard_page,
        get_user_rank_info,
        get_user_participant,
        generate_participant_message_link,
    )
    from handlers.participant import (
        mystatus_keyboard,
        leaderboard_keyboard,
        mylink_keyboard,
        _leaderboard_text,
        _status_registered_text,
        STALE_LEADERBOARD,
    )

    # ── Pure link builder ──
    public = build_participant_message_link(-1004484790002, 55, channel_username="ZynexOfficial")
    check("public channel link", public == "https://t.me/ZynexOfficial/55", str(public))
    public_at = build_participant_message_link(-1004484790002, 55, channel_username="@ZynexOfficial")
    check("public link strips @", public_at == "https://t.me/ZynexOfficial/55", str(public_at))
    private = build_participant_message_link(-1004484790002, 55, channel_username=None)
    check(
        "private channel c/ link",
        private is not None and private.startswith("https://t.me/c/") and private.endswith("/55"),
        str(private),
    )
    no_msg = build_participant_message_link(-1004484790002, None, channel_username="x")
    check("no message_id → None", no_msg is None, str(no_msg))

    # ── Competition ranking: ties share rank (1,1,3) ──
    start = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    # End any prior active type-1 giveaways so this is THE active one
    prev = await db.get_active_vote_giveaway()
    if prev:
        await db.update_giveaway_status(prev["giveaway_id"], "ENDED")
    gid = await db.create_giveaway("RankLB", 1, 1, start, end, -1003777955255, -1004484790002, 8301883098)
    await db.update_giveaway_status(gid, "ACTIVE")

    pa = await db.create_vote_participant(gid, "RankA", telegram_user_id=5001, owner_registered=True)
    pb = await db.create_vote_participant(gid, "RankB", telegram_user_id=5002, owner_registered=True)
    pc = await db.create_vote_participant(gid, "RankC", telegram_user_id=5003, owner_registered=True)
    await db.admin_add_votes(pa, 8301883098, gid, 5)
    await db.admin_add_votes(pb, 8301883098, gid, 5)
    await db.admin_add_votes(pc, 8301883098, gid, 3)

    ra = await db.get_participant_rank(gid, pa)
    rb = await db.get_participant_rank(gid, pb)
    rc = await db.get_participant_rank(gid, pc)
    check(
        "competition ranking 1,1,3",
        ra and rb and rc and int(ra["rank_num"]) == 1 and int(rb["rank_num"]) == 1 and int(rc["rank_num"]) == 3,
        f"a={ra['rank_num'] if ra else None} b={rb['rank_num'] if rb else None} c={rc['rank_num'] if rc else None}",
    )
    check(
        "rank vote totals 5/5/3",
        ra and rb and rc and int(ra["total_votes"]) == 5 and int(rb["total_votes"]) == 5 and int(rc["total_votes"]) == 3,
        f"{ra['total_votes'] if ra else None}/{rb['total_votes'] if rb else None}/{rc['total_votes'] if rc else None}",
    )

    # ── Leaderboard page service ──
    board = await get_leaderboard_page(gid, page=1)
    check("leaderboard page total=3", board["total_participants"] == 3, str(board))
    check("leaderboard total_pages=1", board["total_pages"] == 1, str(board))
    check("leaderboard row count", len(board["rows"]) == 3, str(len(board["rows"])))
    check(
        "leaderboard sorted desc",
        [int(r["total_votes"]) for r in board["rows"]] == [5, 5, 3],
        str([int(r["total_votes"]) for r in board["rows"]]),
    )
    check("leaderboard page out of range clamps", (await get_leaderboard_page(gid, page=99))["page"] == 1)

    # ── get_user_participant + rank_info ──
    part = await get_user_participant(gid, 5001)
    check("get_user_participant by user_id", part is not None and part["participant_name"] == "RankA", str(part))
    info = await get_user_rank_info(gid, part["id"])
    check("mystatus rank_info votes=5 rank=1", info["votes"] == 5 and info["rank"] == 1, str(info))
    missing = await get_user_participant(gid, 999999)
    check("unregistered user → None", missing is None, str(missing))

    # ── Text builders use premium E.* + HTML-safe ──
    g = await db.get_giveaway(gid)
    status_html = _status_registered_text(g, part, info)
    check("mystatus uses tg-emoji", "<tg-emoji" in status_html and "ParseMode" not in status_html)
    check("mystatus shows rank #1", "#1" in status_html, status_html[:80])
    lb_html = _leaderboard_text(g, board)
    check("leaderboard uses tg-emoji", "<tg-emoji" in lb_html)
    check("leaderboard shows Participant names", "RankA" in lb_html and "RankC" in lb_html)

    # ── Keyboards: plain BE only, no tg-emoji in button labels ──
    for name, kb in (
        ("mystatus kb", mystatus_keyboard()),
        ("lb kb", leaderboard_keyboard(gid, 1, 1)),
        ("mylink kb (no url)", mylink_keyboard(None)),
        ("mylink kb (url)", mylink_keyboard("https://t.me/x/1")),
    ):
        labels = [b.text for row in kb.inline_keyboard for b in row]
        check(
            f"{name} no tg-emoji",
            all("<tg-emoji" not in (t or "") for t in labels),
            str(labels),
        )
        check(
            f"{name} no E.* HTML remnants",
            all("emoji-id=" not in (t or "") for t in labels),
            str(labels),
        )

    # ── mylink keyboard with URL includes Vote for Me ──
    kb_url = mylink_keyboard("https://t.me/ZynexOfficial/55")
    urls = [b.url for row in kb_url.inline_keyboard for b in row if b.url]
    check("mylink Vote for Me url present", urls == ["https://t.me/ZynexOfficial/55"], str(urls))
    kb_nourl = mylink_keyboard(None)
    urls2 = [b.url for row in kb_nourl.inline_keyboard for b in row if b.url]
    check("mylink no broken url button", urls2 == [], str(urls2))

    # ── Stale popup text is emoji-free (policy) ──
    check("stale popup no emoji", not _plain_emoji_in(STALE_LEADERBOARD), STALE_LEADERBOARD)

    # ── generate_participant_message_link via FakeBot ──
    class LinkBot:
        def __init__(self, username="ZynexOfficial"):
            self._u = username

        async def get_chat(self, chat_id):
            class C:
                pass

            c = C()
            c.username = self._u
            return c

    await db.set_vote_channel_message(pa, 777)
    fresh = await db.get_vote_participant_by_id(pa)
    link = await generate_participant_message_link(LinkBot(), fresh)
    check(
        "generate_participant_message_link public",
        link == "https://t.me/ZynexOfficial/777",
        str(link),
    )
    # No channel message → None
    no_msg_part = await db.get_vote_participant_by_id(pc)
    link_none = await generate_participant_message_link(LinkBot(), no_msg_part)
    check("generate link without message → None", link_none is None, str(link_none))


async def test_restart_helpers():
    print("\n== restart / git watch helpers ==")
    from utils import process_restart as pr

    # arm once
    pr.reset_restart_arm()
    check("arm_restart first call", pr.arm_restart("test") is True)
    check("arm_restart second call blocked", pr.arm_restart("test2") is False)
    check("is_restart_armed", pr.is_restart_armed() is True)
    pr.reset_restart_arm()
    check("reset_restart_arm clears", pr.is_restart_armed() is False)

    # argv builder
    argv = pr.build_restart_argv(["zynex_cartel/main.py"])
    check(
        "build_restart_argv uses sys.executable",
        argv[0] == sys.executable and argv[1] == "zynex_cartel/main.py",
        str(argv),
    )
    argv_default = pr.build_restart_argv([])
    check("build_restart_argv empty falls back", len(argv_default) >= 2, str(argv_default))

    # git head in this repo
    head = pr.get_git_head()
    check(
        "get_git_head returns 40-char sha or None",
        head is None or (isinstance(head, str) and len(head) == 40 and all(c in "0123456789abcdef" for c in head.lower())),
        str(head),
    )

    # owner-only /restart registration present
    src = (ROOT / "handlers" / "admin.py").read_text(encoding="utf-8")
    check("admin.py defines restart_command", "async def restart_command" in src)
    check("admin.py registers /restart", 'CommandHandler("restart"' in src)
    check("restart uses owner_only", "@owner_only" in src and "restart_command" in src)

    main_src = (ROOT / "main.py").read_text(encoding="utf-8")
    check("main.py starts git watcher", "_git_watch_loop" in main_src and "schedule_restart" in main_src)
    check("main.py cancels git watcher", "git_watch_task" in main_src)

    pr_src = (ROOT / "utils" / "process_restart.py").read_text(encoding="utf-8")
    check("process_restart has execv path", "os.execv" in pr_src)
    check("process_restart has Windows spawn fallback", "subprocess.Popen" in pr_src)

    # adminhelp mentions /restart
    help_src = (ROOT / "handlers" / "start.py").read_text(encoding="utf-8")
    check("adminhelp lists /restart", "/restart" in help_src)


async def test_source_policy():
    print("\n== source policy scan ==")
    handlers = ROOT / "handlers"
    engines = ROOT / "engines"
    # Popups: query.answer( must not contain plain emoji
    popup_bad = []
    answer_re = re.compile(r"query\.answer\(\s*(?:text\s*=\s*)?([\"'])(.*?)\1", re.S)
    for p in list(handlers.glob("*.py")) + list(engines.glob("*.py")):
        src = p.read_text(encoding="utf-8")
        for m in answer_re.finditer(src):
            s = m.group(2)
            if _plain_emoji_in(s):
                popup_bad.append(f"{p.name}: {s[:60]}")
    check("query.answer popups have no plain emojis", not popup_bad, "; ".join(popup_bad[:5]))

    # reply_text / edit_message_text / send_message literals containing E. must use ParseMode.HTML nearby
    # Heuristic: lines with f-string containing E. and reply_text must have parse_mode HTML within same call — hard.
    # Instead: ensure no f-string with <tg-emoji from E. is sent without HTML in same statement block.
    missing_html = []
    call_re = re.compile(
        r"\.(?:reply_text|edit_message_text|send_message)\((.*?)\)\s*$",
        re.M | re.S,
    )
    # Simpler: find f-strings with E.XXX in handler files; check the call containing them has ParseMode.HTML
    for p in handlers.glob("*.py"):
        src = p.read_text(encoding="utf-8")
        # split roughly on await calls
        for m in re.finditer(r"await\s+[^(\n]+\((?:[^()]|\([^()]*\))*\)", src, re.S):
            call = m.group(0)
            if re.search(r"\bE\.[A-Z_]+", call) or "tg-emoji" in call or "<code>" in call:
                if any(x in call for x in ("reply_text", "edit_message_text", "send_message", "answer(")):
                    if "ParseMode.HTML" not in call and "parse_mode" not in call:
                        # answer() popups shouldn't have E. at all
                        if "answer(" in call:
                            missing_html.append(f"{p.name}: emoji in answer → {call[:80]!r}")
                        else:
                            missing_html.append(f"{p.name}: missing HTML → {call[:100]!r}")
    check("E.* / HTML messages carry parse_mode", not missing_html, " | ".join(missing_html[:6]))

    # Random type 2 must not advertise a participate button in keyboards
    kb_src = (ROOT / "utils" / "keyboards.py").read_text(encoding="utf-8")
    check("keyboards type2 branch is pass", "elif gtype == 2" in kb_src and "pass" in kb_src.split("elif gtype == 2")[1][:120])


async def test_live_api_smoke():
    print("\n== live Telegram API smoke ==")
    bot = None
    try:
        from telegram import Bot
        from config import BOT_TOKEN

        bot = Bot(token=BOT_TOKEN)
        me = await bot.get_me()
        check("getMe ok", me.is_bot and me.username, f"{me.username} id={me.id}")
        from config import GIVEAWAY_GROUP_ID, GIVEAWAY_CHANNEL_ID
        try:
            g = await bot.get_chat(GIVEAWAY_GROUP_ID)
            check("getChat group", g.id == GIVEAWAY_GROUP_ID, str(g.id))
        except Exception as e:
            check("getChat group", False, str(e))
        try:
            c = await bot.get_chat(GIVEAWAY_CHANNEL_ID)
            check("getChat channel", c.id == GIVEAWAY_CHANNEL_ID, str(c.id))
        except Exception as e:
            check("getChat channel", False, str(e))
    except Exception as e:
        check("live API smoke", False, f"{type(e).__name__}: {e}")
    finally:
        if bot is not None:
            try:
                await bot.shutdown()
            except Exception:
                pass


async def main():
    print("ZYNEX internal tests")
    print(f"temp DB: {os.environ['DATABASE_URL']}")
    try:
        await test_emoji_and_utils()
        await run_keyboard_tests()
        await test_engines()
        await test_db_and_vote_flow()
        await test_participant_commands()
        await test_restart_helpers()
        await test_source_policy()
        await test_live_api_smoke()
    except Exception:
        traceback.print_exc()
        global FAIL
        FAIL += 1
        FAILURES.append("unhandled exception in suite")

    print(f"\n==== RESULT: {PASS} passed, {FAIL} failed ====")
    if FAILURES:
        print("Failures:")
        for f in FAILURES:
            print(f"  - {f}")
    # Close any leftover DB handle so the process can exit
    try:
        import database as db
        await db.close_db()
    except Exception:
        pass
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
