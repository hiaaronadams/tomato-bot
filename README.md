# Tomato Art Archives Bot

A Bluesky bot that posts tomato-related artwork from various museum collections.

## Museum Sources

### Active Sources (No API key needed)
- **Cooper Hewitt Smithsonian Design Museum** - Requires free API key
- **Art Institute of Chicago** - No API key required
- **Cleveland Museum of Art** - No API key required
- **The Met** - No API key required (uses web scraping)

### Optional Source
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
COOPER_API_KEY=your-cooper-hewitt-key
RIJKS_API_KEY=your-rijksmuseum-key  # Optional
```

### Getting API Keys

**Cooper Hewitt:** https://collection.cooperhewitt.org/api/
Select "read" permission when creating your token.

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
