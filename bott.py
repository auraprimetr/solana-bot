import ccxt
import pandas as pd
import requests
import time
from datetime import datetime, timezone, timedelta

# OKX Birjası
exchange = ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
symbol = 'SOL/USDT'
timeframe = '15m'

WEBHOOK_URL = "https://discord.com/api/webhooks/1550767474553790484/CQPIDYH4vNcCbVnmpckZt_Mk1-UAaBymKhoMNFPcgjxl44P9kWbSoj1mIpSVtM2s2pl8"

# Portfel və Risk İdarəetməsi
initial_balance = 10000.0
cash_usd = 10000.0
sol_held = 0.0
trade_amount_usd = 2500.0

fee_rate = 0.001       # 0.1% Birja komissiyası
stop_loss_pct = 0.02   # -2% Stop Loss
take_profit_pct = 0.04 # +4% Take Profit
buy_price = 0.0 

print(f"🚀 {symbol} üzrə PRO EMBED BOT İşə Düşdü!")

def send_discord_embed(title, color_code, fields, footer_text):
    """Discord-a şık Embed kartı göndərir"""
    embed = {
        "title": title,
        "color": color_code,
        "fields": fields,
        "footer": {"text": footer_text}
    }
    try:
        requests.post(WEBHOOK_URL, json={"embeds": [embed]})
    except Exception as e:
        print(f"Discord xətası: {e}")

def get_fear_and_greed_index():
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5).json()
        value = int(resp['data'][0]['value'])
        classification = resp['data'][0]['value_classification']
        return value, classification
    except:
        return 50, "Neutral"

def add_indicators(df):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    df['bb_mid'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * 2)
    return df

try:
    while True:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=50)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = add_indicators(df)
        
        order_book = exchange.fetch_order_book(symbol, limit=20)
        bids_volume = sum([bid[1] for bid in order_book['bids']])
        asks_volume = sum([ask[1] for ask in order_book['asks']])
        book_ratio = bids_volume / asks_volume if asks_volume > 0 else 1.0
        
        fng_value, fng_class = get_fear_and_greed_index()
        
        current_price = df['close'].iloc[-1]
        current_rsi = df['rsi'].iloc[-1]
        current_macd = df['macd'].iloc[-1]
        current_signal = df['macd_signal'].iloc[-1]
        bb_lower = df['bb_lower'].iloc[-1]
        
        signal_status = "⏸️ NEYTRAL (Fürsət gözlənilir)"
        card_color = 3447003 # Mavi (Default)
        
        # --- ALIŞ STRATEGİYASI ---
        if (current_rsi < 38 or current_price <= bb_lower) and book_ratio > 0.85 and fng_value < 80 and cash_usd >= trade_amount_usd:
            fee = trade_amount_usd * fee_rate
            net_investment = trade_amount_usd - fee
            bought_sol = net_investment / current_price
            
            sol_held += bought_sol
            cash_usd -= trade_amount_usd
            buy_price = current_price
            signal_status = f"🟢 ALINDI! (Giriş: {buy_price:.2f} USDT)"
            card_color = 5763719 # Yeşil
            
        # --- SATIŞ STRATEGİYASI ---
        elif sol_held > 0:
            profit_pct = (current_price - buy_price) / buy_price
            
            if profit_pct >= take_profit_pct:
                gross_usd = sol_held * current_price
                fee = gross_usd * fee_rate
                cash_usd += (gross_usd - fee)
                sol_held = 0.0
                signal_status = f"🎯 TAKE-PROFIT! (+{profit_pct*100:.2f}%)"
                card_color = 5763719 # Yeşil
                
            elif profit_pct <= -stop_loss_pct:
                gross_usd = sol_held * current_price
                fee = gross_usd * fee_rate
                cash_usd += (gross_usd - fee)
                sol_held = 0.0
                signal_status = f"🛑 STOP-LOSS! ({profit_pct*100:.2f}%)"
                card_color = 15548997 # Kırmızı
                
            elif current_rsi > 65 or current_macd < current_signal:
                gross_usd = sol_held * current_price
                fee = gross_usd * fee_rate
                cash_usd += (gross_usd - fee)
                sol_held = 0.0
                signal_status = "🔴 SATILDI (İndikator siqnalı)"
                card_color = 15548997 # Kırmızı

        total_portfolio_value = cash_usd + (sol_held * current_price)
        profit_loss = total_portfolio_value - initial_balance
        profit_loss_pct = (profit_loss / initial_balance) * 100
        pnl_symbol = "+" if profit_loss >= 0 else ""
        macd_trend = "Artır 📈" if current_macd > current_signal else "Enir 📉"
        
        if profit_loss > 0:
            card_color = 5763719 # Portföy kârda ise yeşil yap
        elif profit_loss < 0 and sol_held > 0:
            card_color = 15548997 # Portföy zararda ise kırmızı yap

        az_timezone = timezone(timedelta(hours=4))
        current_time = datetime.now(az_timezone).strftime('%H:%M:%S')
        
        # --- ŞIK EMBED TASARIMI ---
        fields = [
            {"name": "📊 Fiyat", "value": f"`{current_price:,.2f} USDT`", "inline": True},
            {"name": "🧠 RSI", "value": f"`{current_rsi:.1f}`", "inline": True},
            {"name": "📈 MACD", "value": f"`{macd_trend}`", "inline": True},
            
            {"name": "🐋 Balina Oranı", "value": f"`{book_ratio:.2f}`", "inline": True},
            {"name": "😨 Qorxu İndeksi", "value": f"`{fng_value} ({fng_class})`", "inline": True},
            {"name": "🤖 Bot Statusu", "value": f"**{signal_status}**", "inline": False},
            
            {"name": "💵 Nağd Pul", "value": f"`${cash_usd:,.2f}`", "inline": True},
            {"name": "🪙 SOL Varlığı", "value": f"`{sol_held:.4f} SOL`", "inline": True},
            {"name": "💼 Toplam Portfel", "value": f"`${total_portfolio_value:,.2f}`", "inline": True},
            
            {"name": "📈 Net PnL (Kâr/Zərər)", "value": f"```diff\n{pnl_symbol}{profit_loss:,.2f} USDT ({pnl_symbol}{profit_loss_pct:.2f}%)\n```", "inline": False}
        ]
        
        title = f"🤖 SOL/USDT Trading Panel"
        footer = f"Azərbaycan Vaxtı: {current_time} | OKX Spot Simulation"
        
        send_discord_embed(title, card_color, fields, footer)
        print(f"[{current_time}] Yeni Embed Rapor Gönderildi.")
        
        time.sleep(300)
        
except Exception as e:
    err_msg = f"❌ **Botda xəta baş verdi:** {e}"
    send_discord_embed("❌ Hata Oluştu", 15548997, [{"name": "Xəta", "value": str(e), "inline": False}], "Bot Error Handler")
