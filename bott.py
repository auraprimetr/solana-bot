import ccxt
import pandas as pd
import requests
import time

# Bybit birjasını aktivləşdiririk
exchange = ccxt.bybit({
    'enableRateLimit': True
})

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1550767474553790484/CQPIDYH4vNcCbVnmpckZt_Mk1-UAaBymKhoMNFPcgjxl44P9kWbSoj1mIpSVtM2s2pl8"

def send_discord_alert(message):
    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data)
    except Exception as e:
        print(f"Discord xətası: {e}")

def check_market():
    try:
        symbol = 'SOL/USDT'
        
        # Klines (OHLCV) məlumatını çəkirik
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # RSI hesablanması (14 dövrlük)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        current_rsi = df['rsi'].iloc[-1]
        
        # Order Book məlumatı
        order_book = exchange.fetch_order_book(symbol, limit=5)
        bid_volume = sum([bid[1] for bid in order_book['bids']])
        ask_volume = sum([ask[1] for ask in order_book['asks']])
        imbalance = bid_volume / ask_volume if ask_volume > 0 else 1.0
        
        current_price = df['close'].iloc[-1]
        
        report = (
            f"🟢 **Bybit Solana (SOL/USDT) Canlı Hesabatı**\n"
            f"💰 Qiymət: `{current_price}`\n"
            f"📊 RSI (14): `{current_rsi:.2f}`\n"
            f"⚖️ Order Book Balansı: `{imbalance:.2f}`"
        )
        
        send_discord_alert(report)
        print("Hesabat uğurla göndərildi!")
        
    except Exception as e:
        error_msg = f"❌ **Botda xəta baş verdi:** {e}"
        print(error_msg)
        send_discord_alert(error_msg)

if __name__ == "__main__":
    while True:
        check_market()
        time.sleep(300)
