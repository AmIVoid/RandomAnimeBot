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


async def fetch_planning_list(username):
    query = """
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
    """
    variables = {"userName": username}
    url = "https://graphql.anilist.co"
    response = requests.post(url, json={"query": query, "variables": variables})
    if response.status_code == 200:
        data = response.json()
        # Flatten the list of lists of entries into a single list of entries
        entries = []
        for list in data["data"]["MediaListCollection"]["lists"]:
            entries.extend(list["entries"])
        return [entry["media"] for entry in entries]
    else:
        print(f"Error fetching data: HTTP {response.status_code}")
        return []


async def fetch_trending_anime():
    query = """
    query {
        Page(perPage: 50) {
            media(isAdult: false, sort: TRENDING_DESC, type: ANIME) {
                id
                title {
                    userPreferred
                }
                siteUrl
            }
        }
    }
    """
    url = "https://graphql.anilist.co"
    response = requests.post(url, json={"query": query})
    if response.status_code == 200:
        data = response.json()
        return data["data"]["Page"]["media"]
    else:
        print(f"Error fetching data: HTTP {response.status_code}")
        return []


async def fetch_all_time_popular_anime():
    query = """
    query {
        Page(perPage: 50) {
            media(isAdult: false, sort: POPULARITY_DESC, type: ANIME) {  # Adjusted for popularity
                id
                title {
                    userPreferred
                }
                siteUrl
                averageScore
            }
        }
    }
    """
    url = "https://graphql.anilist.co"
    response = requests.post(url, json={"query": query})
    if response.status_code == 200:
        data = response.json()
        return data["data"]["Page"]["media"]
    else:
        print(f"Error fetching data: HTTP {response.status_code}")
        return []


async def fetch_user_anime_list(username):
    query = """
    query ($userName: String) {
        MediaListCollection(userName: $userName, type: ANIME) {
            lists {
                entries {
                    media {
                        id
                    }
                }
            }
        }
    }
    """
    variables = {
        "userName": username,
    }
    url = "https://graphql.anilist.co"
    response = requests.post(url, json={"query": query, "variables": variables})
    if response.status_code == 200:
        data = response.json()
        user_anime_ids = [
            entry["media"]["id"]
            for list in data["data"]["MediaListCollection"]["lists"]
            for entry in list["entries"]
        ]
        return set(user_anime_ids)
    else:
        print(f"Error fetching user's anime list: HTTP {response.status_code}")
        return set()


# Connect to the SQLite database (this will create the database file if it doesn't exist)
conn = sqlite3.connect("user_data.db")
cursor = conn.cursor()

# Create the users table
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    anilist_username TEXT NOT NULL
)"""
)
conn.commit()


def set_user_anilist_username(user_id, username):
    cursor.execute(
        """
    INSERT INTO users(user_id, anilist_username) VALUES(?, ?)
    ON CONFLICT(user_id) DO UPDATE SET anilist_username=excluded.anilist_username
    """,
        (user_id, username),
    )
    conn.commit()


def get_user_anilist_username(user_id):
    cursor.execute("SELECT anilist_username FROM users WHERE user_id = ?", (user_id,))
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
    await interaction.response.send_message(
        f"Your AniList username has been set to: {username}", ephemeral=True
    )


@bot.tree.command(
    name="recommend", description="Recommend an anime based on your preference"
)
@app_commands.describe(
    username="AniList Username (optional)",
    recommendation_type="The type of recommendation: 'planning', 'trending', or 'popular'",
)
@app_commands.choices(
    recommendation_type=[
        app_commands.Choice(name="planning", value="planning"),
        app_commands.Choice(name="trending", value="trending"),
        app_commands.Choice(name="popular", value="popular"),
    ]
)
async def recommend(
    interaction: discord.Interaction,
    recommendation_type: app_commands.Choice[str],
    username: str = None,
):
    user_id = interaction.user.id

    if username is None:
        username = get_user_anilist_username(user_id)
        if username is None:
            await interaction.response.send_message(
                "Please set your AniList username using /setusername command.",
                ephemeral=True,
            )
            return

    if recommendation_type.value == "planning":
        anime_list = await fetch_planning_list(username)
    elif recommendation_type.value == "trending":
        anime_list = await fetch_trending_anime()
    elif recommendation_type.value == "popular":
        anime_list = await fetch_all_time_popular_anime()

    # Shuffle list for randomness if the type is either 'trending' or 'popular'
    if recommendation_type.value in ["trending", "popular"]:
        random.shuffle(anime_list)

    if anime_list:
        user_anime_ids = (
            await fetch_user_anime_list(username)
            if recommendation_type.value in ["trending", "popular"]
            else set()
        )
        filtered_anime_list = [
            anime for anime in anime_list if anime["id"] not in user_anime_ids
        ]

        if filtered_anime_list:
            anime = random.choice(filtered_anime_list)
            title = anime["title"]["userPreferred"]
            anime_id = anime["id"]
            url = anime["siteUrl"]
            response_message = (
                f"Recommendation ({recommendation_type.value}): {title} - {url}"
            )

            button_url = f"https://anilist.co/anime/{anime_id}"
            button = Button(
                label="Watch Now",
                url=button_url,
                style=discord.ButtonStyle.link,
                emoji="📺",
            )
            view = View()
            view.add_item(button)
            await interaction.response.send_message(response_message, view=view)
        else:
            await interaction.response.send_message(
                f"No anime found in the {recommendation_type.value} category or all have been watched."
            )
    else:
        await interaction.response.send_message(
            f"No anime found in the {recommendation_type.value} category."
        )


@atexit.register
def cleanup():
    conn.close()


@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")
    await bot.tree.sync()


bot.run("BOT_TOKEN")
