from bot import _NO_MENTIONS, _format_reply, _chunk_message


def test_format_reply_single_team():
    reply = _format_reply("How many matches did 21333 win?", [21333], 2024, "All", "They won 19.")
    assert reply == (
        "Question: Regarding Team(s) [21333] in the 2024 season in All region: "
        "How many matches did 21333 win?\n\n"
        "Answer: They won 19."
    )


def test_format_reply_multi_team():
    reply = _format_reply("Compare 14469 and 21333", [14469, 21333], 2025, "USIL", "Both are strong.")
    assert "Regarding Team(s) [14469, 21333] in the 2025 season in USIL region:" in reply
    assert reply.startswith("Question: ")
    assert "\n\nAnswer: Both are strong." in reply


def test_format_reply_answer_follows_double_newline():
    reply = _format_reply("q", [1], 2025, "All", "a")
    question_part, answer_part = reply.split("\n\n", 1)
    assert question_part.startswith("Question: ")
    assert answer_part == "Answer: a"


def test_chunk_message_short_text_unchanged():
    assert _chunk_message("short answer") == ["short answer"]


def test_chunk_message_splits_long_text_on_whitespace():
    text = ("word " * 500).strip()
    chunks = _chunk_message(text, limit=100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
    # no word should be split across chunks
    assert " ".join(chunks).replace("  ", " ") == text


def test_no_mentions_suppresses_everyone_and_roles_and_users():
    """External community text (Reddit/Chief Delphi/YouTube) is
    attacker-reachable and gets echoed into Discord replies -- every
    outbound send must use this so a stray @everyone/@role/@user in that
    text can never actually ping anyone."""
    assert _NO_MENTIONS.everyone is False
    assert _NO_MENTIONS.users is False
    assert _NO_MENTIONS.roles is False
