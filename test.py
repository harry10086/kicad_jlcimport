import urllib.request
import re

url = 'https://item.szlcsc.com/421842.html'
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9'
})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    all_imgs = re.findall(r'https://[^\"''<>\s]+\.(?:jpg|png|webp)', html)
    for img in set(all_imgs):
        if 'szlcsc' in img or 'lcsc' in img:
            print("IMG:", img)
except Exception as e:
    print(e)
