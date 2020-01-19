from aioauth_client import GoogleClient
from discord.ext import tasks, commands
import discord
from aiohttp import web
import aiohttp
import asyncio
from dataclasses import dataclass, field

from typing import Optional, List


class Token:
    def __init__(
        self,
        token: str,
        refresh_token: str,
        expires_in: str,
        oauth_client: GoogleClient,
        loop=None,
    ):
        self.token = token
        self.refresh_token = refresh_token
        self.expires_in = expires_in
        self.client = oauth_client
        self.time_left = self.expires_in

        self.__run = True
        self.loop = loop if loop else asyncio.get_event_loop()

        self.t = asyncio.Task(self.run(), loop=self.loop)

    def __repr__(self):
        return f"<Token token={self.token} refresh_token={self.refresh_token} expires_in={self.expires_in} time_left={self.time_left}>"

    def __str__(self):
        return self.token

    async def stop(self):
        self.__run = False
        await self.t

    async def run(self):
        while self.__run:
            await asyncio.sleep(1)
            self.time_left -= 1
            if self.time_left <= self.expires_in * 0.1:

                self.token, meta = await self.client.get_access_token(
                    self.refresh_token, loop=self.loop, grant_type="refresh_token"
                )
                if meta.get("refresh_token"):
                    self.refresh_token = meta.get("refresh_token")
                if meta.get("expires_in"):
                    self.expires_in = meta.get("expires_in")
                self.time_left = self.expires_in

    def save(self):
        return {
            "token": self.token,
            "refresh_token": self.refresh_token,
            "expires_in": self.expires_in,
        }

    @classmethod
    def load(cls, json, auth_client, loop=None):
        loop = loop if loop else asyncio.get_event_loop()
        return cls(json["token"], json["refresh_token"], 0, auth_client, loop)


@dataclass
class Picture:
    description: Optional[str]
    attachment: discord.Attachment


@dataclass
class Upload:
    bot: commands.Bot
    pictures: List[Picture]
    message: discord.Message
    bearer: Token
    user: discord.User
    logging: bool

    __embed: Optional[discord.Embed] = field(init=False)
    __message: Optional[discord.Message] = field(init=False)

    async def log(self):
        if self.logging:
            self.__embed = (
                discord.Embed(title=f"channel: {self.message.channel} -> {self.user}")
                .set_image(url=self.pictures[0].attachment.url)
                .add_field(name="status", value=f"❓ - Uploading")
            )
            self.__message = await self.bot.get_user(self.bot.owner_id).send(
                embed=self.__embed
            )
        await self.message.add_reaction("❓")

    async def log2(self, msg):
        await self.bot.get_user(self.bot.owner_id).send(msg)

    async def update1(self, response):
        if response.status != 200:
            await self.message.add_reaction("🚫")
            if self.logging:
                if not self.__embed:
                    self.__embed = (
                        discord.Embed(
                            title=f"channel: {self.message.channel} -> {self.user}"
                        )
                        .set_image(url=self.pictures[0].attachment.url)
                        .add_field(name="status", value=f"❓")
                    )
                self.__embed.set_field_at(
                    0, name="status", value="🚫 - Could not upload images to google"
                ).add_field(
                    name="details1",
                    value=f"{response.status} {response.reason}: {await response.text()}",
                )
                if not self.__message:
                    self.__message = await self.bot.get_user(self.bot.owner_id).send(
                        embed=self.__embed
                    )
                else:
                    await self.__message.edit(embed=self.__embed)

    async def update2(self, response):
        await self.message.remove_reaction("❓", self.bot.user)
        if response.status == 200 or response.status == 407:
            emoji, m = (
                ("✔️", "All saved successfully")
                if response.status == 200
                else ("➖", "Some saved successfully")
            )
            await self.message.add_reaction(emoji)
            if self.logging:
                if not self.__embed:
                    self.__embed = (
                        discord.Embed(
                            title=f"channel: {self.message.channel} -> {self.user}"
                        )
                        .set_image(url=self.pictures[0].attachment.url)
                        .add_field(name="status", value=f"❓")
                    )
                self.__embed = self.__embed.set_field_at(
                    0, name="status", value=f"{emoji} - {m}"
                )
        else:
            await self.message.add_reaction("❌")
            if self.logging:
                if not self.__embed:
                    self.__embed = (
                        discord.Embed(
                            title=f"channel: {self.message.channel} -> {self.user}"
                        )
                        .set_image(url=self.pictures[0].attachment.url)
                        .add_field(name="status", value=f"❓")
                    )
                self.__embed = self.__embed.set_field_at(
                    0, name="status", value=f"❌ - Unsuccessful"
                ).add_field(name="details2", value=f"{await response.text()}")
        if not self.__message:
            self.__message = await self.bot.get_user(self.bot.owner_id).send(
                embed=self.__embed
            )
        else:
            await self.__message.edit(embed=self.__embed)


class ImageSaverCog(commands.Cog, name="Image saver cog"):
    def __init__(
        self,
        bot,
        client_id,
        client_secret,
        aiohttp_address,
        callback_address,
        port,
        loop=None,
        users=None,
        watching=None,
    ):
        self.loop = loop if loop else asyncio.get_event_loop()
        self.bot = bot
        self.google = GoogleClient(
            client_id=client_id, client_secret=client_secret, redirect_uri=f'http://{callback_address}:{port}/callback'
        )
        self.users = (
            self.load_users(users, self.google, loop=self.loop) if users else {}
        )
        self.watching = self.load_watching(watching) if watching else {}
        self.upload_queue = asyncio.Queue()
        app = web.Application()
        app.add_routes([web.get("/callback", self.callback)])
        self.upload.start()
        self.runner = web.AppRunner(app)
        self.loop.run_until_complete(self.runner.setup())
        site = web.TCPSite(self.runner, aiohttp_address, 8080)
        self.web_task = asyncio.Task(site.start(), loop=loop)
        self.loggingOn = False

    @staticmethod
    def load_users(json, auth_client, loop=None):
        loop = loop if loop else asyncio.get_event_loop()
        return {
            int(user): Token.load(token, auth_client, loop)
            for user, token in json.items()
        }

    @staticmethod
    def load_watching(json):
        return {
            int(channel): {
                int(author_id): user_id for author_id, user_id in users.items()
            }
            for channel, users in json.items()
        }

    def cog_unload(self):
        self.upload.cancel()
        self.loop.run_until_complete(self._stop())

    async def _stop(self):
        await self.runner.cleanup()
        await self.web_task
        self.save()

    def save(self):
        users = {u: t.save() for u, t in self.users.items()}
        with open("users.json", "w") as f:
            json.dump(users, f)
        with open("watching.json", "w") as f:
            json.dump(self.watching, f)

    @tasks.loop()
    async def upload(self):
        u = await self.upload_queue.get()
        upload_tokens = []
        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {str(u.bearer)}"}
        ) as session:
            for pic in u.pictures:
                async with session.post(
                    "https://photoslibrary.googleapis.com/v1/uploads",
                    data=await pic.attachment.read(),
                    headers={
                        "Content-Type": "application/octect-stream",
                        "X-Goog-Upload-File-Name": pic.attachment.filename,
                        "X-Goog-Upload-Protocol": "raw",
                    },
                ) as resp:
                    await u.update1(resp)
                    if resp.status == 200:
                        upload_tokens.append(
                            {"description": pic.description, "token": await resp.text()}
                        )
            if len(upload_tokens) > 0:
                async with session.post(
                    "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate",
                    json={
                        "newMediaItems": [
                            {
                                "description": t["description"],
                                "simpleMediaItem": {"uploadToken": t["token"]},
                            }
                            for t in upload_tokens
                        ]
                    },
                ) as resp:
                    await u.update2(resp)

    @commands.Command
    async def login(self, ctx):
        id = ctx.author.id
        authorize_url = self.google.get_authorize_url(
            scope="https://www.googleapis.com/auth/photoslibrary.appendonly",
            state=str(id),
            access_type="offline",
        )
        await ctx.author.send(f"Login with google here: {authorize_url}")

    @commands.Command
    async def watch(self, ctx, user: commands.UserConverter):
        channel_id = int(ctx.channel.id)
        user_id = int(user.id)
        author_id = int(ctx.author.id)
        if not self.watching.get(channel_id):
            self.watching[channel_id] = {}
        if not self.watching.get(channel_id).get(user_id):
            self.watching[channel_id][user_id] = []
        if not author_id in self.watching.get(channel_id).get(user_id):
            self.watching[channel_id][user_id].append(author_id)
        await ctx.send(
            f"I'm watching {user} for images in this channel to upload to {ctx.author}'s google photos library'"
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        # are we watching this channel?
        if message.author != self.bot.user:
            channel = self.watching.get(message.channel.id)
            if channel:
                # are we watching any users in this channel?
                users = channel.get(message.author.id, [])
                # upload for all users we're watching for.
                for user_id in users:
                    if user_id in self.users.keys():
                        # Message has title + 1 picture
                        if message.content and len(message.attachments) == 1:
                            upload = Upload(
                                self.bot,
                                [Picture(message.content, message.attachments[0])],
                                message,
                                self.users[user_id],
                                self.bot.get_user(user_id),
                                self.loggingOn,
                            )
                            await self.upload_queue.put(upload)
                            await upload.log()
                        elif len(message.attachments) > 0:
                            upload = Upload(
                                self.bot,
                                [Picture(a.filename, a) for a in message.attachments],
                                message,
                                self.users[user_id],
                                self.bot.get_user(user_id),
                                self.loggingOn,
                            )
                            await self.upload_queue.put(upload)
                            await upload.log()

    @commands.command()
    @commands.is_owner()
    async def stop(self, ctx):
        await self.bot.logout()

    @commands.command()
    @commands.is_owner()
    async def check(self, ctx):
        await ctx.author.send(f"users: {self.users}")
        await ctx.author.send(f"watching: {self.watching}")

    @commands.group()
    @commands.is_owner()
    async def logging(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.author.send("Invalid logging command")

    @logging.command()
    async def on(self, ctx):
        self.loggingOn = True
        await ctx.author.send("Logging turned on")

    @logging.command()
    async def off(self, ctx):
        self.loggingOn = False
        await ctx.author.send("Logging turned off")

    async def callback(self, request):
        user_id = request.query.get("state")
        code = request.query.get("code")
        otoken, meta = await self.google.get_access_token(code)
        self.users[int(user_id)] = Token(
            otoken,
            meta.get("refresh_token"),
            meta.get("expires_in"),
            self.google,
            loop=self.loop,
        )
        return web.Response(
            text="Thank you, you can now close this tab and go back to discord"
        )


if __name__ == "__main__":
    import json

    loop = asyncio.get_event_loop()

    config = json.load(open("/config.json", "r"))
    try:
        users = json.load(open(config["users_file"], "r"))
    except FileNotFoundError:
        users = None
    try:
        watching = json.load(open(config["watching_file"], "r"))
    except FileNotFoundError:
        watching = None
    bot = commands.Bot(command_prefix="!")
    bot.add_cog(
        ImageSaverCog(
            bot,
            config["client_id"],
            config["client_secret"],
            config["aiohttp_address"],
            config["callback_address"],
            config["port"],
            loop=loop,
            users=users,
            watching=watching,
        )
    )
    bot.run(config["discord_token"])
