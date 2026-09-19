import ccxt
import pandas as pd
import requests
import time
import json
import os
from datetime import datetime, timezone, timedelta

# OKX Birjası
exchange = ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
symbol = 'SOL/USDT'
timeframe = '15m'

WEBHOOK_URL = "https://discord.com/api/webhooks/1550767474553790484/CQPIDYH4vNcCbVnmpckZt_Mk1-UAaBymKhoMNFPcgjxl44P9kWbSoj1mIpSVtM2s2pl8"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DATA_FILE = "portfolio_data.json"

# --- PERSISTENCE & STATS ENGINE ---
def load_portfolio():
    default_data = {
        "initial_balance": 10000.0,
        "cash_usd": 10000.0,
        "sol_held": 0.0,
        "buy_price": 0.0,
        "highest_price": 0.0,
        "total_trades": 0,
        "win_trades": 0,
        "loss_trades": 0,
        "realized_pnl": 0.0
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                for key, val in default_data.items():
                    if key not in data:
                        data[key] = val
                return data
        except Exception as e:
            print(f"Yaddaş xətası: {e}")
    return default_data

def save_portfolio(data):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Yaddaş yazma xətası: {e}")

portfolio = load_portfolio()

# Ticarət Parametrləri
trade_amount_usd = 2500.0
fee_rate = 0.001           # 0.1% Birja Komissiyası
hard_stop_loss_pct = 0.02 # -2% Əsas Stop
trailing_stop_pct = 0.015  # Zirvədən -1.5% düşərsə İzləyən Stop
take_profit_pct = 0.04     # +4% Take Profit

# --- GEMINI AI ANALYZER ENGINE ---
def analyze_market_with_gemini(price, rsi, book_ratio, fng_val, fng_class):
    if not GEMINI_API_KEY:
        return "Gemini API açarı Railway Variables-da tapılmadı.", True

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""
    Sən peşəkar Wall Street kripto analitikisən. SOL/USDT üçün indikatorları analiz et:
    - Cari Qiymət: ${price:.2f}
    - RSI: {rsi:.1f}
    - Balina Orderbook Həcm Nisbəti (Bids/Asks): {book_ratio:.2f}
    - Qorxu/Tamah İndeksi: {fng_val}/100 ({fng_class})

    Aşağıdakıları et:
    1. Azərbaycan dilində maksimum 2 cümləlik qısa, çox peşəkar bazar xülasəsi yaz.
    2. Cavabın sonuna eynilə bu formatda təhlükəsizlik statusunu əlavə et: [STATUS: SAFE] və ya [STATUS: UNSAFE] (Əgər ekstremal manipulyasiya və ya anormal risk görsən UNSAFE yaz).
    """
    
    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': GEMINI_API_KEY
    }
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=8)
        if response.status_code == 200:
            res_json = response.json()
            text_resp = res_json['candidates'][0]['content']['parts'][0]['text']
            
            is_safe = True
            if "[STATUS: UNSAFE]" in text_resp:
                is_safe = False
                
            clean_text = text_resp.replace("[STATUS: SAFE]", "").replace("[STATUS: UNSAFE]", "").strip()
            return clean_text, is_safe
        else:
            return f"Gemini AI sorğu xətası (Kod: {response.status_code})", True
    except Exception as e:
        return "AI analizi müvəqqəti əlçatmazdır.", True

# --- GUI HELPER FUNCTIONS ---
def make_gauge_bar(val, min_val=0, max_val=100, length=10):
    pct = min(max((val - min_val) / (max_val - min_val), 0), 1)
    filled = int(round(pct * length))
    return "█" * filled + "░" * (length - filled)

def send_discord_embed(title, color_code, fields, footer_text):
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
    
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    return df

print(f"⚡ {symbol} WALL STREET AI-POWERED TERMINAL AKTİVDİR!")

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
        current_atr = df['atr'].iloc[-1]
        bb_lower = df['bb_lower'].iloc[-1]
        
        # --- GEMINI AI ANALİZİ ---
        ai_commentary, ai_is_safe = analyze_market_with_gemini(current_price, current_rsi, book_ratio, fng_value, fng_class)
        
        signal_status = "⏸️ NEYTRAL (Pusquda gözlənilir...)"
        card_color = 0x00F0FF # Cyber Blue
        
        # --- ALIŞ STRATEGİYASI (Riyaziyyat + Gemini AI Süzgəci) ---
        technical_buy = (current_rsi < 38 or current_price <= bb_lower) and book_ratio > 0.85 and fng_value < 80
        
        if technical_buy and ai_is_safe and portfolio['cash_usd'] >= trade_amount_usd:
            fee = trade_amount_usd * fee_rate
            net_investment = trade_amount_usd - fee
            bought_sol = net_investment / current_price
            
            portfolio['sol_held'] += bought_sol
            portfolio['cash_usd'] -= trade_amount_usd
            portfolio['buy_price'] = current_price
            portfolio['highest_price'] = current_price
            save_portfolio(portfolio)
            
            signal_status = f"🟢 AI TƏSDİQLİ ALIM! ({current_price:.2f} USDT)"
            card_color = 0x00FF66 # Emerald Green
            
        elif technical_buy and not ai_is_safe:
            signal_status = "⚠️ İNDİKATOR AL DESƏ DƏ AI RİSK AŞKARLADI (LƏĞV EDİLDİ)"
            card_color = 0xFFD700
            
        # --- SATIŞ VƏ RİSK İDARƏETMƏSİ ---
        elif portfolio['sol_held'] > 0:
            if current_price > portfolio['highest_price']:
                portfolio['highest_price'] = current_price
                save_portfolio(portfolio)
                
            profit_pct = (current_price - portfolio['buy_price']) / portfolio['buy_price']
            drop_from_peak = (portfolio['highest_price'] - current_price) / portfolio['highest_price']
            
            trade_closed = False
            trade_pnl = 0.0
            
            # 1. Take Profit (+4%)
            if profit_pct >= take_profit_pct:
                gross_usd = portfolio['sol_held'] * current_price
                fee = gross_usd * fee_rate
                received = gross_usd - fee
                trade_pnl = received - trade_amount_usd
                
                portfolio['cash_usd'] += received
                portfolio['realized_pnl'] += trade_pnl
                portfolio['total_trades'] += 1
                portfolio['win_trades'] += 1
                trade_closed = True
                signal_status = f"🎯 TAKE-PROFIT! (+{profit_pct*100:.2f}%)"
                card_color = 0xFFD700
                
            # 2. Trailing Stop (-1.5% Zirvədən)
            elif drop_from_peak >= trailing_stop_pct and profit_pct > 0.005:
                gross_usd = portfolio['sol_held'] * current_price
                fee = gross_usd * fee_rate
                received = gross_usd - fee
                trade_pnl = received - trade_amount_usd
                
                portfolio['cash_usd'] += received
                portfolio['realized_pnl'] += trade_pnl
                portfolio['total_trades'] += 1
                portfolio['win_trades'] += 1
                trade_closed = True
                signal_status = f"🏹 TRAILING STOP! Zirvədən Satıldı (+{profit_pct*100:.2f}%)"
                card_color = 0xFFD700
                
            # 3. Hard Stop-Loss (-2%)
            elif profit_pct <= -hard_stop_loss_pct:
                gross_usd = portfolio['sol_held'] * current_price
                fee = gross_usd * fee_rate
                received = gross_usd - fee
                trade_pnl = received - trade_amount_usd
                
                portfolio['cash_usd'] += received
                portfolio['realized_pnl'] += trade_pnl
                portfolio['total_trades'] += 1
                portfolio['loss_trades'] += 1
                trade_closed = True
                signal_status = f"🛑 HARD STOP-LOSS! ({profit_pct*100:.2f}%)"
                card_color = 0xFF0055
                
            # 4. İndikator Dönüşü
            elif current_rsi > 65 or current_macd < current_signal:
                gross_usd = portfolio['sol_held'] * current_price
                fee = gross_usd * fee_rate
                received = gross_usd - fee
                trade_pnl = received - trade_amount_usd
                
                portfolio['cash_usd'] += received
                portfolio['realized_pnl'] += trade_pnl
                portfolio['total_trades'] += 1
                if trade_pnl >= 0:
                    portfolio['win_trades'] += 1
                else:
                    portfolio['loss_trades'] += 1
                trade_closed = True
                signal_status = "🔴 İNDİKATOR SİQNALI İLƏ SATILDI"
                card_color = 0xFF0055

            if trade_closed:
                portfolio['sol_held'] = 0.0
                portfolio['buy_price'] = 0.0
                portfolio['highest_price'] = 0.0
                save_portfolio(portfolio)

        # Hesablamalar
        total_portfolio_value = portfolio['cash_usd'] + (portfolio['sol_held'] * current_price)
        profit_loss = total_portfolio_value - portfolio['initial_balance']
        profit_loss_pct = (profit_loss / portfolio['initial_balance']) * 100
        pnl_symbol = "+" if profit_loss >= 0 else ""
        
        total_tr = portfolio['total_trades']
        win_tr = portfolio['win_trades']
        win_rate = (win_tr / total_tr * 100) if total_tr > 0 else 0.0
        
        rsi_bar = make_gauge_bar(current_rsi)
        rsi_state = "Aşırı Satış 🟢" if current_rsi < 38 else ("Aşırı Alış 🔴" if current_rsi > 70 else "Neytral 🟡")
        macd_trend = "Buğa Momentum 📈" if current_macd > current_signal else "Ayı Momentum 📉"
        
        az_timezone = timezone(timedelta(hours=4))
        current_time = datetime.now(az_timezone).strftime('%H:%M:%S')
        
        # --- DISCORD EMBED BUILDER ---
        fields = [
            {"name": "📊 Cari Qiymət (SOL/USDT)", "value": f"```fix\n${current_price:,.2f} USDT (ATR: ±${current_atr:.2f})\n```", "inline": False},
            {"name": "🧠 Gemini AI Analitik Şərhi", "value": f"> *\"{ai_commentary}\"*", "inline": False},
            
            {"name": "📉 RSI Indikatoru", "value": f"`[{rsi_bar}]` **{current_rsi:.1f}** ({rsi_state})", "inline": True},
            {"name": "📈 MACD Trend", "value": f"`{macd_trend}`", "inline": True},
            {"name": "🐋 Balina Təzyiqi", "value": f"`{book_ratio:.2f}` (OrderBook)", "inline": True},
            
            {"name": "😨 Market Psixologiyası", "value": f"`{fng_value}/100` ({fng_class})", "inline": True},
            {"name": "🤖 Algoritm Statusu", "value": f"**{signal_status}**", "inline": False}
        ]
        
        if portfolio['sol_held'] > 0:
            tp_target = portfolio['buy_price'] * (1 + take_profit_pct)
            sl_target = portfolio['buy_price'] * (1 - hard_stop_loss_pct)
            current_unrealized = (current_price - portfolio['buy_price']) * portfolio['sol_held']
            current_unrealized_pct = (current_price - portfolio['buy_price']) / portfolio['buy_price'] * 100
            unreal_sym = "+" if current_unrealized >= 0 else ""
            
            position_hud = (
                f"```yaml\n"
                f"Giriş Qiyməti : ${portfolio['buy_price']:.2f}\n"
                f"Zirvə Qiyməti : ${portfolio['highest_price']:.2f}\n"
                f"🎯 Take-Profit  : ${tp_target:.2f} (+4.0%)\n"
                f"🛑 Stop-Loss    : ${sl_target:.2f} (-2.0%)\n"
                f"Gözlənilən PnL  : {unreal_sym}${current_unrealized:.2f} ({unreal_sym}{current_unrealized_pct:.2f}%)\n"
                f"```"
            )
            fields.append({"name": "🎯 AKTİV TİCARƏT MONITORU (HUD)", "value": position_hud, "inline": False})
            
            if current_unrealized > 0:
                card_color = 0x00FF66
            else:
                card_color = 0xFF0055
        
        stats_block = (
            f"💵 Nağd Pul : `${portfolio['cash_usd']:,.2f}`\n"
            f"🪙 SOL Həcmi: `{portfolio['sol_held']:.4f} SOL`\n"
            f"💼 Balans   : `${total_portfolio_value:,.2f}`"
        )
        fields.append({"name": "💼 Portfel Vəziyyəti", "value": stats_block, "inline": True})
        
        perf_block = (
            f"🏆 Ticarətlər: `{total_tr}` (Qələbə: `{win_tr}`)\n"
            f"🎯 Win Rate  : `{win_rate:.1f}%`\n"
            f"💰 Realize PnL: `${portfolio['realized_pnl']:,.2f}`"
        )
        fields.append({"name": "📊 Performans Paneli", "value": perf_block, "inline": True})
        
        fields.append({
            "name": "📈 Ümumi Xalis PnL (Net PnL)", 
            "value": f"```diff\n{pnl_symbol}{profit_loss:,.2f} USDT ({pnl_symbol}{profit_loss_pct:.2f}%)\n```", 
            "inline": False
        })
        
        title = "⚡ SOL/USDT Wall Street AI Pro Terminal V3.5"
        footer = f"Bakı/Sumqayıt Vaxtı: {current_time} | Powered by Gemini AI & OKX Spot Engine"
        
        send_discord_embed(title, card_color, fields, footer)
        print(f"[{current_time}] AI Dashboard Yeniləndi.")
        
        time.sleep(300)
        
except Exception as e:
    send_discord_embed("❌ Hata Oluştu", 0xFF0055, [{"name": "Xəta", "value": str(e), "inline": False}], "Wall Street Error Handler")
