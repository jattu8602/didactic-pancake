# Contributing to Colleges API

First off, thank you for considering contributing to the Colleges API! It's people like you that make open source tools great.

## How Can I Contribute?

### 1. Reporting Bugs
If you find a bug in the source code or a mistake in the documentation, you can help us by submitting an issue to our GitHub Repository. Even better, you can submit a Pull Request with a fix.

### 2. Suggesting Enhancements
If you want to see a new feature, feel free to open an issue. Please describe the feature you would like to see, why you need it, and how it should work.

### 3. Contributing Data (Scraping)
The database relies on accurate information. If you'd like to help scrape new districts or fix outdated contact info:
1. Refer to `scraper/README.md` to see how the scraper works.
2. Ensure you add any new data to `public/data/colleges.json` by running `combine.py`.
3. Submit a Pull Request with the updated JSON file and raw CSV files.

### 4. Improving Code & UI
We welcome improvements to:
- The Go backend API (Fiber)
- The frontend UI dashboard (`public/browse.html`)
- The scraper python script (`scraper.py`)

## Pull Request Process
1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation (`public/index.html` and `README.md`).
4. Ensure the test suite passes (if any).
5. Submit your Pull Request!

## Local Development Setup
1. **API / Backend:**
   - Install Go (1.18+)
   - Run `go build -o server . && ./server`
2. **Scraper:**
   - Install Python 3.8+
   - Run `pip install -r scraper/requirements.txt`
   - Run `playwright install chromium`
