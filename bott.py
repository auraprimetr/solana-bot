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
timeframe = '15m'

# Yeni Webhook URL'niz
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
        "last_daily_report_date": ""
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
            print(f"⚠️ Portföy dosyası okunurken hata oluştu, yeni veri oluşturuluyor: {e}")
    return default_data

def save_portfolio(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Veri kaydetme hatası: {e}")

portfolio = load_portfolio()
save_portfolio(portfolio)

# Strateji Parametreleri
trade_amount_usd = 2500.0
fee_rate = 0.001           # %0.1 Komisyon
hard_stop_loss_pct = 0.02  # -%2 Stop Loss
trailing_stop_pct = 0.015   # -%1.5 Trailing Stop
take_profit_pct = 0.04      # +%4 Take Profit

def make_gauge_bar(val, min_val=0, max_val=100, length=10):
    if math.isnan(val):
        val = 50
    pct = min(max((val - min_val) / (max_val - min_val), 0), 1)
    filled = int(round(pct * length))
    return "🟩" * filled + "⬛" * (length - filled)

def make_ratio_bar(ratio, length=10):
    if math.isnan(ratio):
        ratio = 1.0
    pct = min(max(ratio / 2.0, 0), 1)
    filled = int(round(pct * length))
    return "🟦" * filled + "🟧" * (length - filled)

def send_discord_embed(title, color_code, fields, footer_text):
    """
    Discord Webhook Gönderici.
    Content eklenerek mesajın izin sıkıntılarında bile boş düşmesi engellenmiştir.
    """
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
        response = requests.post(
            WEBHOOK_URL, 
            json=payload, 
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code not in [200, 204]:
            print(f"⚠️ Discord Webhook Hatası! Kod: {response.status_code}, Cevap: {response.text}")
    except Exception as e:
        print(f"❌ Discord Bağlantı Hatası: {e}")

def get_fear_and_greed_index():
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5).json()
        value = int(resp['data'][0]['value'])
        classification = resp['data'][0]['value_classification']
        return value, classification
    except Exception:
        return 50, "Neutral"

def add_indicators(df):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    
    loss = loss.replace(0, 1e-9)
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    df['bb_mid'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + (df['bb_std'] * 2)
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
                f"• **Günün Realizə Olunan PnL-i:** `{daily_pnl_sym}${portfolio['daily_pnl']:,.2f}`\n"
                f"• **Ümumi Qazanma Oranı (Win Rate):** `{win_rate:.1f}%`"
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
        },
        {
            "name": "🤖 AI BOT AUDİT QEYDİ",
            "value": f"```diff\n[GÜNLÜK BOT AUDİT İMZA KODU: {today_str}]\nTrades: {portfolio['daily_trades_count']} | WinRate: {win_rate:.1f}% | TotalPnL: {pnl_sym}${total_pnl:.2f}\n```",
            "inline": False
        }
    ]
    
    send_discord_embed(
        f"📊 GÜNLÜK BOT AUDİT HESABATI ({today_str})",
        0x00FFFF,
        fields,
        "Bu mesaj hər gün avtomatik yaradılır."
    )
    
    portfolio['daily_trades_count'] = 0
    portfolio['daily_pnl'] = 0.0
    portfolio['last_daily_report_date'] = today_str
    save_portfolio(portfolio)

print("=" * 60)
print("🚀 QUANTUM PRO TERMINAL V4.3 - STABLE RUNTIME ENGINE")
print("=" * 60)

# KESİNTİSİZ ÇALIŞMA DÖNGÜSÜ
while True:
    try:
        az_timezone = timezone(timedelta(hours=4))
        now_az = datetime.now(az_timezone)
        today_str = now_az.strftime('%Y-%m-%d')
        
        # Piyasa Verilerinin Alınması
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
        current_macd = float(df['macd'].iloc[-1])
        current_signal = float(df['macd_signal'].iloc[-1])
        current_atr = float(df['atr'].iloc[-1])
        bb_lower = float(df['bb_lower'].iloc[-1])
        bb_upper = float(df['bb_upper'].iloc[-1])
        
        # Günlük Audit Kontrolü
        if portfolio['last_daily_report_date'] != today_str and now_az.hour == 0:
            send_daily_audit_report(current_price)
        
        signal_status = "⏸️ NÖTR (Piyasalar İzleniyor...)"
        card_color = 0x2B2D31
        
        # ALIM KOŞULU
        technical_buy = (current_rsi < 38 or current_price <= bb_lower) and book_ratio > 0.85 and fng_value < 80
        
        if technical_buy and portfolio['cash_usd'] >= trade_amount_usd:
            fee = trade_amount_usd * fee_rate
            net_investment = trade_amount_usd - fee
            bought_sol = net_investment / current_price
            
            portfolio['sol_held'] += bought_sol
            portfolio['cash_usd'] -= trade_amount_usd
            portfolio['buy_price'] = current_price
            portfolio['highest_price'] = current_price
            save_portfolio(portfolio)
            
            signal_status = f"⚡ ALIM GERÇEKLEŞTİ! (${current_price:.2f} USDT)"
            card_color = 0x00FF88
            
        elif portfolio['sol_held'] > 0:
            if current_price > portfolio['highest_price']:
                portfolio['highest_price'] = current_price
                save_portfolio(portfolio)
            
            profit_pct = (current_price - portfolio['buy_price']) / portfolio['buy_price']
            drop_from_peak = (portfolio['highest_price'] - current_price) / portfolio['highest_price']
            
            trade_closed = False
            trade_pnl = 0.0
            
            # SATIM KOŞULLARI
            if profit_pct >= take_profit_pct:
                gross_usd = portfolio['sol_held'] * current_price
                fee = gross_usd * fee_rate
                received = gross_usd - fee
                trade_pnl = received - trade_amount_usd
                
                portfolio['cash_usd'] += received
                portfolio['realized_pnl'] += trade_pnl
                portfolio['daily_pnl'] += trade_pnl
                portfolio['total_trades'] += 1
                portfolio['daily_trades_count'] += 1
                portfolio['win_trades'] += 1
                trade_closed = True
                signal_status = f"🎯 TAKE-PROFIT! (+{profit_pct*100:.2f}%)"
                card_color = 0xFFD700
                
            elif drop_from_peak >= trailing_stop_pct and profit_pct > 0.005:
                gross_usd = portfolio['sol_held'] * current_price
                fee = gross_usd * fee_rate
                received = gross_usd - fee
                trade_pnl = received - trade_amount_usd
                
                portfolio['cash_usd'] += received
                portfolio['realized_pnl'] += trade_pnl
                portfolio['daily_pnl'] += trade_pnl
                portfolio['total_trades'] += 1
                portfolio['daily_trades_count'] += 1
                portfolio['win_trades'] += 1
                trade_closed = True
                signal_status = f"🏹 TRAILING STOP! Zirveden Satıldı (+{profit_pct*100:.2f}%)"
                card_color = 0xFFA500
                
            elif profit_pct <= -hard_stop_loss_pct:
                gross_usd = portfolio['sol_held'] * current_price
                fee = gross_usd * fee_rate
                received = gross_usd - fee
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
                
            elif current_rsi > 65 or current_macd < current_signal:
                gross_usd = portfolio['sol_held'] * current_price
                fee = gross_usd * fee_rate
                received = gross_usd - fee
                trade_pnl = received - trade_amount_usd
                
                portfolio['cash_usd'] += received
                portfolio['realized_pnl'] += trade_pnl
                portfolio['daily_pnl'] += trade_pnl
                portfolio['total_trades'] += 1
                portfolio['daily_trades_count'] += 1
                if trade_pnl >= 0:
                    portfolio['win_trades'] += 1
                else:
                    portfolio['loss_trades'] += 1
                trade_closed = True
                signal_status = "🔴 İNDİKATÖR SİNYALİ İLE SATILDI"
                card_color = 0xFF0055

            if trade_closed:
                portfolio['sol_held'] = 0.0
                portfolio['buy_price'] = 0.0
                portfolio['highest_price'] = 0.0
                save_portfolio(portfolio)

        total_portfolio_value = portfolio['cash_usd'] + (portfolio['sol_held'] * current_price)
        profit_loss = total_portfolio_value - portfolio['initial_balance']
        profit_loss_pct = (profit_loss / portfolio['initial_balance']) * 100
        pnl_symbol = "+" if profit_loss >= 0 else ""
        
        total_tr = portfolio['total_trades']
        win_tr = portfolio['win_trades']
        win_rate = (win_tr / total_tr * 100) if total_tr > 0 else 0.0
        
        rsi_bar = make_gauge_bar(current_rsi)
        rsi_state = "Aşırı Satış 🟢" if current_rsi < 38 else ("Aşırı Alış 🔴" if current_rsi > 70 else "Nötr 🟡")
        macd_trend = "🟢 Boğa" if current_macd > current_signal else "🔴 Ayı"
        fng_bar = make_gauge_bar(fng_value)
        
        current_time = now_az.strftime('%H:%M:%S')
        
        fields = [
            {
                "name": "📌 CANLI PİYASA FİYATI",
                "value": f"```ansi\n\x1b[1;36m${current_price:,.2f} USDT\x1b[0m \x1b[0;33m(Volatilite ATR: ±${current_atr:.2f})\x1b[0m\n```",
                "inline": False
            },
            {
                "name": "📊 İNDİKATÖR HUD & SİNYALLER",
                "value": (
                    f"**RSI (14):** `{current_rsi:.1f}` {rsi_state}\n"
                    f"`[{rsi_bar}]`\n\n"
                    f"**MACD Trend:** {macd_trend}\n"
                    f"**Bollinger Alt:** `${bb_lower:.2f}` | **Üst:** `${bb_upper:.2f}`"
                ),
                "inline": True
            },
            {
                "name": "🐋 DERİNLİK & DERECELER",
                "value": (
                    f"**Balina Baskısı:** `{book_ratio:.2f}` *(Bids/Asks)*\n"
                    f"`[{make_ratio_bar(book_ratio)}]`\n\n"
                    f"**Piyasa Duygusu:** `{fng_value}/100` ({fng_class})\n"
                    f"`[{fng_bar}]`"
                ),
                "inline": True
            },
            {
                "name": "⚡ ALGORİTMA DURUMU",
                "value": f"```ansi\n\x1b[1;33m{signal_status}\x1b[0m\n```",
                "inline": False
            }
        ]
        
        if portfolio['sol_held'] > 0:
            tp_target = portfolio['buy_price'] * (1 + take_profit_pct)
            sl_target = portfolio['buy_price'] * (1 - hard_stop_loss_pct)
            current_unrealized = (current_price - portfolio['buy_price']) * portfolio['sol_held']
            current_unrealized_pct = (current_price - portfolio['buy_price']) / portfolio['buy_price'] * 100
            unreal_sym = "+" if current_unrealized >= 0 else ""
            
            position_hud = (
                f"```yaml\n"
                f"Giriş Fiyatı   : ${portfolio['buy_price']:.2f}\n"
                f"Zirve Fiyatı   : ${portfolio['highest_price']:.2f}\n"
                f"🎯 Take-Profit  : ${tp_target:.2f} (+4.0%)\n"
                f"🛑 Stop-Loss    : ${sl_target:.2f} (-2.0%)\n"
                f"Anlık Kar/Zarar: {unreal_sym}${current_unrealized:.2f} ({unreal_sym}{current_unrealized_pct:.2f}%)\n"
                f"```"
            )
            fields.append({"name": "🎯 AKTİF POZİSYON MONİTÖRÜ (HUD)", "value": position_hud, "inline": False})
            if card_color == 0x2B2D31:
                card_color = 0x00FF88 if current_unrealized >= 0 else 0xFF0055
        
        stats_block = (
            f"💵 **Nakit Dolar:** `${portfolio['cash_usd']:,.2f}`\n"
            f"🪙 **Mevcut SOL:** `{portfolio['sol_held']:.4f} SOL`\n"
            f"💼 **Toplam Portföy:** `${total_portfolio_value:,.2f}`"
        )
        fields.append({"name": "💼 PORTFÖY ÖZETİ", "value": stats_block, "inline": True})
        
        perf_block = (
            f"🏆 **İşlemler:** `{total_tr}` *(Kazanılan: `{win_tr}`)*\n"
            f"🎯 **Kazanma Oranı:** `{win_rate:.1f}%`\n"
            f"💰 **Realize PnL:** `${portfolio['realized_pnl']:,.2f}`"
        )
        fields.append({"name": "📊 PERFORMANS METRİKLERİ", "value": perf_block, "inline": True})
        
        fields.append({
            "name": "📈 TOPLAM NET KAR / ZARAR (PnL)", 
            "value": f"```diff\n{pnl_symbol}{profit_loss:,.2f} USDT ({pnl_symbol}{profit_loss_pct:.2f}%)\n```", 
            "inline": False
        })
        
        title = "🚀 QUANTUM PRO TERMINAL V4.3 (PURE ALGO ENGINE)"
        footer = f"Bakü Saati: {current_time} | OKX Spot Engine"
        
        send_discord_embed(title, card_color, fields, footer)
        print(f"[{current_time}] Dashboard Yenilendi - Fiyat: ${current_price:.2f}")
        
        time.sleep(300)

    except Exception as e:
        print(f"⚠️ Hata Oluştu: {e}")
        time.sleep(30)
