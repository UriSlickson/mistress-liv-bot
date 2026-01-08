# Standings Extraction Approach

## Challenge
The MyMadden website uses Vue.js components that render data client-side. The raw HTML from aiohttp doesn't contain the actual standings data.

## Solution
Since the Discord bot can't run a headless browser, we'll use a different approach:

### Option 1: Use the #scores channel as the trigger
When the Super Bowl game is posted to #scores, the bot can:
1. Detect it's a Super Bowl game
2. Prompt an admin to run `/importseedings` 
3. The admin command will use the current season's final standings

### Option 2: Store team-to-user mappings
Since we already have team registrations in the bot, we can:
1. Map team abbreviations to Discord users via the registration system
2. When importing seedings, just need the team order (which can be parsed from #scores over time)

### Option 3: Manual trigger with auto-fetch
Create a command `/importseedings [year]` that:
1. Uses Playwright/Selenium to fetch the rendered page
2. Extracts the standings data
3. Auto-populates the seedings

## Recommended Approach
For simplicity, we'll implement:
1. `/importseedings [year]` - Admin command that fetches standings from MyMadden
2. Uses the existing team-to-user registration mapping
3. Automatically sets all seedings for both conferences

## Team ID Mapping (from MyMadden logo URLs)
```
1: bears, 2: bengals, 3: bills, 4: broncos,
5: browns, 6: buccaneers, 7: cardinals, 8: chargers,
9: chiefs, 10: colts, 11: commanders, 12: cowboys,
13: dolphins, 14: eagles, 15: falcons, 16: giants,
17: jaguars, 18: jets, 19: lions, 20: packers,
21: panthers, 22: patriots, 23: raiders, 24: rams,
25: ravens, 26: saints, 27: seahawks, 28: steelers,
29: texans, 30: titans, 31: 49ers, 32: vikings
```
