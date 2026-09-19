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

# Portfel və Risk İdarəetməsi (Smart-Aggressive)
initial_balance = 10000.0
cash_usd = 10000.0
sol_held = 0.0
trade_amount_usd = 2500.0 # Hər alımda 2500$ istifadə olunacaq

# Risk Qaydaları
fee_rate = 0.001       # 0.1% Birja komissiyası
stop_loss_pct = 0.02   # -2% Zərəri Kəs (Capital Protection)
take_profit_pct = 0.04 # +4% Qazancı Götür (Tez və Dəqiq Qazanc)
buy_price = 0.0 

print(f"🚀 {symbol} üzrə SMART-AGGRESSIVE Bot İşə Düşdü!")

def send_discord_message(message):
    try:
        requests.post(WEBHOOK_URL, json={"content": message})
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
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    # Bollinger Bands
    df['bb_mid'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * 2)
    
    return df

send_discord_message("⚡ **V2.5 AĞILLI-AQRESSİV REJİM AKTİVDİR:** Fürsət şərtləri optimallaşdırıldı, alım həddi çevikləşdirildi.")

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
        
        signal_status = "NEYTRAL (Fürsət gözlənilir)"
        
        # --- ÇEVİK ALIŞ STRATEGİYASI ---
        # Şərtlər: RSI < 38 VƏ YA Bollinger Dibinə Dəyibsə + Order Book > 0.85 + FNG Extreme Greed (>80) deyilsə
        if (current_rsi < 38 or current_price <= bb_lower) and book_ratio > 0.85 and fng_value < 80 and cash_usd >= trade_amount_usd:
            fee = trade_amount_usd * fee_rate
            net_investment = trade_amount_usd - fee
            bought_sol = net_investment / current_price
            
            sol_held += bought_sol
            cash_usd -= trade_amount_usd
            buy_price = current_price
            signal_status = f"🟢 ALINDI! (Giriş Qiyməti: {buy_price:.2f} USDT)"
            
        # --- SATIŞ VƏ RİSK İDARƏETMƏSİ ---
        elif sol_held > 0:
            profit_pct = (current_price - buy_price) / buy_price
            
            if profit_pct >= take_profit_pct:
                gross_usd = sol_held * current_price
                fee = gross_usd * fee_rate
                cash_usd += (gross_usd - fee)
                sol_held = 0.0
                signal_status = f"🎯 TAKE-PROFIT! Qazanc götürüldü (+{profit_pct*100:.2f}%)"
                
            elif profit_pct <= -stop_loss_pct:
                gross_usd = sol_held * current_price
                fee = gross_usd * fee_rate
                cash_usd += (gross_usd - fee)
                sol_held = 0.0
                signal_status = f"🛑 STOP-LOSS! Zərər kəsildi ({profit_pct*100:.2f}%)"
                
            elif current_rsi > 65 or current_macd < current_signal:
                gross_usd = sol_held * current_price
                fee = gross_usd * fee_rate
                cash_usd += (gross_usd - fee)
                sol_held = 0.0
                signal_status = "🔴 SATILDI (İndikator siqnalı)"

        total_portfolio_value = cash_usd + (sol_held * current_price)
        profit_loss = total_portfolio_value - initial_balance
        profit_loss_pct = (profit_loss / initial_balance) * 100
        pnl_symbol = "+" if profit_loss >= 0 else ""
        macd_trend = "Artır 📈" if current_macd > current_signal else "Enir 📉"
        
        az_timezone = timezone(timedelta(hours=4))
        current_time = datetime.now(az_timezone).strftime('%H:%M:%S')
        
        report_message = (
            f"⏰ **Saat:** `{current_time}`\n"
            f"📊 **BAZAR:** {symbol} | **QİYMƏT:** `{current_price:,.2f} USDT`\n"
            f"😨 **QORXU İNDEKSİ:** `{fng_value} ({fng_class})`\n"
            f"🧠 **İNDİKATORLAR:** RSI: `{current_rsi:.1f}` | MACD: `{macd_trend}` | Balina Oranı: `{book_ratio:.2f}`\n"
            f"🤖 **BOT STATUSU:** {signal_status}\n"
            f"------------------------------------\n"
            f"💵 Nağd: `{cash_usd:,.2f} $` | 🪙 SOL: `{sol_held:.4f}`\n"
            f"💼 Portfel: `{total_portfolio_value:,.2f} USDT`\n"
            f"📈 Xalis PnL: `{pnl_symbol}{profit_loss:,.2f} USDT ({pnl_symbol}{profit_loss_pct:.2f}%)`\n"
            f"===================================="
        )
        
        print(f"[{current_time}] Hesabat göndərildi.")
        send_discord_message(report_message)
        
        time.sleep(300)
        
except Exception as e:
    err_msg = f"❌ **Botda xəta baş verdi:** {e}"
    send_discord_message(err_msg)
