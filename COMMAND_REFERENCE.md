# Mistress LIV Bot - Command Reference

**Last Updated:** January 18, 2026  
**Total Commands:** 51 (8 command groups + 43 standalone)

---

## Data Source Priority

All commands that fetch external data follow this priority:
1. **Snallabot API** (Primary) - `https://snallabot.me`
2. **MyMadden Website** (Fallback) - `https://mymadden.com/lg/liv`

---

## Command Groups (Subcommands)

### `/admin` - Server Administration
| Subcommand | Description | Data Source |
|------------|-------------|-------------|
| `/admin setup roles` | Create team roles with proper colors | Discord API |
| `/admin setup payouts` | Create the payouts channel | Discord API |

### `/announce` - Announcements
| Subcommand | Description | Data Source |
|------------|-------------|-------------|
| `/announce all <message>` | Post to #townsquare, #announcements, AND DM all members | Discord API |
| `/announce post <message>` | Post to #townsquare and #announcements only | Discord API |
| `/announce dm <message>` | DM all league members only | Discord API |

### `/bestball` - Best Ball Fantasy Football
| Subcommand | Description | Data Source |
|------------|-------------|-------------|
| `/bestball start <name> <fee>` | Create a new Best Ball event | Database |
| `/bestball join <event>` | Join a Best Ball event | Database |
| `/bestball roster` | View your roster | Database |
| `/bestball add <player>` | Add a player to your roster | **Snallabot** (player data) |
| `/bestball remove <player>` | Remove a player from your roster | Database |
| `/bestball status` | Check event standings | Database |
| `/bestball rules` | View Best Ball rules | Static |
| `/bestball close` | [Admin] Close event and start scoring | Database |
| `/bestball end` | [Admin] End event and generate payments | Database |
| `/bestball cancel` | [Admin] Cancel a Best Ball event | Database |

### `/league` - League Configuration
| Subcommand | Description | Data Source |
|------------|-------------|-------------|
| `/league setup <name> <id> <platform>` | Set up league configuration | Database |
| `/league add <name> <id> <platform>` | Add another league | Database |
| `/league switch <league>` | Switch active league | Database |
| `/league list` | List all leagues | Database |
| `/league info` | Show current league info | Database |
| `/league season <year>` | Set current season | Database |
| `/league remove <league>` | [Admin] Remove a league | Database |
| `/league channels` | [Admin] Set notification channels | Database |

### `/payments` - Payment Tracking
| Subcommand | Description | Data Source |
|------------|-------------|-------------|
| `/payments owedtome` | See who owes you money | Database |
| `/payments iowe` | See who you owe money to | Database |
| `/payments status` | View your complete payment status | Database |
| `/payments schedule` | View all outstanding payments | Database |
| `/payments create` | [Admin] Create a payment obligation | Database |
| `/payments paid @user` | Mark a payment as paid | Database |
| `/payments clear` | [Admin] Delete a specific payment | Database |

### `/leaderboard` - Earnings Leaderboards
| Subcommand | Description | Data Source |
|------------|-------------|-------------|
| `/leaderboard earners` | View the top earners leaderboard | Database |
| `/leaderboard losers` | View the biggest losers leaderboard | Database |

### `/playoff` - Playoff Management
| Subcommand | Description | Data Source |
|------------|-------------|-------------|
| `/playoff winner <season> <round> @user` | Record a playoff round winner | Database |
| `/playoff generate <season>` | Generate all payment obligations | Database |
| `/playoff pairings <season>` | View AFC/NFC seed pairings | Database |
| `/playoff clear <season> <type>` | Clear payment/playoff/season data | Database |
| `/playoff post <season>` | Post payment summaries to channels | Database |

### `/profit` - Profitability Stats
| Subcommand | Description | Data Source |
|------------|-------------|-------------|
| `/profit view [season]` | View league-wide profitability rankings | Database |
| `/profit mine` | View your personal profitability | Database |
| `/profit structure` | View the complete payout structure | Static |

---

## Standalone Commands

### Wagers
| Command | Description | Data Source |
|---------|-------------|-------------|
| `/wager @opponent <amount> <week> <team1> <team2> <pick>` | Create a wager on any game | **Snallabot** (schedule validation) |
| `/acceptwager <wager_id>` | Accept a pending wager | Database |
| `/declinewager <wager_id>` | Decline a pending wager | Database |
| `/cancelwager <wager_id>` | Cancel your own pending wager | Database |
| `/mywagers` | View your active wagers | Database |
| `/wagerwin <wager_id>` | Claim victory on a wager | Database |
| `/paid` | Mark a wager as paid | Database |
| `/wagerboard` | View the wager leaderboard | Database |
| `/unpaidwagers` | View your unpaid wagers | Database |

### Auto Settlement
| Command | Description | Data Source |
|---------|-------------|-------------|
| `/forcecheckwagers` | Force check all pending wagers | **Snallabot** → MyMadden |
| `/settlewager <wager_id> <winner>` | Manually settle a wager | Database |
| `/checkscore <week>` | Check scores for a week | **Snallabot** → MyMadden |
| `/parsescore <text>` | Parse a score from text | Local parsing |
| `/allunpaidwagers` | [Admin] View all unpaid wagers | Database |

### Snallabot Integration
| Command | Description | Data Source |
|---------|-------------|-------------|
| `/setsnallabotconfig <league_id> <platform> <season>` | [Admin] Configure Snallabot | Database |
| `/snallabottest` | Test Snallabot API connection | **Snallabot** |
| `/checkplayoffs` | Check Snallabot for playoff results | **Snallabot** |
| `/viewplayoffresults <season>` | View recorded playoff results | Database |

### Seeding & Playoffs
| Command | Description | Data Source |
|---------|-------------|-------------|
| `/autoplayoffs <season> AUTOPAY` | [Admin] Auto-import standings & generate payments | **Snallabot** → Madden Export |
| `/bulkseeding <season> <conf> <seedings>` | [Admin] Bulk set seedings | Database |
| `/viewseedings <season>` | View current seedings | Database |
| `/checkexportapi` | Check data source status | **Snallabot** + Madden Export |

### Registration
| Command | Description | Data Source |
|---------|-------------|-------------|
| `/register` | Register as a team owner | Database |
| `/unregister` | Unregister from team owner | Database |
| `/whoregistered` | [Admin] See all registered owners | Database |
| `/registerall` | [Admin] Prompt all to register | Database |
| `/registeruser @user` | [Admin] Register a user | Database |
| `/bulkregister @users` | [Admin] Register multiple users | Database |

### Welcher System
| Command | Description | Data Source |
|---------|-------------|-------------|
| `/welcher @user <reason>` | [Admin] Ban a user from wagering | Database |
| `/checkwelcher @user` | Check if user is a welcher | Database |
| `/listwelchers` | List current welchers | Database |

### League Info
| Command | Description | Data Source |
|---------|-------------|-------------|
| `/rules` | View the league rules | Static |
| `/dynamics` | View league dynamics/settings | Static |
| `/requirements` | View league requirements | Static |
| `/payouts` | View the payout structure | Static |

### Utility
| Command | Description | Data Source |
|---------|-------------|-------------|
| `/clearchannel <channel> CONFIRM` | Clear a selected channel | Discord API |
| `/checkreminders` | Check pending payment reminders | Database |
| `/postguide` | Post the command guide | Static |

---

## Background Automations

| Task | Frequency | Data Source | Description |
|------|-----------|-------------|-------------|
| `check_pending_wagers` | Every 30 min | **Snallabot** → MyMadden | Auto-settles completed wagers |
| `check_playoff_results` | Every 1 hour | **Snallabot** | Checks for playoff game results |
| `daily_channel_reminder` | Every 24 hours | Database | Posts payment reminders to #payouts |
| `dm_reminder_check` | Every 12 hours | Database | DMs users with overdue payments |

---

## Initial Setup Commands

Before using the bot, run these setup commands in order:

1. `/setsnallabotconfig <league_id> <platform> <season>` - Configure Snallabot API connection
2. `/league setup <name> <id> <platform>` - Set up your league
3. `/league season <year>` - Set the current season year (e.g., 2028)
4. `/admin setup roles` - Create team roles
5. `/admin setup payouts` - Create payouts channel

---

## Troubleshooting

### Wagers not auto-settling?
1. Run `/snallabottest` - Verify Snallabot connection is working
2. Run `/league info` - Verify correct season is set (e.g., 2028 not 2026)
3. Run `/forcecheckwagers` - Manually trigger settlement check
4. Check that the game has actually been played on Snallabot

### No earnings showing?
1. Wagers must be **settled** (winner recorded) before earnings appear
2. Run `/mywagers` to see if wagers show "WON" or "LOST" status
3. If still "Active", the game hasn't been settled yet - run `/forcecheckwagers`

### Commands not appearing?
- The bot has 51 commands total (under Discord's 100 limit)
- Some commands require Admin permissions
- Try restarting Discord or waiting a few minutes for slash commands to sync

### DMs not being sent?
- Users must have DMs enabled from server members
- Check that users have team roles assigned (e.g., "49ers", "SF", "San Francisco")

---

## Migration Notes (Old → New Commands)

| Old Command | New Command |
|-------------|-------------|
| `/setupleague` | `/league setup` |
| `/addleague` | `/league add` |
| `/switchleague` | `/league switch` |
| `/setseason` | `/league season` |
| `/setuproles` | `/admin setup roles` |
| `/createpayouts` | `/admin setup payouts` |
| `/setplayoffwinner` | `/playoff winner` |
| `/generatepayments` | `/playoff generate` |
| `/profitability` | `/profit view` |
| `/myprofit` | `/profit mine` |
| `/bestballstart` | `/bestball start` |
| `/owedtome` | `/payments owedtome` |
| `/announcement` | `/announce post` |
| `/dmowners` | `/announce dm` |
