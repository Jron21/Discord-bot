import os
import random
import asyncio
import logging
import re

import discord
from dotenv import load_dotenv
from discord.ext import commands

load_dotenv()


# ============================================================
# Configuration
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("Sora10Chan")


# ============================================================
# Existing bot data
# ============================================================

ASUKA_IMAGES = [
    'https://i.pinimg.com/originals/e4/66/6a/e4666af369f09d81cdebf7111bc428f6.gif',
    'https://i.pinimg.com/originals/5d/81/34/5d81345ab238484837d263bb47eb681d.gif',
    'https://i.pinimg.com/originals/14/37/a4/1437a4af80a3d551b38dc929d31a569e.gif',
    'https://i.pinimg.com/originals/76/f6/ab/76f6abc1f0684bd222500bfd8e0f0a4a.gif',
    'https://i.pinimg.com/originals/e1/24/b6/e124b632cd2d9cc00b8aa7e2c6d0dfa1.gif',
    'https://i.pinimg.com/originals/0b/e2/ec/0be2ec18244adef461b269c25c5b1a15.gif',
]

DOOR_IMAGES = [
    'https://media.discordapp.net/attachments/794492424713797642/955809260342759485/IMG_20220322_203535.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955808883836862484/IMG_20220322_203725.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809260137226270/IMG_20220322_203635.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809260544098344/IMG_20220322_203412.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809260783165510/IMG_20220322_203350.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809261001273394/IMG_20220322_203301.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809261206773831/IMG_20220322_203230.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809261437468712/IMG_20220322_203118.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955810094258483230/unknown-1.png',
    'https://media.discordapp.net/attachments/794492424713797642/955810094615003226/Screenshot_2022-02-28-01-11-57-81_572064f74bd5f9fa804b05334aa4f912.png',
    'https://media.discordapp.net/attachments/794492424713797642/955811133988667424/IMG_20220318_231533.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955811853026590740/Screenshot_2022-03-15-13-48-40-29_be80aec1db9a2b53c9d399db0c602181.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955811853248917514/IMG_20220307_195827.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955812010564673656/IMG_20220225_160006.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955812789463703562/IMG_20220205_214056.jpg',
]

RESPONSES = {
    'nice': 'https://media.discordapp.net/attachments/950636380902535178/954749647748988978/ikuchan_thumbs_up_2.gif',
    'wtf': 'https://media.discordapp.net/attachments/950636380902535178/954720092711686194/AmusedLittleDamselfly-size_restricted_1.gif',
    'night': 'https://media.discordapp.net/attachments/950636380902535178/954720173573672991/tumblr_m7u7pn8lnr1rol1m7o5_250_1.gif',
    'sorry': 'https://tenor.com/view/idol-sakamichi-nogizaka46-gomen-gomennasai-gif-15222467',
    'morning': 'https://tenor.com/view/kaki-haruka-kakki-nogizaka46-gif-22485470',
    'see': 'https://giant.gfycat.com/DaringEveryIsabellinewheatear.mp4',
}

SEMBATSU_ENTRIES = [
    {
        'number': 1,
        'title': 'Guruguru Curtain',
        'announced': '2012-01-08',
        'onSale': '2012-02-22',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956072832595550298/1.jpg',
    },
    {
        'number': 2,
        'title': 'Oide Shampoo',
        'announced': '2012-03-18',
        'onSale': '2012-05-22',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956073027068624906/2.jpg',
    },
    {
        'number': 3,
        'title': 'Hashire! Bicycle',
        'announced': '2012-06-17',
        'onSale': '2012-08-22',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956073151375233034/3.jpg',
    },
    {
        'number': 4,
        'title': 'Seifuku No Mannequin',
        'announced': '2012-10-07',
        'onSale': '2012-12-19',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956073425930162176/4.jpg',
    },
    {
        'number': 5,
        'title': 'Kimi No Na Wa Kibou',
        'announced': '2013-01-06',
        'onSale': '2013-03-13',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956073508838985778/5.jpg',
    },
    {
        'number': 6,
        'title': "Girl's Rule",
        'announced': 'at 5th Single National Handshake Event, 2013-04-20',
        'onSale': '2013-07-03',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956115367158235156/6.jpg',
    },
    {
        'number': 7,
        'title': 'Barette',
        'announced': '2013-10-06',
        'onSale': '2013-11-27',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956115441296736266/7.jpg',
    },
    {
        'number': 8,
        'title': 'Kizuitara Kataomoi',
        'announced': '2014-01-26',
        'onSale': '2014-04-02',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956115555117563914/8.jpg',
    },
    {
        'number': 9,
        'title': 'Natsu No Free & Easy',
        'announced': '2014-05-11',
        'onSale': '2014-07-09',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956115655327883274/9.jpg',
    },
    {
        'number': 10,
        'title': 'Nandome No Aozora Ka?',
        'announced': '2014-08-03',
        'onSale': '2014-10-08',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956115727788691506/10.jpg',
    },
    {
        'number': 11,
        'title': 'Inochi Wa Utsukushii',
        'announced': '2015-01-18',
        'onSale': '2015-03-18',
    },
    {
        'number': 12,
        'title': 'Taiyou Knock',
        'announced': '2015-05-10',
        'onSale': '2015-07-22',
    },
    {
        'number': 13,
        'title': 'Ima, Hanashitai Dareka Ga Iru',
        'announced': '2015-08-30',
        'onSale': '2015-10-28',
    },
    {
        'number': 14,
        'title': 'Harujion Ga Sakukoro',
        'announced': '2016-01-31',
        'onSale': '2016-03-23',
    },
    {
        'number': 15,
        'title': 'Hadashi De Summer',
        'announced': '2016-06-05',
        'onSale': '2016-07-27',
    },
    {
        'number': 16,
        'title': 'Sayonara No Imi',
        'announced': '2016-10-16',
        'onSale': '2016-11-09',
    },
    {
        'number': 17,
        'title': 'Influencer',
        'announced': '2017-01-29',
        'onSale': '2017-03-22',
    },
    {
        'number': 18,
        'title': 'Nigemizu',
        'announced': '2017-07-09',
        'onSale': '2017-08-09',
    },
    {
        'number': 19,
        'title': 'Ituka Dekiru Nara Kyou Dekiru',
        'announced': '2017-09-03',
        'onSale': '2017-10-11',
    },
    {
        'number': 20,
        'title': 'Synchronicity',
        'announced': '2018-03-11',
        'onSale': '2018-04-25',
    },
    {
        'number': 21,
        'title': 'Single 21',
        'announced': 'Not provided in the original source',
        'onSale': 'Not provided in the original source',
    },
    {
        'number': 22,
        'title': 'Single 22',
        'announced': 'Not provided in the original source',
        'onSale': 'Not provided in the original source',
    },
]

# ============================================================
# Discord setup
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# guild_id -> voice channel_id
target_voice_channels: dict[int, int] = {}

# guild_id -> asyncio.Task
voice_reconnect_tasks: dict[int, asyncio.Task] = {}


def random_item(items):
    return random.choice(items)


async def send_message(message: discord.Message, content: str) -> None:
    await message.channel.send(content)


# ============================================================
# Voice connection handling
# ============================================================

def schedule_voice_reconnect(guild_id: int, channel_id: int) -> None:
    """Schedule one reconnect attempt after five seconds."""
    if target_voice_channels.get(guild_id) != channel_id:
        return

    existing = voice_reconnect_tasks.get(guild_id)
    if existing is not None and not existing.done():
        return

    async def retry() -> None:
        try:
            await asyncio.sleep(5)
            voice_reconnect_tasks.pop(guild_id, None)
            await reconnect_voice(guild_id, channel_id)
        except asyncio.CancelledError:
            voice_reconnect_tasks.pop(guild_id, None)
            raise
        except Exception as error:
            voice_reconnect_tasks.pop(guild_id, None)
            logger.warning(
                "Sora10Chan voice reconnect attempt encountered an error: %s",
                error,
            )
            schedule_voice_reconnect(guild_id, channel_id)

    voice_reconnect_tasks[guild_id] = asyncio.create_task(retry())


async def reconnect_voice(guild_id: int, channel_id: int) -> None:
    if target_voice_channels.get(guild_id) != channel_id:
        return

    guild = bot.get_guild(guild_id)
    if guild is None:
        return

    channel = guild.get_channel(channel_id)

    if channel is None:
        try:
            channel = await guild.fetch_channel(channel_id)
        except discord.DiscordException:
            target_voice_channels.pop(guild_id, None)
            logger.warning(
                "Sora10Chan stopped voice recovery because the target "
                "channel no longer exists: guild=%s channel=%s",
                guild_id,
                channel_id,
            )
            return

    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        target_voice_channels.pop(guild_id, None)
        logger.warning(
            "Sora10Chan stopped voice recovery because the target "
            "channel is no longer a voice channel: guild=%s channel=%s",
            guild_id,
            channel_id,
        )
        return

    existing = guild.voice_client

    if existing is not None:
        if existing.is_connected():
            return
        try:
            await existing.disconnect(force=True)
        except discord.DiscordException:
            pass

    try:
        await channel.connect(self_deaf=True)
        logger.info(
            "Sora10Chan is connected to the voice channel: guild=%s channel=%s",
            guild_id,
            channel_id,
        )
    except Exception as error:
        logger.warning(
            "Sora10Chan voice recovery attempt failed: guild=%s channel=%s error=%s",
            guild_id,
            channel_id,
            error,
        )
        schedule_voice_reconnect(guild_id, channel_id)


# ============================================================
# Bot events
# ============================================================

@bot.event
async def on_ready():
    logger.info(
        "Sora10Chan is online as %s in %d guild(s)",
        bot.user,
        len(bot.guilds),
    )

    try:
        synced = await bot.tree.sync()
        logger.info(
            "Registered %d slash command(s): %s",
            len(synced),
            ", ".join(command.name for command in synced),
        )
    except Exception:
        logger.exception("Discord slash command registration failed")


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
    # Only react to changes involving the bot itself.
    if bot.user is None or member.id != bot.user.id:
        return

    guild_id = member.guild.id
    channel_id = target_voice_channels.get(guild_id)

    if channel_id is None:
        return

    if after.channel is None or after.channel.id != channel_id:
        schedule_voice_reconnect(guild_id, channel_id)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    command = message.content.strip().lower()
    username = message.author.name

    if command == "*ashu":
        await send_message(message, random_item(ASUKA_IMAGES))
        return

    if command == "door":
        await send_message(message, random_item(DOOR_IMAGES))
        return

    direct_responses = {
        "nice": RESPONSES["nice"],
        "wtf": RESPONSES["wtf"],
        "sorry": RESPONSES["sorry"],
        "gomen": RESPONSES["sorry"],
        "i see": RESPONSES["see"],
    }

    direct_response = direct_responses.get(command)
    if direct_response:
        await send_message(message, direct_response)
        return

    if command in ("good morning", "ohayou"):
        await send_message(message, "おはよう！")
        await send_message(message, RESPONSES["morning"])
        return

    if command in ("good night", "oyasumi"):
        await send_message(message, "おやすみ！")
        await send_message(message, RESPONSES["night"])
        return

    if command == "sad":
        await send_message(message, "sad link")
        return

    sembatsu_match = re.fullmatch(r"\*sembatsu\s+(\d{1,2})", command)

    if sembatsu_match:
        number = int(sembatsu_match.group(1))
        entry = next(
            (item for item in SEMBATSU_ENTRIES if item["number"] == number),
            None,
        )

        if entry is None:
            await send_message(
                message,
                "Sembatsu entries are available from 1 through 22.",
            )
            return

        await send_message(
            message,
            f'{entry["number"]}th Single: {entry["title"]}, '
            f'Sembatsu Announced {entry["announced"]}, '
            f'On Sale {entry["onSale"]}',
        )

        if entry.get("image"):
            await send_message(message, entry["image"])
        elif entry["number"] >= 21:
            await send_message(message, "LOL")
            await send_message(
                message,
                "The original source did not include an image link for this entry.",
            )
        else:
            await send_message(
                message,
                "The original source did not include an image link for this entry.",
            )
        return

    # Preserve the original behavior: hello/bye only work in #bot.
    if isinstance(message.channel, discord.TextChannel):
        if message.channel.name == "bot" and command == "hello":
            await send_message(message, f"hello {username}")
        elif message.channel.name == "bot" and command == "bye":
            await send_message(message, f"bye {username}")


# ============================================================
# Slash commands
# ============================================================

@bot.tree.command(
    name="ping",
    description="Check whether Sora10Chan is responding",
)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Pong! WebSocket latency: {round(bot.latency * 1000)}ms"
    )


@bot.tree.command(
    name="test",
    description="Run a quick Sora10Chan test",
)
async def test(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Sora10Chan slash commands are working!"
    )


@bot.tree.command(
    name="join",
    description="Join your current voice channel",
)
async def join(interaction: discord.Interaction):
    await interaction.response.defer()

    if interaction.guild is None:
        await interaction.followup.send(
            "This command can only be used inside a server."
        )
        return

    member = interaction.guild.get_member(interaction.user.id)

    if member is None:
        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except discord.DiscordException:
            await interaction.followup.send(
                "I couldn't find your member information."
            )
            return

    voice_channel = member.voice.channel

    if voice_channel is None:
        await interaction.followup.send(
            "Join a voice channel first, then use `/join` again."
        )
        return

    if not isinstance(
        voice_channel,
        (discord.VoiceChannel, discord.StageChannel),
    ):
        await interaction.followup.send(
            "I couldn't connect to that voice channel."
        )
        return

    guild_id = interaction.guild.id
    channel_id = voice_channel.id

    target_voice_channels[guild_id] = channel_id

    existing = interaction.guild.voice_client

    try:
        if existing is not None:
            if existing.channel and existing.channel.id == channel_id:
                await interaction.followup.send(
                    f"Already in <#{channel_id}>."
                )
                return

            await existing.move_to(voice_channel)
        else:
            await voice_channel.connect(self_deaf=True)

        logger.info(
            "Sora10Chan joined voice channel: guild=%s channel=%s",
            guild_id,
            channel_id,
        )

        await interaction.followup.send(f"Joined <#{channel_id}>.")

    except Exception as error:
        target_voice_channels.pop(guild_id, None)
        logger.warning(
            "Sora10Chan could not join the requested voice channel: %s",
            error,
        )

        await interaction.followup.send(
            "I couldn't connect to that voice channel. "
            "Please check that I have the Connect permission "
            "and that the channel is not full."
        )


@bot.tree.command(
    name="leave",
    description="Leave the current voice channel",
)
async def leave(interaction: discord.Interaction):
    await interaction.response.defer()

    if interaction.guild is None:
        await interaction.followup.send(
            "This command can only be used inside a server."
        )
        return

    guild_id = interaction.guild.id

    target_voice_channels.pop(guild_id, None)

    task = voice_reconnect_tasks.pop(guild_id, None)
    if task is not None and not task.done():
        task.cancel()

    connection = interaction.guild.voice_client

    if connection is None:
        await interaction.followup.send(
            "I am not currently in a voice channel."
        )
        return

    await connection.disconnect()
    await interaction.followup.send("Left the voice channel.")


# ============================================================
# Start
# ============================================================

if __name__ == "__main__":
    if not TOKEN:
        logger.warning(
            "DISCORD_TOKEN is not configured; Discord bot is disabled"
        )
    else:
        try:
            bot.run(TOKEN)
        except Exception:
            logger.exception("Sora10Chan could not connect to Discord")
