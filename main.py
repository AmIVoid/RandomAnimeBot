import discord
from discord.ui import Button, View
import requests
import random
import sqlite3
import atexit
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)

user_anilist_usernames = {}

async def fetch_planning_list(username, min_score=0):
    query = '''
    query ($userName: String) {
        MediaListCollection(userName: $userName, type: ANIME, status: PLANNING) {
            lists {
                entries {
                    media {
                        id
                        title {
                            userPreferred
                        },
                        siteUrl
                        averageScore
                    }
                }
            }
        }
    }
    '''
    variables = {
        'userName': username,
    }
    url = 'https://graphql.anilist.co'
    response = requests.post(url, json={'query': query, 'variables': variables})
    if response.status_code == 200:
        data = response.json()
        entries = data['data']['MediaListCollection']['lists'][0]['entries']
        # Filter the entries based on the minimum score
        if min_score > 0:
            filtered_entries = [entry for entry in entries if entry['media']['averageScore'] is not None and entry['media']['averageScore'] >= min_score]
            return filtered_entries
        return entries
    else:
        print(f"Error fetching data: HTTP {response.status_code}")
        return []

# Connect to the SQLite database (this will create the database file if it doesn't exist)
conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()

# Create the users table
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    anilist_username TEXT NOT NULL
)''')
conn.commit()

def set_user_anilist_username(user_id, username):
    cursor.execute('''
    INSERT INTO users(user_id, anilist_username) VALUES(?, ?)
    ON CONFLICT(user_id) DO UPDATE SET anilist_username=excluded.anilist_username
    ''', (user_id, username))
    conn.commit()

def get_user_anilist_username(user_id):
    cursor.execute('SELECT anilist_username FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    if row:
        return row[0]
    return None

# Modify your set_username command to use the database
@bot.tree.command(name="setusername", description="Set your AniList username")
@app_commands.describe(username="AniList Username")
async def set_username(interaction: discord.Interaction, username: str):
    user_id = interaction.user.id
    set_user_anilist_username(user_id, username)
    await interaction.response.send_message(f"Your AniList username has been set to: {username}", ephemeral=True)

# Adjust your recommend command to retrieve the username from the database if not provided
@bot.tree.command(name="recommend", description="Recommend an anime from your AniList planning list")
@app_commands.describe(username="AniList Username", score="Minimum score")
async def recommend(interaction: discord.Interaction, username: str = None, score: int = 0):
    user_id = interaction.user.id
    if username is None:
        username = get_user_anilist_username(user_id)
        if username is None:
            await interaction.response.send_message("Please set your AniList username using /setusername command.", ephemeral=True)
            return

    if score < 0 or score > 100:
        await interaction.response.send_message("Score must be between 0 and 100.", ephemeral=True)
        return

    anime_list = await fetch_planning_list(username, score)
    if anime_list:
        anime = random.choice(anime_list)['media']
        title = anime['title']['userPreferred']
        anime_id = anime['id']
        url = anime['siteUrl']
        response_message = f"Here's a recommendation: {title} - {url}"
        
        button_url = f"https://moopa.live/en/anime/{anime_id}"
        button = Button(label="Watch Now", url=button_url, style=discord.ButtonStyle.link, emoji="📺")

        view = View()
        view.add_item(button)
        await interaction.response.send_message(response_message, view=view)
    else:
        response_message = "Couldn't fetch the planning list or it's empty."
        # If there's no view to add, omit the view parameter entirely
        await interaction.response.send_message(response_message)

@atexit.register
def cleanup():
    conn.close()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.tree.sync()

bot.run('BOT_TOKEN')
