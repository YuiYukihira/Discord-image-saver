# Discord Image Saver

Discord Image saver (DIS) is a small bot that uses oauth2 to save images your google photos library from discord.

## Using

Using DIS is pretty easy all you have to do is follow these 2 steps:

1. Go into any server where a DIS bot is in and run the command: `!login`. The DIS bot should send you a google to [accounts.google.com](accounts.google.com).

2. Go to a channel you want to follow someone in and use the command `!watch` by simply mentioning the person you wish to follow.

Whenever the person you're following sends a message in the channel you sent the watch command from you'll see that the DIS bot reacts. The different reactions signify different states the upload can be in:

- `❓`  - The bot is uploading the image(s) and has not heard back from Google yet.

- `🚫` - The bot was not able to upload the images(s), this is likely caused by an authenication issue, rerun the `!login` and it'll most likely start working again.

- `✔️` - All the images were successfully uploaded.

- `➖` - Some of the images were successfully uploaded.

## Running

Running a DIS bot yourself is pretty easy, you have three main options of how you want to run it:

- As a cog for a larger bot

- As a script

- As a docker container

### Prerequsites

Before you can run the DIS bot you need to create an application with Google, this is pretty simple, just go to the [Google Developers Console](https://console.developers.google.com) and create a new application, you need to enable the Google Photos api. Make sure to add some credentials and an oauth form.

### As a cog for a larger bot

The bot is implemented as a cog so all you should need to do is download the file [src/index.py](src/index.py) import it and add the `ImageSaverCog` cog, it takes a few arguements:

- The bot the cog is on
  
- The client_id of your google application

- The client_secret of you google application

- The domain name/IP address to serve the aiohttp server on

- The domain name/IP address to send users to for the callback (usually the same as your setting for the aiohttp server). This is for the reidrect URI.

- The port to server the aiohttp server on.

Pass those parameters in and the bot should now also be a DIS bot!

### On it's own

This way is probably the simplest, all you have to do is clone this repo to a directory and run the [start](start) script. This script will download everything and ask you for some paramaters to generate the config file if needed. That's it. However this probably the best way, the better way is below.

### As a docker container

A little more complicated to setup but could save you time later. To run with docker you'll need to create image with your config file in it. All you have to do is create a config file called `config.json` it will look like this:

```json
{
    "client_id": "",
    "client_secret": "",
    "aiohttp_address": "",
    "callback_address": "",
    "port": 80,
    "discord_token": "",
    "user_file": "/data/users.json",
    "watching_file": "/data/watching.json"
}
```

From experience the best value to use for `aiohttp_address` would be `0.0.0.0` but don't use this for `callback_address` set that to your public IP/domain name.

Then create a dockerfile for your image in the same place as your config file. The dockerfile should look something like this:

```Dockerfile
FROM yuiyukihira/discord-image-saver:latest
VOLUME /data
COPY config.json /config.json
```

Build this docker file and tag it, then you can create a container using this new image. run the container and your done.

#### Building from source

You can also build the base image from source, just clone the repo and build the [Dockerfile](Dockerfile)
