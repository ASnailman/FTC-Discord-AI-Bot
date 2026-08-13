# Creating the Discord application and bot

## 1. Create the application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and sign in.
2. **New Application** -> give it a name (e.g. "FTC Scouting Bot") -> Create.

## 2. Configure the bot

1. Open the **Bot** tab.
2. **Reset Token** -> copy the token immediately. It is shown exactly once; if you lose it, reset it again. Paste it into `.env` as `DISCORD_TOKEN`.
3. **Public Bot** -- leave enabled unless you want to be the only one who can invite it.
4. **Privileged Gateway Intents** -- this bot only uses slash commands, so no privileged intents (Message Content, Presence, Server Members) need to be enabled. Leave them off; enabling unneeded intents adds a verification requirement once the bot is in 100+ servers for no benefit here.

## 3. Build the invite URL

1. Open **OAuth2 -> URL Generator**.
2. Under **Scopes**, check both:
   - `bot`
   - `applications.commands`

   Both are required. A URL with only `bot` will let the bot join a server, but its slash commands will never appear -- this is the single most common "why doesn't `/ask` show up" mistake.
3. Under **Bot Permissions**, check:
   - Send Messages
   - Embed Links
   - Read Message History
   - Use Application Commands
   - Attach Files (needed for `/portfolio`'s HTML/Markdown attachments; `/ask` and `/ping` don't need it)
4. Copy the generated URL at the bottom of the page.

Alternatively, build it directly once you have your Application ID (Developer Portal -> General Information) and the permissions integer for the five permissions above (Send Messages `2048` + Embed Links `16384` + Attach Files `32768` + Read Message History `65536` + Use Application Commands `2147483648` = `2147600384`):

```
https://discord.com/api/oauth2/authorize?client_id=<APPLICATION_ID>&permissions=2147600384&scope=bot%20applications.commands
```

## 4. Invite it to a server

Open the URL from step 3 in a browser, pick a server you manage, and authorize.

## 5. Slash command sync: guild vs. global

- **Guild-scoped** (instant): set `DISCORD_GUILD_ID` in `.env` to your server's ID. Right-click your server icon in Discord -> Copy Server ID (requires Developer Mode: User Settings -> Advanced -> Developer Mode). Commands sync to that one server the moment the bot starts.
- **Global** (default, no `DISCORD_GUILD_ID` set): commands sync to every server the bot is in, but can take up to an hour to propagate after each restart. Use this for a production deployment across multiple servers.

## 6. Run the bot

```bash
python src/bot.py
```

You should see `Logged in as <bot name>` and either `Synced slash commands to guild <id> (instant).` or `Synced slash commands globally (may take up to an hour to propagate).`

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `/ask` doesn't appear in Discord | Missing `applications.commands` scope on the invite (step 3), or global sync still propagating (wait up to an hour, or use `DISCORD_GUILD_ID` for instant sync). |
| `401: Unauthorized` / "Improper token" on startup | `DISCORD_TOKEN` is wrong, was reset since you copied it, or has stray whitespace/quotes in `.env`. |
| `Missing Access` when the bot tries to respond | The bot's role in the server lacks Send Messages / Embed Links in that channel. |
| `/portfolio` fails to send its files | The bot's role lacks Attach Files in that channel -- re-invite with the URL in step 3, or grant the permission directly in Server Settings -> Roles. |
| Discord returns `50035` (invalid form body) on a long answer | The reply exceeded Discord's 2000-character single-message limit. `bot.py` already chunks long replies (`_chunk_message`); if you've raised `GEMINI_MAX_TOKENS` further, verify the chunking still fires. |
