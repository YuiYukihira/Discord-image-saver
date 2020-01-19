from aioauth_client import GoogleClient
from discord.ext import tasks, commands
from aiohttp import web
import aiohttp
import asyncio

class ImageSaverCog(commands.Cog, name='Image saver cog'):
    def __init__(self, bot, client_id, client_secret, redirect_uri, loop=None):
        self.loop = loop if loop else asyncio.get_event_loop()
        if not loop:
            self.loop = asyncio.get_event_loop()
        else:
            self.loop = loop
class ImageSaverCog(commands.Cog, name="Image saver cog"):
    def __init__(
        self,
        bot,
        client_id,
        client_secret,
        redirect_uri,
        loop=None,
        users=None,
        watching=None,
    ):
        self.loop = loop if loop else asyncio.get_event_loop()
        self.bot = bot
        self.users = self.load_users(users) if users else {}
        self.watching = self.load_watching(watching) if watching else {}
        self.upload_queue = asyncio.Queue()
        self.google = GoogleClient(
            client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri
        )
        app = web.Application()
        app.add_routes([web.get("/callback", self.callback)])
        self.upload.start()
        self.runner = web.AppRunner(app)
        self.loop.run_until_complete(self.runner.setup())
        site = web.TCPSite(self.runner, "0.0.0.0", 8080)
        self.web_task = asyncio.Task(site.start(), loop=loop)

    @staticmethod
    def load_users(json):
        return {int(user): token for user, token in json.items()}

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
        with open("users.json", "w") as f:
            json.dump(self.users, f)
        with open("watching.json", "w") as f:
            json.dump(self.watching, f)

    @tasks.loop()
    async def upload(self):
        u = await asyncio.wait_for(self.upload_queue.get(), 10)
        upload_tokens = []
        async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {u['bearer']}"}) as session:
            for pic in u['pictures']:
                async with session.post("https://photoslibrary.googleapis.com/v1/uploads",
                    data=await pic["attachment"].read(),
                    headers={
                        "Content-Type": "application/octect-stream",
                        "X-Goog-Upload-File-Name": pic['attachment'].filename,
                        "X-Goog-Upload-Protocol": "raw"
                    }) as resp:
                        if resp.status == 200:
                            upload_tokens.append(
                                {"description": pic['description'], "token": await resp.text()}
                            )
            if len(upload_tokens) > 0:
                async with session.post(
                    "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate",
                    json={
                        "newMediaItems": [
                            {"description": t['description'],
                            "simpleMediaItem": {"uploadToken": t['token']}
                            } for t in upload_tokens
                        ]
                    }
                ) as resp:
                    await u['message'].remove_reaction('❓', self.bot.user)
                    if resp.status == 200:
                        await u['message'].add_reaction('✔️')
                    elif resp.status == 407:
                        await u['message'].add_reaction('➖')
                    else:
                        await u['message'].add_reaction('❌')

    @commands.Command
    async def login(self, ctx):
        id = ctx.author.id
        authorize_url = self.google.get_authorize_url(
            scope="https://www.googleapis.com/auth/photoslibrary.appendonly",
            state=str(id),
        )
        await ctx.author.send(f"Login with google here: {authorize_url}")

    @commands.Command
    async def watch(self, ctx, user: commands.UserConverter):
        if not self.watching.get(ctx.channel.id):
            self.watching[ctx.channel.id] = {}
        if not self.watching.get(ctx.channel.id).get(user.id):
            self.watching[ctx.channel.id][user.id] = []
        if not ctx.author.id in self.watching.get(ctx.channel.id).get(user.id):
            self.watching[ctx.channel.id][user.id].append(ctx.author.id)
        await ctx.send(f"I'm watching {user} for images in this channel to upload to {ctx.author}'s google photos library'")

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
                            await message.add_reaction('❓')
                            await self.upload_queue.put({
                                "bearer": self.users[user_id],
                                "pictures": [{
                                    "description": message.content,
                                    "attachment": message.attachments[0]
                                }],
                                "message": message,
                                "user": self.bot.get_user(user_id)
                            })
                        elif len(message.attachments) > 0:
                            await message.add_reaction('❓')
                            await self.upload_queue.put({
                                "bearer": self.users[user_id],
                                "pictures": [{
                                    "description": a.filename,
                                    "attachment": a
                                } for a in message.attachments],
                                "message": message,
                                "user": self.bot.get_uer(user_id)
                            })
        
    @commands.command()
    @commands.is_owner()
    async def stop(self, ctx):
        await self.bot.logout()

    @commands.command()
    @commands.is_owner()
    async def check(self, ctx):
        await ctx.author.send(f'users: {self.users}')
        await ctx.author.send(f'watching: {self.watching}')

    async def callback(self, request):
        user_id = request.query.get("state")
        code = request.query.get("code")
        otoken, _ = await self.google.get_access_token(code)
        self.users[int(user_id)] = otoken
        return web.Response(
            text="Thank you, you can now close this tab and go back to discord"
        )


if __name__ == "__main__":
    import json

    loop = asyncio.get_event_loop()

    config = json.load(open("config.json", "r"))
    try:
        users = json.load(open("users.json", "r"))
    except FileNotFoundError:
        users = None
    try:
        watching = json.load(open("watching.json", "r"))
    except FileNotFoundError:
        watching = None
    bot = commands.Bot(command_prefix="!")
    bot.add_cog(
        ImageSaverCog(
            bot,
            config["client_id"],
            config["client_secret"],
            config["redirect_uri"],
            loop=loop,
            users=users,
            watching=watching,
        )
    )
    bot.run(config["discord_token"])
