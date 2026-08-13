"""Covers /portfolio's command-level error paths in bot.py: validation
before defer(), the three business-logic exceptions caught inside the
generation flow, the cooldown error handler, and the no-mentions/no-leak
invariants every other command in this file already upholds."""
import pytest
from discord import app_commands

import bot
import config
from bot import _NO_MENTIONS
from portfolio.compose import ComposeError
from portfolio.extract import ExtractionResult
from portfolio.ingest import IngestError
from portfolio.render import RenderSecurityError
from portfolio.schema import Banner, PortfolioDoc, PortfolioPage
from portfolio.throttle import QuotaExceededError


class FakeAttachment:
    def __init__(self, filename="cad.png", size=1024):
        self.filename = filename
        self.size = size

    async def read(self):
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 20


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.sent = []
        self._done = False

    async def defer(self):
        self.deferred = True
        self._done = True

    async def send_message(self, content=None, **kwargs):
        self.sent.append({"content": content, **kwargs})
        self._done = True

    def is_done(self):
        return self._done


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kwargs):
        self.sent.append({"content": content, **kwargs})


class FakeUser:
    id = 42


class FakeInteraction:
    def __init__(self):
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.user = FakeUser()
        self.edits = []

    async def edit_original_response(self, content=None, **kwargs):
        self.edits.append(content)


async def _call_portfolio(**kwargs):
    interaction = FakeInteraction()
    defaults = dict(
        team=14496, instructions=None, season=None, accent=None,
        past_portfolio=None, file1=None, file2=None, file3=None, file4=None, file5=None,
    )
    defaults.update(kwargs)
    await bot.portfolio.callback(interaction, **defaults)
    return interaction


def _minimal_doc():
    return PortfolioDoc(
        team_number=14496,
        season_label="Decode (2025)",
        pages=[PortfolioPage(title="Motivate", blocks=[Banner(text="Hello")])],
    )


@pytest.mark.anyio
async def test_no_attachments_is_rejected_before_defer():
    interaction = await _call_portfolio()
    assert interaction.response.deferred is False
    assert interaction.response.sent
    assert "Attach at least one file" in interaction.response.sent[0]["content"]
    assert interaction.response.sent[0]["ephemeral"] is True
    assert interaction.response.sent[0]["allowed_mentions"] is _NO_MENTIONS


@pytest.mark.anyio
async def test_disabled_flag_short_circuits(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_PORTFOLIO", False)
    interaction = await _call_portfolio(file1=FakeAttachment())
    assert "disabled" in interaction.response.sent[0]["content"].lower()
    assert interaction.response.deferred is False


@pytest.mark.anyio
async def test_ingest_error_message_is_shown_verbatim_via_edit(monkeypatch):
    async def _raise_ingest_error(attachments):
        raise IngestError("'bad.exe' has an unsupported file type.")

    monkeypatch.setattr(bot.portfolio_ingest, "validate_and_read", _raise_ingest_error)
    interaction = await _call_portfolio(file1=FakeAttachment())
    assert interaction.response.deferred is True
    assert interaction.edits[-1] == "'bad.exe' has an unsupported file type."


@pytest.mark.anyio
async def test_unexpected_exception_never_leaks_exception_text(monkeypatch):
    async def _raise_ingest_ok(attachments):
        return []

    def _raise_weird(files):
        raise RuntimeError("/etc/shadow: permission denied, secret=abc123")

    monkeypatch.setattr(bot.portfolio_ingest, "validate_and_read", _raise_ingest_ok)
    monkeypatch.setattr(bot.portfolio_extract, "extract_all", _raise_weird)
    interaction = await _call_portfolio(file1=FakeAttachment())
    final_message = interaction.edits[-1]
    assert "secret" not in final_message
    assert "/etc/shadow" not in final_message
    assert final_message == "Something went wrong generating that portfolio. Please try again shortly."


@pytest.mark.anyio
async def test_render_security_error_gives_generic_message_not_raw_html(monkeypatch):
    async def _ok_ingest(attachments):
        return []

    def _ok_extract(files):
        return ExtractionResult()

    def _ok_compose(**kwargs):
        return _minimal_doc(), []

    def _raise_render_security(doc, images=None):
        raise RenderSecurityError("generated HTML matched the forbidden-content scan")

    monkeypatch.setattr(bot.portfolio_ingest, "validate_and_read", _ok_ingest)
    monkeypatch.setattr(bot.portfolio_extract, "extract_all", _ok_extract)
    monkeypatch.setattr(bot.portfolio_compose, "compose", _ok_compose)
    monkeypatch.setattr(bot.portfolio_render, "render_html", _raise_render_security)

    interaction = await _call_portfolio(file1=FakeAttachment())
    assert interaction.edits[-1] == "Something went wrong generating that portfolio. Please try again shortly."


@pytest.mark.anyio
async def test_compose_error_message_is_shown_via_edit(monkeypatch):
    async def _ok_ingest(attachments):
        return []

    def _ok_extract(files):
        return ExtractionResult()

    def _raise_compose(**kwargs):
        raise ComposeError("The model didn't produce any usable pages.")

    monkeypatch.setattr(bot.portfolio_ingest, "validate_and_read", _ok_ingest)
    monkeypatch.setattr(bot.portfolio_extract, "extract_all", _ok_extract)
    monkeypatch.setattr(bot.portfolio_compose, "compose", _raise_compose)

    interaction = await _call_portfolio(file1=FakeAttachment())
    assert interaction.edits[-1] == "The model didn't produce any usable pages."


@pytest.mark.anyio
async def test_daily_quota_exceeded_mid_flow_reports_wait_time(monkeypatch):
    async def _ok_ingest(attachments):
        return []

    def _ok_extract(files):
        return ExtractionResult()

    def _raise_quota(user_id):
        raise QuotaExceededError(retry_after_seconds=3600)

    monkeypatch.setattr(bot.portfolio_ingest, "validate_and_read", _ok_ingest)
    monkeypatch.setattr(bot.portfolio_extract, "extract_all", _ok_extract)
    monkeypatch.setattr(bot.portfolio_throttle, "check_and_consume_daily_quota", _raise_quota)

    interaction = await _call_portfolio(file1=FakeAttachment())
    assert "limit" in interaction.edits[-1].lower()


@pytest.mark.anyio
async def test_successful_generation_sends_html_and_markdown_with_no_mentions(monkeypatch):
    async def _ok_ingest(attachments):
        return []

    def _ok_extract(files):
        return ExtractionResult()

    def _noop_quota(user_id):
        return None

    def _ok_compose(**kwargs):
        return _minimal_doc(), []

    monkeypatch.setattr(bot.portfolio_ingest, "validate_and_read", _ok_ingest)
    monkeypatch.setattr(bot.portfolio_extract, "extract_all", _ok_extract)
    monkeypatch.setattr(bot.portfolio_throttle, "check_and_consume_daily_quota", _noop_quota)
    monkeypatch.setattr(bot.portfolio_compose, "compose", _ok_compose)

    interaction = await _call_portfolio(file1=FakeAttachment())

    assert interaction.response.deferred is True
    assert len(interaction.followup.sent) == 1
    sent = interaction.followup.sent[0]
    assert sent["allowed_mentions"] is _NO_MENTIONS
    filenames = {f.filename for f in sent["files"]}
    assert any(name.endswith(".html") for name in filenames)
    assert any(name.endswith(".md") for name in filenames)


@pytest.mark.anyio
async def test_output_over_size_cap_is_rejected_without_sending_files(monkeypatch):
    async def _ok_ingest(attachments):
        return []

    def _ok_extract(files):
        return ExtractionResult()

    def _noop_quota(user_id):
        return None

    def _ok_compose(**kwargs):
        return _minimal_doc(), []

    monkeypatch.setattr(bot.portfolio_ingest, "validate_and_read", _ok_ingest)
    monkeypatch.setattr(bot.portfolio_extract, "extract_all", _ok_extract)
    monkeypatch.setattr(bot.portfolio_throttle, "check_and_consume_daily_quota", _noop_quota)
    monkeypatch.setattr(bot.portfolio_compose, "compose", _ok_compose)
    monkeypatch.setattr(config, "PORTFOLIO_MAX_OUTPUT_MB", 0.0000001)

    interaction = await _call_portfolio(file1=FakeAttachment())
    assert not interaction.followup.sent
    assert "too large" in interaction.edits[-1].lower()


@pytest.mark.anyio
async def test_cooldown_error_handler_sends_ephemeral_message_not_followup():
    interaction = FakeInteraction()
    cooldown = app_commands.checks.Cooldown(1, 300)
    error = app_commands.CommandOnCooldown(cooldown, retry_after=42.0)
    await bot.portfolio_error(interaction, error)
    assert interaction.response.sent
    assert "42" in interaction.response.sent[0]["content"]
    assert interaction.response.sent[0]["ephemeral"] is True
    assert not interaction.followup.sent
