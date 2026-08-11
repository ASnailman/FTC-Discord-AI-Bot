import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import chain
import config
import clients
from data_retrieval import fetch_team_data, get_cached_teams_by_region
from extraction import extract_info
from logging_setup import get_logger
from seasons import SEASON_NAMES
from vectordb import VectorDBManager

logger = get_logger(__name__)

vectordb = VectorDBManager()

# Chroma's PersistentClient is not safe for concurrent writers; serialize
# upserts across simultaneous /ask invocations.
_chroma_write_lock = asyncio.Lock()

# Discord echoes whatever text we send verbatim; external community sources
# (Reddit/Chief Delphi/YouTube captions) are attacker-reachable text that
# could contain an @everyone/@here or a user/role mention. Disabling all
# mentions on every outbound message means such text is inert regardless of
# what nodes.fusion's sanitization does or doesn't catch -- see docs/security.md.
_NO_MENTIONS = discord.AllowedMentions.none()


class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """Runs once at startup, before the bot connects."""
        await asyncio.to_thread(clients.warm_up)

        if config.DISCORD_GUILD_ID:
            guild = discord.Object(id=int(config.DISCORD_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Synced slash commands to guild {config.DISCORD_GUILD_ID} (instant).")
        else:
            await self.tree.sync()
            print("Synced slash commands globally (may take up to an hour to propagate).")


bot = MyBot()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")


@bot.tree.command(name="ping", description="Check the bot's latency")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Latency: {latency}ms", allowed_mentions=_NO_MENTIONS)


async def region_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    abbreviations = [
        "All", "UnitedStates", "International", "USCA", "USNY", "USTX", "AU", "BR",
        "CAAB", "CABC", "CAON", "CAQC", "CMPIC", "CMPZ2", "CN", "CY", "DE", "EG",
        "ES", "FR", "GB", "IL", "IN", "JM", "KR", "KZ", "LY", "MX", "NG", "NL",
        "NZ", "ONADOD", "QA", "RO", "RU", "SA", "TH", "TW", "USAK", "USAL", "USAR",
        "USARL", "USAZ", "USCALA", "USCALS", "USCANO", "USCASD", "USCHS", "USCO",
        "USCT", "USDE", "USFL", "USGA", "USHI", "USIA", "USID", "USIL", "USIN",
        "USKY", "USLA", "USMA", "USMD", "USMI", "USMN", "USMOKS", "USMS", "USMT",
        "USNC", "USND", "USNE", "USNH", "USNJ", "USNM", "USNV", "USNYEX", "USNYLI",
        "USNYNY", "USOH", "USOK", "USOR", "USPA", "USRI", "USSC", "USTN", "USTXCE",
        "USTXHO", "USTXNO", "USTXSO", "USTXWP", "USUT", "USVA", "USVT", "USWA",
        "USWI", "USWV", "USWY", "ZA",
    ]
    expanded_names = [
        "Worldwide", "United States", "International", "California (General)", "New York (General)",
        "Texas (General)", "Australia", "Brazil", "Alberta, Canada", "British Columbia, Canada",
        "Ontario, Canada", "Quebec, Canada", "Championship - Impact", "Championship - Zone 2",
        "China", "Cyprus", "Germany", "Egypt", "Spain", "France", "United Kingdom", "Israel",
        "India", "Jamaica", "South Korea", "Kazakhstan", "Libya", "Mexico", "Nigeria",
        "Netherlands", "New Zealand", "Ontario - DoDEA", "Qatar", "Romania", "Russia",
        "Saudi Arabia", "Thailand", "Taiwan", "Alaska", "Alabama", "Arkansas",
        "Arkansas (Regional/League)", "Arizona", "California - Los Angeles", "California - Southern",
        "California - Northern", "California - San Diego", "Chesapeake (MD/VA/DC)", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Iowa", "Idaho", "Illinois",
        "Indiana", "Kentucky", "Louisiana", "Massachusetts", "Maryland", "Michigan", "Minnesota",
        "Missouri / Kansas", "Mississippi", "Montana", "North Carolina", "North Dakota", "Nebraska",
        "New Hampshire", "New Jersey", "New Mexico", "Nevada", "New York - Excelsior",
        "New York - Long Island", "New York - New York City", "Ohio", "Oklahoma", "Oregon",
        "Pennsylvania", "Rhode Island", "South Carolina", "Tennessee", "Texas - Central",
        "Texas - Houston", "Texas - North", "Texas - South", "Texas - West Panhandle", "Utah",
        "Virginia", "Vermont", "Washington", "Wisconsin", "West Virginia", "Wyoming", "South Africa",
    ]

    all_choices = [
        app_commands.Choice(name=name, value=value)
        for name, value in zip(expanded_names, abbreviations)
    ]

    filtered = [
        choice for choice in all_choices
        if current.lower() in choice.name.lower() or current.lower() in choice.value.lower()
    ]
    filtered.sort(key=lambda x: x.name.lower().startswith(current.lower()), reverse=True)
    return filtered[:7]


def _format_reply(question: str, team_nums: list[int], season: int, region: str, answer: str) -> str:
    """Restate the resolved question before the answer, so the user can see
    which team(s)/season/region the bot understood without changing what's
    sent to the LLM (chain.answer still receives the raw `question`)."""
    context_question = f"Regarding Team(s) {team_nums} in the {season} season in {region} region: {question}"
    return f"Question: {context_question}\n\nAnswer: {answer}"


def _chunk_message(text: str, limit: int = None) -> list[str]:
    """Split a reply across multiple messages at Discord's length limit,
    breaking on whitespace so words aren't cut in half."""
    limit = limit or config.DISCORD_MESSAGE_LIMIT
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind(" ", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


@bot.tree.command(name="ask", description="Ask the FTC AI Bot a question")
@app_commands.describe(
    season="FTC Season (OPTIONAL), Defaults to 2025",
    region="Region (OPTIONAL), Defaults to 'All Regions'",
    question="What do you want to know about FTC teams?",
)
@app_commands.choices(season=[
    app_commands.Choice(name=f"{name} ({year})", value=year)
    for year, name in SEASON_NAMES.items()
])
@app_commands.autocomplete(region=region_autocomplete)
async def ask(interaction: discord.Interaction,
              question: str,
              season: app_commands.Choice[int] = None,
              region: str = None):
    await interaction.response.defer()

    season_val = season.value if season is not None else 2025
    region_str = region if region is not None else "All"

    region_dict = await asyncio.to_thread(get_cached_teams_by_region, region_str)
    if region_dict is None:
        await interaction.followup.send(
            "I couldn't reach the FTCScout team directory right now. Please try again shortly.",
            allowed_mentions=_NO_MENTIONS,
        )
        return

    matches = extract_info(question, region_dict)
    team_nums = [num for num, _span, _source in matches]

    if not team_nums:
        await interaction.followup.send(
            "I couldn't identify a team in that question -- try including the team number or "
            "name, e.g. `/ask question: How many matches did 14469 win?`",
            allowed_mentions=_NO_MENTIONS,
        )
        return

    # Reverse lookup for the human-readable names of the identified teams --
    # used by the external nodes (chain.answer) to build better search terms
    # than the bare number alone (e.g. "Technophobia FTC" vs. "14469 FTC").
    names_by_num = {num: name for name, num in region_dict.items()}
    team_names = [names_by_num[n] for n in team_nums if n in names_by_num]

    async with _chroma_write_lock:
        for team_num in team_nums:
            try:
                await asyncio.to_thread(
                    vectordb.get_or_load_team,
                    team_num=team_num,
                    fetch_function=fetch_team_data,
                    season=season_val,
                    region=region_str,
                )
            except Exception:
                logger.exception("failed to fetch/cache data for team %s", team_num)
                await interaction.followup.send(
                    f"Failed to fetch data for team {team_num}. Please try again shortly.",
                    allowed_mentions=_NO_MENTIONS,
                )
                return

    try:
        answer = await asyncio.to_thread(
            chain.answer, question, team_nums=team_nums, season=season_val, region=region_str,
            team_names=team_names,
        )
        reply = _format_reply(question, team_nums, season_val, region_str, answer)
        for chunk in _chunk_message(reply):
            await interaction.followup.send(chunk, allowed_mentions=_NO_MENTIONS)
    except Exception:
        logger.exception("unhandled error answering question: %r", question)
        await interaction.followup.send(
            "Something went wrong answering that question. Please try again shortly.",
            allowed_mentions=_NO_MENTIONS,
        )


if __name__ == "__main__":
    if config.DISCORD_TOKEN:
        bot.run(config.DISCORD_TOKEN)
    else:
        print("Error: No DISCORD_TOKEN found in .env file.")
