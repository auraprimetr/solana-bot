import ccxt
import pandas as pd
import requests
import time
import json
import os
from datetime import datetime, timezone, timedelta

# OKX Exchange Konfigürasyonu
exchange = ccxt.okx({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})
symbol = 'SOL/USDT'
timeframe = '15m'

WEBHOOK_URL = "https://discord.com/api/webhooks/1550767474553790484/CQPIDYH4vNcCbVnmpckZt_Mk1-UAaBymKhoMNFPcgjxl44P9kWbSoj1mIpSVtM2s2pl8"
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
                # Eksik anahtar varsa varsayılanla tamamla
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
    pct = min(max((val - min_val) / (max_val - min_val), 0), 1)
    filled = int(round(pct * length))
    return "🟩" * filled + "⬛" * (length - filled)

def make_ratio_bar(ratio, length=10):
    pct = min(max(ratio / 2.0, 0), 1)
    filled = int(round(pct * length))
    return "🟦" * filled + "🟧" * (length - filled)

def send_discord_embed(title, color_code, fields, footer_text):
    """
    Discord Webhook Gönderici.
    NOT: 'flags': 4 KESİNLİKLE KULLANILMIYOR (Embed kartlarının gizlenmesini önlemek için).
    """
    embed = {
        "title": title,
        "color": color_code,
        "fields": fields,
        "footer": {"text": footer_text},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    payload = {
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
            print(f"⚠️ Discord Webhook İsteği Başarısız! Kod: {response.status_code}, Cevap: {response.text}")
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
    
    # Sıfıra bölünme hatasını engelleme
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
    
    return df

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
            "value": f"```diff\n[GÜNLÜK BOT AUDİT İMZA KODU: {today_str}]\nTrades: {portfolio['daily_trades_count']} | WinRate: {win_rate:.1f}% | TotalPn
