import ccxt
import pandas as pd
import requests
import time
import json
import os
import math
from datetime import datetime, timezone, timedelta

# OKX Exchange Konfigürasyonu
exchange = ccxt.okx({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})
symbol = 'SOL/USDT'
timeframe = '1h'  # 15m yerine 1 saatlik grafik (Gürültüyü keser)

WEBHOOK_URL = "https://discord.com/api/webhooks/1551226030180663341/G1giGhYaf7S27KDsJzBffn82gXwR6pEaKnXCgxzWT32E5q_5gayC45UXmxdVCsx4imop"
DATA_FILE = "portfolio_data.json"

# --- PORTFÖY YÖNETİM MOTORU ---
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
        "realized_pnl": 0.0,
        "daily_trades_count": 0,
        "daily_pnl": 0.0,
        "last_daily_report_date": "",
        "last_trade_time": 0
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for key, val in default_data.items():
                    if key not in data:
                        data[key] = val
                return data
        except Exception as e:
            print(f"⚠️ Portföy dosyası hatası: {e}")
    return default_data

def save_portfolio(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Veri kaydetme hatası: {e}")

portfolio = load_portfolio()
save_portfolio(portfolio)

# Strateji Parametreleri (Garantici & Muhafazakar)
trade_amount_usd = 2000.0
fee_rate = 0.001           # %0.1 Komisyon
hard_stop_loss_pct = 0.02  # -%2 Stop Loss
take_profit_pct = 0.04      # +%4 Take Profit
cooldown_seconds = 14400   # İşlem sonrası 4 saat bekleme süresi

def make_gauge_bar(val, min_val=0, max_val=100, length=10):
    if math.isnan(val):
        val = 50
    pct = min(max((val - min_val) / (max_val - min_val), 0), 1)
    filled = int(round(pct * length))
    return "🟩" * filled + "⬛" * (length - filled)

def send_discord_embed(title, color_code, fields, footer_text):
    embed = {
        "title": title,
        "color": color_code,
        "fields": fields,
        "footer": {"text": footer_text},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    payload = {
        "content": f"📢 **{title}**",
        "embeds": [embed]
    }
    try:
        requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
    except Exception as e:
        print(f"❌ Discord Hatası: {e}")

def get_fear_and_greed_index():
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5).json()
        val_raw = resp['data'][0]['value']
        if str(val_raw).isdigit():
            return int(val_raw), resp['data'][0].get('value_classification', 'Neutral')
    except Exception:
        pass
    return 50, "Neutral"

def add_indicators(df):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    loss = loss.replace(0, 1e-9)
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    df['bb_mid'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * 2)
    
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    return df.fillna(0)

def send_daily_audit_report(current_price):
    az_timezone = timezone(timedelta(hours=4))
    today_str = datetime.now(az_timezone).strftime('%Y-%m-%d')
    
    total_tr = portfolio['total_trades']
    win_tr = portfolio['win_trades']
    win_rate = (win_tr / total_tr * 100) if total_tr > 0 else 0.0
    
    total_val = portfolio['cash_usd'] + (portfolio['sol_held'] * current_price)
    total_pnl = total_val - portfolio['initial_balance']
    pnl_sym = "+" if total_pnl >= 0 else ""
    daily_pnl_sym = "+" if portfolio['daily_pnl'] >= 0 else ""
    
    fields = [
        {
            "name": "📋 GÜNLÜK İCRAAT ÖZETİ",
            "value": (
                f"• **Bu Gün Edilən Əməliyyat:** `{portfolio['daily_trades_count']}` ədəd\n"
                f"• **Günün Net PnL-i:** `{daily_pnl_sym}${portfolio['daily_pnl']:,.2f}`\n"
                f"• **Ümumi Qazanma Oranı:** `{win_rate:.1f}%`"
            ),
            "inline": False
        },
        {
            "name": "💼 ÜMUMİ PORTFELİN VƏZİYYƏTİ",
            "value": (
                f"• **Başlanğıc Balans:** `${portfolio['initial_balance']:,.2f}`\n"
                f"• **Anlıq Portfel Dəyəri:** `${total_val:,.2f}`\n"
                f"• **Ümumi Mənfəət/Zərər:** `{pnl_sym}${total_pnl:,.2f} ({pnl_sym}{(total_pnl/portfolio['initial_balance'])*100:.2f}%)`"
            ),
            "inline": False
        }
    ]
    
    send_discord_embed(f"📊 GÜNLÜK BOT AUDİT HESABATI ({today_str})", 0x00FFFF, fields, "Quantum Conservative Engine")
    portfolio['daily_trades_count'] = 0
    portfolio['daily_pnl'] = 0.0
    portfolio['last_daily_report_date'] = today_str
    save_portfolio(portfolio)

print("🚀 QUANTUM V5.0 - CONSERVATIVE HIGH-PRECISION ENGINE")

while True:
    try:
        az_timezone = timezone(timedelta(hours=4))
        now_az = datetime.now(az_timezone)
        today_str = now_az.strftime('%Y-%m-%d')
        
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=50)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = add_indicators(df)
        
        order_book = exchange.fetch_order_book(symbol, limit=20)
        bids_volume = sum([bid[1] for bid in order_book['bids']])
        asks_volume = sum([ask[1] for ask in order_book['asks']])
        book_ratio = bids_volume / asks_volume if asks_volume > 0 else 1.0
        
        fng_value, fng_class = get_fear_and_greed_index()
        
        current_price = float(df['close'].iloc[-1])
        current_rsi = float(df['rsi'].iloc[-1])
        current_atr = float(df['atr'].iloc[-1])
        bb_lower = float(df['bb_lower'].iloc[-1])
        
        if portfolio['last_daily_report_date'] != today_str and now_az.hour == 0:
            send_daily_audit_report(current_price)
        
        signal_status = "⏸️ NÖTR (Sağlam Fırsat Bekleniyor...)"
        card_color = 0x2B2D31
        
        current_timestamp = time.time()
        cooldown_active = (current_timestamp - portfolio.get('last_trade_time', 0)) < cooldown_seconds
        
        # SERT ALIM KOŞULU (Sadece Çok Net Diplerde)
        technical_buy = (current_rsi <= 28 or current_price <= bb_lower) and book_ratio >= 1.20 and not cooldown_active
        
        if technical_buy and portfolio['cash_usd'] >= trade_amount_usd and portfolio['sol_held'] == 0:
            fee = trade_amount_usd * fee_rate
            net_investment = trade_amount_usd - fee
            bought_sol = net_investment / current_price
            
            portfolio['sol_held'] = bought_sol
            portfolio['cash_usd'] -= trade_amount_usd
            portfolio['buy_price'] = current_price
            portfolio['highest_price'] = current_price
            save_portfolio(portfolio)
            
            signal_status = f"⚡ STRATEJİK ALIM YAPILDI! (${current_price:.2f} USDT)"
            card_color = 0x00FF88
            
        elif portfolio['sol_held'] > 0:
            profit_pct = (current_price - portfolio['buy_price']) / portfolio['buy_price']
            trade_closed = False
            trade_pnl = 0.0
            
            # SADECE NET KAR VE STOP HEDEFLERİ (Piyasadan Korkup Satmak Yok)
            if profit_pct >= take_profit_pct:
                gross_usd = portfolio['sol_held'] * current_price
                received = gross_usd - (gross_usd * fee_rate)
                trade_pnl = received - trade_amount_usd
                
                portfolio['cash_usd'] += received
                portfolio['realized_pnl'] += trade_pnl
                portfolio['daily_pnl'] += trade_pnl
                portfolio['total_trades'] += 1
                portfolio['daily_trades_count'] += 1
                portfolio['win_trades'] += 1
                trade_closed = True
                signal_status = f"🎯 KÂR HEDEFİNE ULAŞILDI! (+{profit_pct*100:.2f}%)"
                card_color = 0xFFD700
                
            elif profit_pct <= -hard_stop_loss_pct:
                gross_usd = portfolio['sol_held'] * current_price
                received = gross_usd - (gross_usd * fee_rate)
                trade_pnl = received - trade_amount_usd
                
                portfolio['cash_usd'] += received
                portfolio['realized_pnl'] += trade_pnl
                portfolio['daily_pnl'] += trade_pnl
                portfolio['total_trades'] += 1
                portfolio['daily_trades_count'] += 1
                portfolio['loss_trades'] += 1
                trade_closed = True
                signal_status = f"🛑 HARD STOP-LOSS! ({profit_pct*100:.2f}%)"
                card_color = 0xFF0055

            if trade_closed:
                portfolio['sol_held'] = 0.0
                portfolio['buy_price'] = 0.0
                portfolio['last_trade_time'] = time.time()
                save_portfolio(portfolio)

        total_portfolio_value = portfolio['cash_usd'] + (portfolio['sol_held'] * current_price)
        profit_loss = total_portfolio_value - portfolio['initial_balance']
        profit_loss_pct = (profit_loss / portfolio['initial_balance']) * 100
        pnl_symbol = "+" if profit_loss >= 0 else ""
        
        total_tr = portfolio['total_trades']
        win_tr = portfolio['win_trades']
        win_rate = (win_tr / total_tr * 100) if total_tr > 0 else 0.0
        
        current_time = now_az.strftime('%H:%M:%S')
        
        fields = [
            {
                "name": "📌 CANLI PİYASA FİYATI (1 Saatlik)",
                "value": f"```ansi\n\x1b[1;36m${current_price:,.2f} USDT\x1b[0m\n```",
                "inline": False
            },
            {
                "name": "📊 İNDİKATÖR DURUMU",
                "value": f"**RSI (14):** `{current_rsi:.1f}` (Hedef: <=28)\n**Bollinger Alt:** `${bb_lower:.2f}`",
                "inline": True
            },
            {
                "name": "🐋 ALIM BASKISI",
                "value": f"**Alıcı/Satıcı Oranı:** `{book_ratio:.2f}` (Hedef: >=1.20)",
                "inline": True
            },
            {
                "name": "⚡ ALGORİTMA DURUMU",
                "value": f"```ansi\n\x1b[1;33m{signal_status}\x1b[0m\n```",
                "inline": False
            }
        ]
        
        if portfolio['sol_held'] > 0:
            current_unrealized = (current_price - portfolio['buy_price']) * portfolio['sol_held']
            current_unrealized_pct = (current_price - portfolio['buy_price']) / portfolio['buy_price'] * 100
            unreal_sym = "+" if current_unrealized >= 0 else ""
            
            position_hud = (
                f"```yaml\n"
                f"Giriş Fiyatı   : ${portfolio['buy_price']:.2f}\n"
                f"🎯 Target (+4%): ${portfolio['buy_price'] * 1.04:.2f}\n"
                f"🛑 Stop (-2%)  : ${portfolio['buy_price'] * 0.98:.2f}\n"
                f"Anlık Durum    : {unreal_sym}${current_unrealized:.2f} ({unreal_sym}{current_unrealized_pct:.2f}%)\n"
                f"```"
            )
            fields.append({"name": "🎯 AKTİF POZİSYON MONİTÖRÜ", "value": position_hud, "inline": False})
        
        fields.append({"name": "💼 PORTFÖY ÖZETİ", "value": f"💵 **Nakit:** `${portfolio['cash_usd']:,.2f}`\n🪙 **SOL:** `{portfolio['sol_held']:.4f}`\n💼 **Toplam:** `${total_portfolio_value:,.2f}`", "inline": True})
        fields.append({"name": "📊 PERFORMANS", "value": f"🏆 **İşlem:** `{total_tr}` *(Başarı: `{win_rate:.1f}%`)*\n💰 **Gerçekleşen PnL:** `${portfolio['realized_pnl']:,.2f}`", "inline": True})
        fields.append({"name": "📈 NET PORTFÖY PnL", "value": f"```diff\n{pnl_symbol}{profit_loss:,.2f} USDT ({pnl_symbol}{profit_loss_pct:.2f}%)\n```", "inline": False})
        
        send_discord_embed("🚀 QUANTUM V5.0 (CONSERVATIVE ENGINE)", card_color, fields, f"Bakü Saati: {current_time}")
        time.sleep(300)

    except Exception as e:
        print(f"⚠️ Hata: {e}")
        time.sleep(30)
