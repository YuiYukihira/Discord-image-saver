from aioauth_client import GoogleClient
from discord.ext import commands
from aiohttp import web
import aiohttp
import asyncio

users = {}
watching = {}
upload_queue = asyncio.Queue()

bot = commands.Bot(command_prefix="!")
google = GoogleClient(
    client_id="",
    client_secret="",
    redirect_uri="http://127.0.0.1:8080/callback",
)
run = True


async def upload():
    while run:
        a = await upload_queue.get()
        upload_tokens = []
        print(a)
        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {a['bearer']}"}
        ) as session:
            for pic in a['pictures']:
                async with session.post(
                    "https://photoslibrary.googleapis.com/v1/uploads",
                    data=await pic["attachment"].read(),
                    headers={
                        "Content-type": "application/octect-stream",
                        "X-Goog-Upload-File-Name": pic["attachment"].filename,
                        "X-Goog-Upload-Protocol": "raw",
                    },
                ) as resp:
                    print(resp.status)
                    if resp.status == 200:
                        upload_tokens.append(
                            {"desc": pic['description'], "token": await resp.text()}
                        )
            if len(upload_tokens) > 0:
                async with session.post(
                    "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate",
                    json={
                        "newMediaItems": [
                            {
                                "description": t['desc'],
                                "simpleMediaItem": {"uploadToken": t['token']},
                            }
                            for t in upload_tokens
                        ]
                    },
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    print(resp.status)
                    if resp.status == 200:
                        print("success")
                    if resp.status == 400:
                        print(await resp.text())


app = web.Application()


async def start_bot(app):
    asyncio.create_task(
        bot.start("")
    )
    asyncio.create_task(upload())


async def stop_bot(app):
    global run
    run = False
    await bot.close()


@bot.command()
async def login(ctx):
    id = ctx.author.id
    authorize_url = google.get_authorize_url(
        scope="https://www.googleapis.com/auth/photoslibrary.appendonly", state=str(id)
    )
    await ctx.author.send(f"Login with google here: {authorize_url}")


@bot.command()
async def watch(ctx, user: commands.UserConverter):
    print(user.id)
    if not watching.get(ctx.channel.id):
        watching[ctx.channel.id] = {}
    if not watching.get(ctx.channel.id).get(ctx.author.id):
        watching[ctx.channel.id][user.id] = []
    watching[ctx.channel.id][user.id].append(ctx.author.id)
    print(watching)
    await ctx.send(f'I\'m watching {user} for images in this channel to upload to {ctx.author}\'s google photos i')


@bot.event
async def on_message(message):
    channel = watching.get(message.channel.id)
    if channel:
        u = channel.get(message.author.id)
        if u:
            for code in users:
                if code:
                    if message.content and len(message.attachments) == 1:
                        await upload_queue.put(
                            {
                                "bearer": users[code],
                                "pictures": [
                                    {
                                        "description": message.content,
                                        "attachment": message.attachments[0],
                                    }
                                ],
                            }
                        )
                    else:
                        await upload_queue.put(
                            {
                                "bearer": code,
                                "pictures": [
                                    {"description": a.filename, "attachment": a}
                                    for a in message.attachments
                                ],
                            }
                        )
    await bot.process_commands(message)


async def callback(request):
    id = request.query.get("state")
    code = request.query.get("code")
    print(code)
    try:
        otoken, _ = await google.get_access_token(code)
    except web.HTTPBadRequest as e:
        print(f"whoops {str(e)}, {e.reason}")
    else:
        print(otoken)
        users[id] = otoken
        return web.Response(text=str(otoken))
    return web.Response(text="none")


async def check(request):
    return web.Response(text=str(users))


app.on_startup.append(start_bot)
app.on_shutdown.append(stop_bot)
app.add_routes([web.get("/callback", callback), web.get("/check", check)])
web.run_app(app)
