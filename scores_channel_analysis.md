# Scores Channel Analysis

## Format Observed in #scores Channel

The scores are posted by the **MyMadden** bot (verified app) in a specific format:

### Score Post Format:
```
LIV on MyMadden
[Away Team] [Record] [Away Score] AT [Home Score] [Home Team] [Record]
@[Away Owner] AT @[Home Owner]
[Year] | [Season Type] | [Week]
```

### Example 1 (Playoff Game):
```
LIV on MyMadden
Ravens 11-6-0 35 AT 17 Steelers 11-6-0
@Repenters - 🏆 baltimoreee AT @hi
2027 | Post Season | Divisional
```
- **Away Team:** Ravens (35 points)
- **Home Team:** Steelers (17 points)
- **Winner:** Ravens (higher score)

### Example 2 (Preseason Game):
```
LIV on MyMadden
Chargers 1-2-0 13 AT 6 Commanders
@LAC BOLT UP ⚡ ⚡ ⚡(OG Panthers) AT @Commanders
2028 | Pre Season | Week 1
```
- **Away Team:** Chargers (13 points)
- **Home Team:** Commanders (6 points)
- **Winner:** Chargers (higher score)

### Visual Score Cards:
The bot also posts visual score cards with:
- Team logos
- Final score (e.g., "Ravens 35 - 17 Steelers")
- Top performers for each team
- Season/Week info

## Key Patterns for Parsing:

1. **Score format:** `[Team1] [Score1] AT [Score2] [Team2]`
2. **Owner mentions:** `@[Owner1] AT @[Owner2]`
3. **Game info:** `[Year] | [Season Type] | [Week]`
4. **Winner determination:** Team with higher score wins

## Implementation Notes:

To auto-detect game winners for wager settlement:
1. Monitor #scores channel for MyMadden bot posts
2. Parse the score line to extract teams and scores
3. Determine winner by comparing scores
4. Match against active wagers for that week/matchup
5. Auto-settle wagers based on winner

## MyMadden Bot Details:
- Bot name: "My Madden" (VERIFIED APP)
- Posts are embeds with clickable links
- Contains team records, scores, and owner mentions
