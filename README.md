# Tomato Art Archives Bot

A Bluesky bot that posts tomato-related artwork from various museum collections.

## Museum Sources

### Active Sources
- **MoMA (Museum of Modern Art)** - No API key required (uses web scraping)
- **Whitney Museum of American Art** - No API key required
- **Harvard Art Museums** - Requires free API key
- **Cooper Hewitt Smithsonian Design Museum** - Requires free API key
- **Cleveland Museum of Art** - No API key required
- **The Met** - No API key required (uses web scraping)
- **Library of Congress** - No API key required

### Optional Sources
- **Rijksmuseum** - Requires free API key (optional)

## Setup

1. Install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Create `.env` file with your credentials:
```
BSKY_HANDLE=your-bot-handle.bsky.social
BSKY_APP_PASSWORD=your-app-password
HARVARD_API_KEY=your-harvard-key
COOPER_API_KEY=your-cooper-hewitt-key
RIJKS_API_KEY=your-rijksmuseum-key  # Optional
```

### Getting API Keys

**Harvard Art Museums:** https://harvardartmuseums.org/collections/api
- Free registration to request API key
- Rate limit: 2,500 requests per day
- Non-commercial use only

**Cooper Hewitt:** https://collection.cooperhewitt.org/api/
- Select "read" permission when creating your token
- **Note:** API keys expire periodically - regenerate when needed
- Bot will skip Cooper Hewitt and use other sources if key is expired

**Rijksmuseum (Optional):** https://data.rijksmuseum.nl/
Free registration required.

## Running the Bot

```bash
python tomato_bot.py
```

The bot will:
1. Randomly select a museum source
2. Search for tomato artwork
3. Post to Bluesky with image and metadata
4. Track posted items to avoid duplicates

## Scheduling

To run automatically, set up a cron job or scheduled task:

```bash
# Run daily at 10am
0 10 * * * cd /path/to/tomato-bot && source venv/bin/activate && python tomato_bot.py
```
