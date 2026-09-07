# Commands

> Generated from the cogs by `scripts/gen_readme.py`.
> Stays in sync with the bot's own `/help` command automatically.

<!-- COMMANDS:START -->

### Lobbies

| Command | Description |
| --- | --- |
| `/region` | Change your current lobby's voice region |
| `/rename` | Rename your current lobby voice-channel |
| `/resize` | Resize your current lobby |

### Music

| Command | Description |
| --- | --- |
| `/insert` | Add a track to the front of the queue |
| `/loop` | Set the loop mode |
| `/pause` | Pause playback |
| `/play` | Play a track, or add it to the queue |
| `/playing` | Show the track currently playing |
| `/queue` | Show the queue |
| `/resume` | Resume playback |
| `/seek` | Jump to a position in the current track |
| `/shuffle` | Shuffle the queue |
| `/skip` | Skip the current track, or drop tracks from the queue |
| `/stop` | Stop playback, clear the queue and leave |
| `/volume` | Set or view the playback volume |

### Fun

| Command | Description |
| --- | --- |
| `/8ball` | Ask the magic 8-ball a question |
| `/cat` | Fetch a random cat image |
| `/choice` | Chooses randomly from the given options (separated by commas) |
| `/dog` | Fetch a random dog image |

### Utility

| Command | Description |
| --- | --- |
| `/avatar` | Displays the avatar of a user |
| `/help` | Displays the help message with all available commands |
| `/rules` | Displays the server rules |
| `/serverinfo` | Displays server statistics |
| `/settings` | View your personal settings |
| `/stats` | Shows technical information about the bot |
| `/timestamp at` | Generate a timestamp tag for a specific date and time |
| `/timestamp in` | Generate a timestamp tag relative to now |
| `/userinfo` | Displays information about a user |

### Image

| Command | Description |
| --- | --- |
| `/image ace` | Make an Ace Attorney dialogue image |
| `/image billboard` | Put an image on a billboard |
| `/image bonk` | Bonk an image |
| `/image burn` | Set an image on fire |
| `/image cow` | Turn an image into a cow |
| `/image cube` | Spin an image on a cube |
| `/image earthquake` | Shake an image like an earthquake |
| `/image explode` | Blow up an image |
| `/image flag` | Wave an image like a flag |
| `/image flush` | Flush an image down a toilet |
| `/image glitch` | Glitch an image |
| `/image heartlocket` | Put one or two images in a heart locket |
| `/image hearts` | Cover an image in hearts |
| `/image laundry` | Toss an image in the laundry |
| `/image math` | Cover an image in equations |
| `/image matrix` | Turn an image into the Matrix |
| `/image petpet` | Pat an image |
| `/image print` | Print out an image |
| `/image pyramid` | Turn an image into a pyramid |
| `/image rain` | Make it rain with an image |
| `/image sensitive` | Slap a sensitive content warning on an image |
| `/image sphere` | Wrap an image around a spinning globe |
| `/image spin` | Spin an image |
| `/image stereo` | Split an image into a stereo effect |
| `/image stretch` | Stretch an image |

### Administration

| Command | Description |
| --- | --- |
| `/autorole add` | Adds a role to be automatically given to new members |
| `/autorole list` | Lists all currently configured autoroles |
| `/autorole remove` | Removes a role from the autorole list |
| `/embed createjson` | Create an embed using raw JSON |
| `/embed editjson` | Edit an existing embed using raw JSON |
| `/embed json` | Get the JSON source of an embed |
| `/log commands` | Setup or disable the log channel for every command used |
| `/log moderation` | Setup or disable the moderation log channel |
| `/moderation ban` | Bans a user from the server |
| `/moderation clearwarnings` | Clears every warning for a member |
| `/moderation kick` | Kicks a member from the server |
| `/moderation removetimeout` | Removes an active timeout from a member |
| `/moderation timeout` | Times out a member |
| `/moderation unban` | Unbans a user from the server |
| `/moderation warn` | Warns a member |
| `/moderation warnings` | Lists warnings for a member, or every member currently in the server |
| `/serverconfig` | View the server's current bot settings |
| `/set djrole` | Set or reset the role required to control music playback |
| `/set embedcolor` | Set or reset the server's embed color |
| `/set lobbyregion` | Set or reset the voice region new lobbies are created in |
| `/set musicvolume` | Set or reset the volume new players start at |
| `/setup lobbies` | Setup temporary voice-chat system with user-created lobbies |
| `/setup welcome` | Setup or disable the welcome message channel |
| `/test welcome` | Simulate a member joining to test the welcome message |

<!-- COMMANDS:END -->

## Developer commands

Bot-owner-only, `ç!`-prefixed commands ([`cogs/core/developer_tools.py`](../cogs/core/developer_tools.py)),
hidden from `/help` and excluded from the table above. Not part of the generated docs.

| Command | Description |
| --- | --- |
| `ç!reload [cog]` | Reload a specific cog, or all loaded cogs if none is given |
| `ç!load <cog>` | Load a specific cog |
| `ç!unload <cog>` | Unload a specific cog |
| `ç!sync [. \| ^]` | Sync slash commands (globally, to the current guild, or clear guild commands) |
| `ç!devtools` | List all developer commands |
| `ç!deletemessage <id>` | Delete one of the bot's own messages by ID |
| `ç!reloadweb` | Reload the web dashboard without restarting the bot |
