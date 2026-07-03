# College Contact Scraper

This directory contains a complete scraping system designed to automatically find and extract phone numbers, email addresses, and website links for colleges in India.

This document provides a **detailed, easy-to-understand guide** covering everything you need to know to run the scraper and the website.

---

## 🛠️ How to Install Things

Before you can run the scraper, you need to install the required tools.

**Requirements:**
- Python 3.8 or higher installed on your computer.
- A terminal or command prompt.

**Installation Steps:**
1. Open your terminal and navigate to the `scraper` folder:
   ```bash
   cd scraper
   ```
2. Install the necessary Python libraries:
   ```bash
   pip install -r requirements.txt
   ```
3. Install Playwright (the browser engine used for scraping):
   ```bash
   playwright install chromium
   ```

---

## 🚀 How to Run the Scraper for Any State and Any District

The scraper reads from a main CSV file (e.g., `mp_colleges.csv` or `colleges.csv`) and allows you to scrape data for specific regions.

**1. See available districts for a state:**
```bash
python3 scraper.py --csv ../data/mp_colleges.csv --state "Madhya Pradesh" list
```

**2. Scrape a specific district in a state:**
```bash
python3 scraper.py --csv ../data/mp_colleges.csv --state "Madhya Pradesh" "Bhopal"
```

**3. Scrape across all states (if you omit `--state`):**
```bash
python3 scraper.py --csv ../data/all_colleges.csv "Chennai"
```

**4. Check your overall scraping progress:**
```bash
python3 scraper.py summary
```

**5. Combine your scraped data:**
Once you've scraped your desired districts, merge the newly found data into a final JSON file for the website to use:
```bash
python3 combine.py
```

---

## 🧠 How This Works (The Basics)

The scraper uses **Playwright** to open a real background browser. By acting like a real human, it bypasses basic bot-detection.

1. **Search:** It searches Google for the college name (e.g., `"Govt. College Bhopal official website"`).
2. **Visit:** It clicks the best official link (preferring `.ac.in`, `.gov.in`).
3. **Extract:** It reads the webpage text and uses rules (Regular Expressions) to find phone numbers and emails.
4. **Backup Plan:** If the homepage fails, it checks pages like `/contact` or tries to guess the website URL.
5. **Save:** It saves the data to a district CSV file and pauses to avoid being detected by Google.

### Refresh Time Estimation
Scraping isn't instantaneous because we must wait between searches to avoid getting blocked.
* **1-10 colleges:** ~2 to 5 minutes
* **10-50 colleges:** ~10 to 45 minutes
* **200+ colleges:** ~3 to 6 hours
*(Each college takes roughly 20-30 seconds total, including the random delay).*

---

## 🛡️ IP Blocking and Proxies Explained

**What is IP Blocking?**
Google hates automated bots. If you search too fast, Google will show a CAPTCHA or block your IP address (your internet connection's ID), causing the scraper to fail.

**How we prevent it:**
- **Stealth Code:** We hide browser flags that shout "I am a robot".
- **Random Delays:** The script pauses for 5-10 seconds between every search.

### How to Bypass IP Blocking & Proxies

If you get blocked, you have a few options to bypass it:

1. **Wait it out (Easiest):** Just wait 1-2 hours and Google will usually unblock you.
2. **Increase Delays:** Open `scraper.py` and change `SEARCH_DELAY_S = (5, 10)` to something higher, like `(15, 25)`.
3. **Use a Proxy:** A proxy is a server that hides your real IP address and replaces it with a different one. 
   - To use one, open `scraper.py` and find where the browser is launched. Add your proxy details like this:
     ```python
     context = browser.new_context(
         proxy={"server": "http://your-proxy-ip:port"},
         ...
     )
     ```
   - *Note: For serious scraping, you can buy "Residential Proxies" which rotate your IP automatically so you never get blocked.*

---

## 💻 How to Modify Code to Scrape More Data

If you want to extract additional information (like social media links or addresses), you can easily modify `scraper.py`.

1. Open `scraper.py` and find the `visit_and_scrape()` function.
2. Add your new extraction rules. For example, to scrape the page title and address:

```python
# After page loads...
text = page.inner_text("body")
college_name = page.title()           # gets the page title
address = page.inner_text("address")  # gets the <address> element (if it exists)

# Add it to your output down in the main loop:
out = {
    **row,
    "website": contact["website"],
    "phone_numbers": "; ".join(contact["phones"]),
    "emails": "; ".join(contact["emails"]),
    "page_title": college_name,
}
```

---

## 🌐 How to Run the Website (and Export Features)

This project includes a built-in user interface to browse your scraped data.

### Starting the Server
1. Open your terminal and go to the **root folder** of the project (one folder up from `scraper`).
   ```bash
   cd ..
   ```
2. Build and run the Go server:
   ```bash
   go build -o server . && ./server
   ```
3. Open your web browser and go to: `http://localhost:3000/browse.html`

### Website Features
The website provides a powerful dashboard to view your data, including:
* **District-wise Filtering:** Quickly view colleges for a specific district.
* **State-wise Filtering:** Filter colleges by state.
* **Complete Export as CSV:** A button to export all (or currently filtered) data to a standard CSV format.
* **Complete Export as Excel:** A built-in feature to download the data as a neatly formatted Microsoft Excel (`.xlsx` or `.xls`) file.
