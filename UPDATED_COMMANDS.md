# Mistress LIV Bot - Complete Command List (Updated)

**Last Updated:** January 7, 2026

---

## 📊 GENERAL COMMANDS (Everyone)

| Command | Description |
|---------|-------------|
| `/help` | Get help with bot commands |
| `/ping` | Check bot latency |
| `/serverinfo` | Get server information |

---

## 📝 REGISTRATION COMMANDS

| Command | Description |
|---------|-------------|
| `/register` | Register yourself as a team owner |
| `/unregister` | Unregister from team owner announcements |
| `/whoregistered` | [Admin] See all registered team owners |
| `/registerall` | [Admin] Prompt all team owners to register |
| `/registeruser @user` | [Admin] Register a user as team owner |
| `/bulkregister` | [Admin] Register multiple users |

---

## 💰 PAYMENT & DUES COMMANDS (NEW!)

### User Commands
| Command | Description |
|---------|-------------|
| `/whooowesme` | See who owes YOU money |
| `/whoiowe` | See who YOU owe money to |
| `/mypayments` | View your complete payment summary (owed vs incoming) |
| `/markpaid @debtor amount` | Mark a payment as paid (admin or creditor) |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/paymentschedule [season]` | Post all outstanding payments to #dues |
| `/createpayment @debtor @creditor amount reason` | Create a new payment obligation |
| `/clearpayment @debtor @creditor amount` | Delete a specific payment |

---

## 📈 PROFITABILITY COMMANDS

### User Commands
| Command | Description |
|---------|-------------|
| `/profitability [season]` | View franchise profitability rankings |
| `/myprofit` | View your personal profitability breakdown |
| `/topearners [season]` | Leaderboard of top earners |
| `/toplosers [season]` | Leaderboard of biggest losers |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/viewseasondata [season]` | View all data for a specific season |
| `/showpayers [season]` | Show who owes money (NFC seeds 8-16) |
| `/setseeding season conference seed @user` | Set NFC/AFC seeding for a season |
| `/setplayoffwinner season round @winner` | Record a playoff round winner |
| `/generatepayments [season]` | Generate payment obligations from standings |
| `/clearpayments [season]` | Clear all payments for a season |
| `/postpayments [season]` | Post payment summaries to channels |
| `/testpayments [season]` | Test view of payment data |
| `/autopopulate [season]` | Auto-populate season data from MyMadden |

---

## 😭 WHINER TRACKER (NEW!)

| Command | Description |
|---------|-------------|
| `/whiner [timeframe]` | See who complains the most (all time, month, week, day) |
| `/mywhines` | See your own complaint stats |
| `/resetwhiner [@user]` | [Admin] Reset complaint stats |

**How it works:** The bot automatically monitors messages for complaint keywords (rigged, bs, unfair, trash, etc.) and tracks who complains the most. The more you whine, the higher your score!

---

## 📢 ANNOUNCEMENT COMMANDS (Admin)

| Command | Description |
|---------|-------------|
| `/announcement` | Post announcement + DM team owners |
| `/announce` | Post announcement to channels |
| `/dmowners` | Send DM to all registered owners |

---

## 🎨 ADMIN/UTILITY COMMANDS

| Command | Description |
|---------|-------------|
| `/synchelmet @user` | Add helmet emoji to nickname |
| `/syncallhelmets` | Add helmets to all registered owners |
| `/removehelmet @user` | Remove helmet from nickname |
| `/setuproles` | Create team roles with colors |
| `/createfinances` | Create finances channel |

---

## 🎰 WAGER COMMANDS (Coming Soon)

| Command | Description |
|---------|-------------|
| `/wager @opponent amount` | Create a wager |
| `/mywagers` | View active wagers |
| `/wagerboard` | Wager leaderboard |
| `/markwagerpaid` | Mark a wager as paid |

---

## Summary

| Category | Count |
|----------|-------|
| **General Commands** | 3 |
| **Registration Commands** | 6 |
| **Payment Commands** | 7 |
| **Profitability Commands** | 13 |
| **Whiner Commands** | 3 |
| **Announcement Commands** | 3 |
| **Admin/Utility Commands** | 5 |
| **Wager Commands (Placeholder)** | 4 |
| **TOTAL** | 44 |

---

## Quick Reference for #commands Channel

```
**MISTRESS LIV BOT COMMANDS**

💰 **Payments**
/whooowesme - See who owes you
/whoiowe - See who you owe
/mypayments - Your payment summary
/markpaid @user amount - Mark as paid

📈 **Profitability**
/profitability - League rankings
/myprofit - Your earnings
/topearners - Top earners leaderboard
/toplosers - Biggest losers leaderboard

😭 **Whiner Tracker**
/whiner - Who complains the most
/mywhines - Your complaint stats

📋 **Info**
/help - All commands
/serverinfo - Server info
```
