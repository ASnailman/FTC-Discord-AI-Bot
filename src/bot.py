import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from discord.ui import Button, View

# function imports
from data_retrieval import fetch_team_data, fetch_teams_by_region
from rag_chain import ask_bot, extract_info
from vectordb import VectorDBManager

vectordb = VectorDBManager()

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
# MY_GUILD = discord.Object(id=) # remove later

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        # Prefix is still needed for some internal bot functions
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """This runs when the bot starts, before it connects."""
        # self.tree.copy_global_to(guild=MY_GUILD) # remove this line when switching from testing to global
        # await self.tree.sync(guild=MY_GUILD) # remove guild=MY_GUILD for same reasoning as above
        # print(f"Synced slash commands to guild {MY_GUILD.id}")
        synced = await self.tree.sync
        print(f"Synced {synced} commands globally.")

bot = MyBot()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.tree.command(name="ping", description="Check the bot's latency")
async def ping(interaction: discord.Interaction):
    """Slash command version of ping."""
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Latency: {latency}ms")

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
        "USWI", "USWV", "USWY", "ZA"
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
        "Virginia", "Vermont", "Washington", "Wisconsin", "West Virginia", "Wyoming", "South Africa"
    ]

    all_choices = [
        app_commands.Choice(name=name, value=value) 
        for name, value in zip(expanded_names, abbreviations) # zip obj to make tuples from two iterables
    ]

    # filtered list comprehension
    # check if what user is typing is the name (ex: "illinois") or value (ex:, "USIL")
    filtered = [
        choice for choice in all_choices 
        if current.lower() in choice.name.lower() or current.lower() in choice.value.lower()
    ]

    # sort results to put best matching at top with lamba function
    # set reverse since python sort function puts 0s first, so if a user types "illinois" 
    # and "germany pops up, which is false, it will be at the top"
    filtered.sort(key=lambda x: x.name.lower().startswith(current.lower()), reverse=True)

    return filtered[:7]

@bot.tree.command(name="ask", description="Ask the FTC AI Bot a question")
@app_commands.describe(
    # team="FTC team name or number",
    season="FTC Season (OPTIONAL), Defaults to 2025",
    region="Region (OPTIONAL), Defaults to 'All Regions'",
    question="What do you want to know about FTC teams?"
)
@app_commands.choices(season=[
    app_commands.Choice(name="Decode (2025)", value=2025),
    app_commands.Choice(name="Into the Deep (2024)", value=2024),
    app_commands.Choice(name="Centerstage (2023)", value=2023),
    app_commands.Choice(name="Powerplay (2022)", value=2022),
    app_commands.Choice(name="Freight Frenzy (2021)", value=2021),
    app_commands.Choice(name="Ultimate Goal (2020)", value=2020),
    app_commands.Choice(name="Skystone (2019)", value=2019),
    app_commands.Choice(name="Rover Ruckus (2018)", value=2018)
])
@app_commands.autocomplete(region=region_autocomplete)
async def ask(interaction: discord.Interaction, 
            #   team: int, 
              question: str,
              season: app_commands.Choice[int] = None, 
              region: str = None):
    """Placeholder for your RAG logic."""
    # 'defer' the response because AI can take more than 3 seconds to think
    await interaction.response.defer()

    if season is not None:
        season_val = season.value
    else:
        season_val = 2025
    if region is not None:
        region_str = region
    else:
        region_str = 'All'

    region_dict = fetch_teams_by_region(region_str)
    team_nums = extract_info(question, region_dict)

    for single_team in team_nums:
        try:
            vectordb.get_or_load_team(
                team_num=single_team, 
                fetch_function=fetch_team_data,
                season=season_val,
                region=region_str
            )
        except Exception as e:
            await interaction.followup.send(f"Failed to fetch data: {e}")
            return

    context_question = f"Regarding Team(s) {team_nums} in the {season_val} season in {region_str} region: {question}"
    
    try:
        answer = ask_bot(context_question)
        await interaction.followup.send(f"Question: {question}\n\nAnswer: {answer}")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}")

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: No DISCORD_TOKEN found in .env file.")