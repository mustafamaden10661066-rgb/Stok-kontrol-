"""Apple İstanbul mağazadan teslim stok alarmı. Python 3.11+, requests."""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PART = os.getenv('APPLE_PART_NUMBER', '').strip().upper()
BOT = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
CHAT = os.getenv('TELEGRAM_CHAT_ID', '').strip()
STATE = Path('stock_state.json')
PRODUCT = 'https://www.apple.com/tr/shop/buy-iphone/iphone-18-pro/6.9-in%C3%A7-ekran-512gb-burgonya'
STORES = ('akasya', 'zorlu', 'bağdat', 'bagdat')

def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {'User-Agent': 'Mozilla/5.0 (compatible; IstanbulStockMonitor/1.0)', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def send(message):
    payload = urllib.parse.urlencode({'chat_id': CHAT, 'text': message, 'disable_web_page_preview': 'true'}).encode()
    url = 'https://api.telegram.org/bot' + BOT + '/sendMessage'
    req = urllib.request.Request(url, data=payload)
    with urllib.request.urlopen(req, timeout=20) as r:
        resp = json.load(r)
    if not resp.get('ok'):
        raise RuntimeError('Telegram gönderimi başarısız')

def main():
    if not (PART and BOT and CHAT):
        raise ValueError('APPLE_PART_NUMBER, TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID tanımlanmalı. Ürün kodu tahmin edilmez.')
    if not PART.replace('/', '').isalnum():
        raise ValueError('Geçersiz ürün kodu')
    seen = {}
    # Önce TR mağaza uç noktası; başarısız olursa sessizce "stok yok" denmez.
    query = urllib.parse.urlencode({'pl':'true','location':'İstanbul','parts.0':PART})
    urls = [f'https://www.apple.com/tr/shop/retail/pickup-message?{query}',
            f'https://www.apple.com/shop/retail/pickup-message?{query}']
    errors = []
    data = None
    for url in urls:
        try:
            candidate = get_json(url)
            stores = candidate.get('body', {}).get('stores') or candidate.get('stores')
            if isinstance(stores, list) and stores:
                data = stores
                break
            errors.append('Geçersiz veya boş mağaza yanıtı')
        except Exception as e:
            errors.append(str(e))
    if data is None:
        raise RuntimeError('Apple geçerli mağaza verisi döndürmedi: ' + '; '.join(errors)[:600])
    matched = 0
    for store in data:
        name = str(store.get('storeName') or store.get('name') or '')
        if not any(s in name.casefold() for s in STORES):
            continue
        matched += 1
        availability = store.get('partsAvailability') or {}
        item = availability.get(PART, {})
        # Apple yanıtları sürüme göre değişebiliyor, yalnızca açık "available" kabul edilir.
        status = str(item.get('pickupDisplay', '')).lower()
        if not status:
            raise RuntimeError(f'{name}: {PART} için ürün yanıtı yok. Kod veya Apple API yapısı kontrol edilmeli.')
        seen[name] = status == 'available'
    if matched < 3:
        raise RuntimeError(f'3 İstanbul mağazası doğrulanamadı. Görülen mağazalar: {list(seen)}')
    try:
        prior = json.loads(STATE.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        prior = {}
    available_now = [n for n, v in seen.items() if v and not prior.get(n)]
    for name in available_now:
        send(f'🚨 iPHONE STOK BULUNDU!\n\niPhone 18 Pro Max 512 GB Burgonya\nMağaza: {name}\n{PRODUCT}\n\nHemen Apple sitesinde mağazadan teslim almayı kontrol et. Stok rezervasyonu yapılmadı.')
    STATE.write_text(json.dumps(seen, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(datetime.now(timezone.utc).isoformat(), 'Mağaza sayısı:', matched, 'Stok:', seen, 'Yeni alarm:', available_now)

if __name__ == '__main__':
    try:
        main()
    except Exception as ex:
        print(f'HATA: {ex}', file=sys.stderr)
        sys.exit(1)
