import os
import sys
import pandas as pd
import numpy as np
import yfinance as yf
import torch
import torch.nn as nn
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
REPORT_DIR = os.path.join(PROJECT_ROOT, "backtest_report")
WEIGHTS_DIR = os.path.join(PROJECT_ROOT, "weights")
os.makedirs(REPORT_DIR, exist_ok=True)


class LSTMPredictor(nn.Module):
    def __init__(self, input_size=4, hidden_size=64, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.fc(out[:, -1, :])
        return out


def fetch_stock_data(ticker="005930.KS", start="2024-01-01", end="2026-08-01"):
    print(f"[+] {ticker} 실제 주가 데이터 수집 중...")
    df = yf.download(ticker, start=start, end=end)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={'Close': 'close', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Volume': 'volume'})
    return df.dropna()


def generate_ai_signals(df: pd.DataFrame, seq_len=20, model_path=None):
    if model_path is None:
        model_path = os.path.join(WEIGHTS_DIR, "stock_model.pt")

    if os.path.exists(model_path):
        print(f"  [LSTM] 학습된 AI 모델({model_path}) 로딩 중...")
        df_feat = df.copy()
        df_feat['ret'] = df_feat['close'].pct_change()
        df_feat['sma5'] = df_feat['close'].rolling(5).mean() / df_feat['close'] - 1
        df_feat['sma20'] = df_feat['close'].rolling(20).mean() / df_feat['close'] - 1
        df_feat = df_feat.fillna(0)

        features = df_feat[['close', 'ret', 'sma5', 'sma20']].values
        mean = features.mean(axis=0)
        std = features.std(axis=0) + 1e-8
        features = (features - mean) / std

        xs = []
        for i in range(len(features)):
            if i < seq_len:
                pad = np.tile(features[0], (seq_len - i - 1, 1))
                seq = np.vstack([pad, features[:i+1]])
            else:
                seq = features[i - seq_len + 1:i + 1]
            xs.append(seq)

        x_tensor = torch.tensor(np.array(xs), dtype=torch.float32)

        model = LSTMPredictor(input_size=4, hidden_size=64, num_layers=2)
        model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
        model.eval()

        with torch.no_grad():
            probs = model(x_tensor).numpy().flatten()

        return (probs > 0.5).astype(int)
    else:
        print("  [알림] AI 모델이 없어 이동평균선 시그널을 사용합니다.")
        return np.where(df['close'].rolling(5).mean() > df['close'].rolling(20).mean(), 1, 0)


class FastGpuBacktester:
    def __init__(self, initial_capital=10000000, fee_rate=0.00015):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate

    def run_simulation(self, df: pd.DataFrame, signals: np.ndarray):
        df = df.copy()
        df['signal'] = signals
        df['market_return'] = df['close'].pct_change()
        df['strategy_return'] = df['market_return'] * df['signal'].shift(1)
        
        trades = df['signal'].diff().abs()
        df['strategy_return'] -= trades * self.fee_rate
        
        df['cum_return'] = (1 + df['strategy_return'].fillna(0)).cumprod()
        df['portfolio_value'] = self.initial_capital * df['cum_return']
        
        total_return = (df['portfolio_value'].iloc[-1] / self.initial_capital - 1) * 100

        df['peak'] = df['portfolio_value'].cummax()
        df['drawdown'] = (df['portfolio_value'] - df['peak']) / df['peak']
        mdd = df['drawdown'].min() * 100

        daily_rf = (1 + 0.035) ** (1/252) - 1
        excess_returns = df['strategy_return'].dropna() - daily_rf
        sharpe = np.sqrt(252) * (excess_returns.mean() / (excess_returns.std() + 1e-9))

        active_returns = df['strategy_return'][df['signal'].shift(1) == 1]
        win_rate = (active_returns > 0).mean() * 100 if len(active_returns) > 0 else 0.0

        metrics = {
            'total_return': total_return,
            'mdd': mdd,
            'sharpe_ratio': sharpe,
            'win_rate': win_rate
        }

        return df, metrics

    def export_report(self, df: pd.DataFrame, metrics: dict, ticker="005930.KS"):
        safe_ticker = ticker.replace(".", "_")
        pdf_path = os.path.join(REPORT_DIR, f"Backtest_{safe_ticker}.pdf")
        chart_path = os.path.join(REPORT_DIR, f"chart_{safe_ticker}.png")

        fig, ax = plt.subplots(figsize=(9, 4), dpi=300)
        ax.plot(df.index, df['portfolio_value'], label="LSTM Strategy Portfolio", color="#1f77b4", linewidth=1.5)
        ax.set_title(f"Portfolio Value Chart ({ticker})", fontsize=11, pad=8)
        ax.set_xlabel("Date", fontsize=9)
        ax.set_ylabel("Value (KRW)", fontsize=9)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.legend(loc="upper left")

        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{int(x):,}"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        fig.autofmt_xdate(rotation=25)

        plt.tight_layout()
        plt.savefig(chart_path, bbox_inches='tight')
        plt.close()

        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas

            c = canvas.Canvas(pdf_path, pagesize=letter)
            c.setFont("Helvetica-Bold", 16)
            c.drawString(54, 750, f"Backtest Performance Report ({ticker})")
            
            c.setFont("Helvetica", 10)
            c.drawString(54, 725, f"Initial Capital:   {self.initial_capital:,.0f} KRW")
            c.drawString(54, 710, f"Final Capital:     {df['portfolio_value'].iloc[-1]:,.0f} KRW")
            c.drawString(54, 695, f"Total Return:      {metrics['total_return']:.2f}%")
            c.drawString(54, 680, f"Max Drawdown (MDD): {metrics['mdd']:.2f}%")
            c.drawString(54, 665, f"Sharpe Ratio:      {metrics['sharpe_ratio']:.2f}")
            c.drawString(54, 650, f"Win Rate:          {metrics['win_rate']:.2f}%")
            
            c.setLineWidth(0.5)
            c.line(54, 638, 558, 638)

            c.drawImage(chart_path, 54, 230, width=504, height=380)
            c.save()
            print(f"[+] PDF 리포트 생성 완료: {pdf_path}")

        except ImportError:
            print("[!] reportlab 패키지가 필요합니다.")


if __name__ == "__main__":
    tickers = ["005930.KS", "AAPL", "NVDA", "TSLA"]
    backtester = FastGpuBacktester()

    for ticker in tickers:
        stock_df = fetch_stock_data(ticker=ticker, start="2024-01-01", end="2026-08-01")
        signals = generate_ai_signals(stock_df)
        result_df, metrics = backtester.run_simulation(stock_df, signals)
        
        print(f"[{ticker}] 수익률: {metrics['total_return']:.2f}% | MDD: {metrics['mdd']:.2f}% | Sharpe: {metrics['sharpe_ratio']:.2f} | 승률: {metrics['win_rate']:.2f}%")
        backtester.export_report(result_df, metrics, ticker=ticker)