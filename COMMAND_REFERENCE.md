# Mistress LIV Bot - Command Reference

## Command Count Summary
- **Total Top-Level Commands:** 57 (well under Discord's 100 limit)
- **Command Groups:** 8
- **Standalone Commands:** 49

---

## Command Groups (Subcommands)

### `/admin` - Administrative Commands
| Subcommand | Description |
|------------|-------------|
| `/admin setup roles` | Create team roles with proper colors |
| `/admin setup payouts` | Create the payouts channel |

### `/announce` - Announcement Commands
| Subcommand | Description |
|------------|-------------|
| `/announce post <message>` | Post announcement to channels, optionally DM owners |
| `/announce dm <message>` | Send a DM to all team owners |
| `/announce clear <channel>` | Delete all messages in a channel |
| `/announce commands` | Post the command list to a channel |

### `/bestball` - Best Ball Fantasy Football
| Subcommand | Description |
|------------|-------------|
| `/bestball start <name> <fee>` | Create a new Best Ball event |
| `/bestball join <event>` | Join a Best Ball event |
| `/bestball roster` | View your roster and what positions you need |
| `/bestball add <player>` | Add a player to your roster |
| `/bestball remove <player>` | Remove a player from your roster |
| `/bestball status` | Check event standings and leaderboard |
| `/bestball rules` | View Best Ball rules and scoring |
| `/bestball close` | [Admin] Close event and start scoring |
| `/bestball end` | [Admin] End event and generate payments |
| `/bestball cancel` | [Admin] Cancel a Best Ball event |

### `/league` - League Configuration
| Subcommand | Description |
|------------|-------------|
| `/league setup <name> <id> <platform>` | Set up or update league configuration |
| `/league add <name> <id> <platform>` | Add another league to this server |
| `/league switch <league>` | Switch the active league |
| `/league list` | List all leagues for this server |
| `/league info` | Show current league configuration |
| `/league season <year>` | Set the current season |
| `/league remove <league>` | [Admin] Remove a league |
| `/league channels` | [Admin] Set notification channels |

### `/payments` - Payment Tracking
| Subcommand | Description |
|------------|-------------|
| `/payments owedtome` | See who owes you money |
| `/payments iowe` | See who you owe money to |
| `/payments status` | View your complete payment status |
| `/payments schedule` | View all outstanding payments |
| `/payments create` | [Admin] Create a payment obligation |
| `/payments paid @user` | Mark a payment as paid |
| `/payments clear` | [Admin] Delete a specific payment |

### `/leaderboard` - Leaderboards
| Subcommand | Description |
|------------|-------------|
| `/leaderboard earners` | View the top earners leaderboard |
| `/leaderboard losers` | View the biggest losers leaderboard |

### `/playoff` - Playoff Management (Admin)
| Subcommand | Description |
|------------|-------------|
| `/playoff seeding <season> <conf> <seed> @user` | Set NFC/AFC seeding |
| `/playoff winner <season> <round> @user` | Record a playoff round winner |
| `/playoff generate <season>` | Generate all payment obligations |
| `/playoff pairings <season>` | View AFC/NFC seed pairings |
| `/playoff clear <season> <type>` | Clear payment/playoff/season data |
| `/playoff post <season>` | Post payment summaries to channels |

### `/profit` - Profitability Viewing
| Subcommand | Description |
|------------|-------------|
| `/profit view [season]` | View league-wide profitability rankings |
| `/profit mine` | View your personal profitability |
| `/profit structure` | View the complete payout structure |

---

## Standalone Commands

### Wagers
| Command | Description |
|---------|-------------|
| `/wager @opponent <amount>` | Create a wager for your game |
| `/acceptwager <wager_id>` | Accept a pending wager |
| `/declinewager <wager_id>` | Decline a pending wager |
| `/cancelwager <wager_id>` | Cancel your own pending wager |
| `/wagerwin <wager_id>` | Settle a wager (declare winner) |
| `/paid <wager_id>` | Confirm payment received |
| `/mywagers` | View your active wagers |
| `/wagerboard` | View the wager leaderboard |
| `/pendingwagers` | View all pending wagers |
| `/unpaidwagers` | View all unpaid wagers |

### Registration
| Command | Description |
|---------|-------------|
| `/register` | Register yourself as a team owner |
| `/registeruser @user <team>` | [Admin] Register a user to a team |
| `/registerall` | [Admin] Prompt all unregistered owners |
| `/unregister @user` | [Admin] Unregister a user |
| `/whoregistered` | View all registered team owners |
| `/bulkregister` | [Admin] Bulk register multiple users |

### League Info
| Command | Description |
|---------|-------------|
| `/rules` | View league rules |
| `/dynamics` | View league dynamics |
| `/requirements` | View member requirements |
| `/payouts` | View payout structure |

### Welcher System
| Command | Description |
|---------|-------------|
| `/welcher @user <reason>` | [Admin] Ban a user from wagers/payouts |
| `/redeemed @user` | [Admin] Remove welcher status |
| `/welcherlist` | View all current welchers |
| `/checkwelcher @user` | Check if a user is a welcher |

### Utility
| Command | Description |
|---------|-------------|
| `/help` | Get help with bot commands |
| `/ping` | Check bot latency |
| `/serverinfo` | Get server information |
| `/postguide` | Post the command guide |

### Auto Settlement
| Command | Description |
|---------|-------------|
| `/checkscore <week>` | Check scores for a specific week |
| `/settlewager <wager_id>` | Manually settle a wager |
| `/forcecheckwagers` | Force check all pending wagers |
| `/parsescore <text>` | Parse a score from text |
| `/allunpaidwagers` | View all unpaid wagers |

### Snallabot Integration
| Command | Description |
|---------|-------------|
| `/setsnallabotconfig` | [Admin] Configure Snallabot integration |
| `/snallabottest` | Test Snallabot API connection |
| `/scanteams` | Scan and update team data |
| `/checkexportapi` | Check export API status |

### Seeding & Playoffs
| Command | Description |
|---------|-------------|
| `/autoplayoffs` | [Admin] Auto-generate playoff seeding |
| `/viewseedings <season>` | View current seedings |
| `/viewplayoffresults <season>` | View playoff results |
| `/importseedings` | [Admin] Import seedings from API |
| `/importstandings` | [Admin] Import standings from API |
| `/bulkseeding` | [Admin] Bulk set seedings |
| `/generateplayoffpayments` | [Admin] Generate playoff payments |
| `/checkplayoffs` | Check playoff status |

### Whiner System
| Command | Description |
|---------|-------------|
| `/whiner @user <reason>` | Report a whiner |
| `/mywhines` | View your whine history |
| `/resetwhiner @user` | [Admin] Reset whiner status |

### Payment Reminders
| Command | Description |
|---------|-------------|
| `/checkreminders` | Check pending payment reminders |
| `/forcecheckwagers` | Force check all pending wagers |

---

## Migration Notes

### Old Commands → New Commands

| Old Command | New Command |
|-------------|-------------|
| `/setupleague` | `/league setup` |
| `/addleague` | `/league add` |
| `/switchleague` | `/league switch` |
| `/listleagues` | `/league list` |
| `/leagueinfo` | `/league info` |
| `/setseason` | `/league season` |
| `/removeleague` | `/league remove` |
| `/setchannels` | `/league channels` |
| `/setuproles` | `/admin setup roles` |
| `/createpayouts` | `/admin setup payouts` |
| `/setseeding` | `/playoff seeding` |
| `/setplayoffwinner` | `/playoff winner` |
| `/generatepayments` | `/playoff generate` |
| `/viewpairings` | `/playoff pairings` |
| `/clearpayments` | `/playoff clear` |
| `/clearplayoffresults` | `/playoff clear` |
| `/clearseason` | `/playoff clear` |
| `/postpayments` | `/playoff post` |
| `/profitability` | `/profit view` |
| `/myprofit` | `/profit mine` |
| `/payoutstructure` | `/profit structure` |
| `/bestballstart` | `/bestball start` |
| `/bestballjoin` | `/bestball join` |
| `/bestballroster` | `/bestball roster` |
| `/bestballadd` | `/bestball add` |
| `/bestballremove` | `/bestball remove` |
| `/bestballstatus` | `/bestball status` |
| `/bestballrules` | `/bestball rules` |
| `/owedtome` | `/payments owedtome` |
| `/iowe` | `/payments iowe` |
| `/paymentstatus` | `/payments status` |
| `/announcement` | `/announce post` |
| `/dmowners` | `/announce dm` |
| `/clearchannel` | `/announce clear` |
