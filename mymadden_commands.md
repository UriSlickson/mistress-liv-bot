# MyMadden Bot Commands Reference

Source: https://mymadden.com/bot-commands

## Basic Commands (use / prefix)

| Command | Description |
|---------|-------------|
| `/hello` | Posts "Hello, World!" |
| `/help` | Posts a link to the help page |
| `/web` | Posts the link to the league website |
| `/trades` | Posts the link to the league trades |
| `/schedule` | Posts the link to the schedule |
| `/standings` | Posts the link to the league standings |
| `/stats` | Posts the link to the league stats |
| `/players` | Posts the link to the league players search |
| `/injuries` | Posts the link to the league injuries table |
| `/teams` | Posts the link to the league teams |
| `/week` | Posts the current year, stage, and week |

## Team Commands

| Command | Description |
|---------|-------------|
| `/team {team}` | Posts the link to the specified team |
| `/owner {team}` | Posts the owner listed on the console and on the site |

*{team} can be the team's city/state, nickname, or abbreviation*

## Game Commands

| Command | Description |
|---------|-------------|
| `/games` | Posts the games for the current week |
| `/unplayed` | Posts the unplayed games for the current week |
| `/played` | Posts the played games for the current week |
| `/tws {team} [week]` | Posts the game specified by the team and week |

*tws = team week score*

## Player Search

| Command | Description |
|---------|-------------|
| `/ps [args]` | Player search with various filters |

**Args can include:**
- Team city, name, or abbreviation
- Player name (first, last, or both)
- `r`, `rookie`, or `rookies` for rookies only
- Position or position groups

**Position Groups:**
- RB → HB, FB
- SKILL → HB, TE, WR
- OL → LT, LG, C, RG, RT
- DL → LE, DT, RE
- LB → LOLB, MLB, ROLB
- DB → CB, FS, SS

## Trade Block

| Command | Description |
|---------|-------------|
| `/tblock [args]` | Posts trade block results (same args as ps) |

## Blog

| Command | Description |
|---------|-------------|
| `/blog [number]` | Posts the link to the blog and recent posts |

## Social Media Commands

These require connecting your profile with Discord on MyMadden.

| Command | Description |
|---------|-------------|
| `/whois me` or `/whois @user` | Shows MyMadden username, league status, and team |
| `/twitch me` or `/twitch @user` | Shows Twitch link |
| `/youtube me` or `/youtube @user` | Shows YouTube link |
| `/psn me` or `/psn @user` | Shows PSN username |
| `/xbox me` or `/xbox @user` | Shows Xbox Live username |
| `/steam me` or `/steam @user` | Shows Steam username and link |
| `/facebook me` or `/facebook @user` | Shows Facebook link |
| `/twitter me` or `/twitter @user` | Shows Twitter link |

## Sync Commands

| Command | Description |
|---------|-------------|
| `/sync` | Trigger a data sync from the console to MyMadden |
