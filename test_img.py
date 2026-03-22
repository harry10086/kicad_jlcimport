import urllib.request
import re

url = 'https://item.szlcsc.com/421842.html'
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9'
})
html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
match = re.search(r'https://(?:alimg\.szlcsc\.com/upload/public/product/source)/[^\s"<>]+(?:\.jpg|\.png)', html)
img_url = match.group(0)

# Fetch without webp accept
req2 = urllib.request.Request(img_url, headers={
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'image/jpeg,image/png,image/*,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': url
})
data = urllib.request.urlopen(req2).read()
print('Header without webp:', data[:16])
