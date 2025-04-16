# Install dependencies

To run this scraper, you need Python 3.8+ and the following packages:

- [playwright](https://pypi.org/project/playwright/)
- [markdownify](https://pypi.org/project/markdownify/)
- [httpx](https://pypi.org/project/httpx/)
- [requests](https://pypi.org/project/requests/)

## 1. Install Python packages

```sh
python3 -m venv venv
source venv/bin/activate
pip install playwright markdownify httpx requests
```

## 2. Install Playwright browsers

```sh
python -m playwright install
```

## 3. Run the scraper

```sh
python test.py
```

## Notes

- The output Markdown files will be saved in the `markdown_out` directory by default.
- You can customize the base URL, paths, and delay in `test.py` or by modifying the script for CLI usage.
