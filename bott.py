import ccxt
import pandas as pd
import feedparser
import requests
import time

# OKX birjasını aktivləşdiririk
exchange = ccxt.okx({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot'
    }
})

symbol = 'SOL/USDT'
timeframe = '15m'

# Discord Webhook Linkin
WEBHOOK_URL = "https://discord.com/api/webhooks/1550767474553790484/CQPIDYH4vNcCbVnmpckZt_Mk1-UAaBymKhoMNFPcgjxl44P9kWbSoj1mIpSVtM2s2pl8"

# Virtual Portfel (10,000$ ilkin balans)[cite: 4]
initial_balance = 10000.0
cash_usd = 10000.0
sol_held = 0.0
trade_amount_usd = 2000.0

print(f"🔥 {symbol} üzrə Discord Canlı Hesabat və Portfel Botu İşə Düşdü!")

def send_discord_message(message):
    data = {"content": message}
    try:
        requests.post(WEBHOOK_URL, json=data)
    except Exception as e:
        print(f"Discord xətası: {e}")

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices):
    exp1 = prices.ewm(span=12, adjust=False).mean()
    exp2 = prices.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def get_real_crypto_sentiment():
    try:
        rss_url = "https://cointelegraph.com/rss"
        feed = feedparser.parse(rss_url)
        positive_words = ['bull', 'surge', 'pump', 'high', 'up', 'approval', 'gain', 'growth', 'rally', 'record']
        negative_words = ['bear', 'drop', 'crash', 'down', 'ban', 'sec', 'lawsuit', 'loss', 'fall', 'risk']
        score = 0
        latest_headline = "Xəbər tapılmadı"
        if feed.entries:
            latest_headline = feed.entries[0].title
            for entry in feed.entries[:3]:
                title_lower = entry.title.lower()
                for word in positive_words:
                    if word in title_lower:
                        score += 1
                for word in negative_words:
                    if word in title_lower:
                        score -= 1
        return score, latest_headline
    except Exception as e:
        return 0, f"Xəbər oxunmadı: {e}"

send_discord_message("🚀 **Pro Portfel Botu işə düşdü!** Saat və balans hesabatları aktivdir.")

try:
    while True:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=50)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        order_book = exchange.fetch_order_book(symbol, limit=20)
        bids_volume = sum([bid[1] for bid in order_book['bids']])
        asks_volume = sum([ask[1] for ask in order_book['asks']])
        book_ratio = bids_volume / asks_volume if asks_volume > 0 else 1.0
        
        news_score, headline = get_real_crypto_sentiment()
        
        df['rsi'] = calculate_rsi(df['close'], period=14)
        df['macd'], df['macd_signal'] = calculate_macd(df['close'])
        
        current_price = df['close'].iloc[-1]
        current_rsi = df['rsi'].iloc[-1]
        current_macd = df['macd'].iloc[-1]
        current_signal = df['macd_signal'].iloc[-1]
        
        signal_status = "NEYTRAL (Fürsət gözlənilir)"
        
        # Alış Şərti
        if current_rsi < 38 and current_macd > current_signal and book_ratio > 1.1 and news_score >= 0 and cash_usd >= trade_amount_usd:
            bought_sol = trade_amount_usd / current_price
            sol_held += bought_sol
            cash_usd -= trade_amount_usd
            signal_status = "🟢 GÜCLÜ ALIM HƏYATA KEÇDİ!"
            
        # Satış Şərti
        elif (current_rsi > 62 or current_macd < current_signal or news_score < 0) and sol_held > 0:
            sold_usd = sol_held * current_price
            cash_usd += sold_usd
            sol_held = 0.0
            signal_status = "🔴 SATILDI (Qazanc götürüldü / Risk)"
        
        total_portfolio_value = cash_usd + (sol_held * current_price)
        profit_loss = total_portfolio_value - initial_balance
        profit_loss_pct = (profit_loss / initial_balance) * 100
        pnl_symbol = "+" if profit_loss >= 0 else ""
        
        macd_trend = "Artır 📈" if current_macd > current_signal else "Enir 📉"
        
        # Anlıq saat sətrini əlavə edirik
        current_time = time.strftime('%H:%M:%S')
        
        report_message = (
            f"⏰ **Saat:** `{current_time}`\n"
            f"📊 **BAZAR:** {symbol} (15m) | **QİYMƏT:** `{current_price:,.2f} USDT`\n"
            f"📰 **SON XƏBƏR:** `{headline[:50]}...`\n"
            f"🧠 **İNDİKATORLAR:** RSI: `{current_rsi:.1f}` | MACD: `{macd_trend}` | Balina Oranı: `{book_ratio:.2f}`\n"
            f"🤖 **BOT STATUSU:** {signal_status}\n"
            f"------------------------------------\n"
            f"💵 Nağd: `{cash_usd:,.2f} $` | 🪙 SOL: `{sol_held:.2f}`\n"
            f"💼 Portfel: `{total_portfolio_value:,.2f} USDT`\n"
            f"📈 Xalis PnL: `{pnl_symbol}{profit_loss:,.2f} USDT ({pnl_symbol}{profit_loss_pct:.2f}%)`\n"
            f"===================================="
        )
        
        print(f"[{current_time}] Hesabat göndərildi. Qiymət: {current_price} | RSI: {current_rsi:.1f}")
        send_discord_message(report_message)
        
        # Hər 5 dəqiqədən bir yenilənir
        time.sleep(300)
        
except Exception as e:
    err_msg = f"❌ **Botda xəta baş verdi:** {e}"
    print(err_msg)
    send_discord_message(err_msg)
