import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from discord.ui import Button, View

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
MY_GUILD = discord.Object(id=694409795968434266) # remove later

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        # Prefix is still needed for some internal bot functions
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """This runs when the bot starts, before it connects."""
        self.tree.copy_global_to(guild=MY_GUILD) # remove this line when switching from testing to global
        await self.tree.sync(guild=MY_GUILD) # remove guild=MY_GUILD for same reasoning as above
        print(f"Synced slash commands to guild {MY_GUILD.id}")

bot = MyBot()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.tree.command(name="ping", description="Check the bot's latency")
async def ping(interaction: discord.Interaction):
    """Slash command version of ping."""
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Latency: {latency}ms")

@bot.tree.command(name="ask", description="Ask the FTC AI a question")
@app_commands.describe(question="What do you want to know about FTC teams?")
async def ask(interaction: discord.Interaction, question: str):
    """Placeholder for your RAG logic."""
    # 'defer' the response because AI can take more than 3 seconds to think
    await interaction.response.defer() 
    await interaction.followup.send(f"Temp")

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: No DISCORD_TOKEN found in .env file.")