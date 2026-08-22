import os
import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
import numpy as np
import yfinance as yf

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
WEIGHTS_DIR = os.path.join(PROJECT_ROOT, "weights")
os.makedirs(WEIGHTS_DIR, exist_ok=True)


# PyTorch LSTM 모델 정의
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


def create_sequences(features, labels, seq_length=20):
    xs, ys = [], []
    for i in range(len(features) - seq_length):
        xs.append(features[i:i + seq_length])
        ys.append(labels[i + seq_length])
    return np.array(xs), np.array(ys)


def prepare_data(ticker="005930.KS", start="2020-01-01", end="2024-01-01", seq_len=20):
    print(f"[+] LSTM 학습용 데이터 수집 중 ({ticker})...")
    df = yf.download(ticker, start=start, end=end)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={'Close': 'close'}).dropna()

    df['ret'] = df['close'].pct_change()
    df['sma5'] = df['close'].rolling(5).mean() / df['close'] - 1
    df['sma20'] = df['close'].rolling(20).mean() / df['close'] - 1
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    
    df = df.dropna()
    features = df[['close', 'ret', 'sma5', 'sma20']].values
    labels = df['target'].values

    mean = features.mean(axis=0)
    std = features.std(axis=0) + 1e-8
    features = (features - mean) / std

    X, y = create_sequences(features, labels, seq_length=seq_len)
    return torch.tensor(X, dtype=torch.float32), torch.tensor(y, dtype=torch.float32).unsqueeze(1)


def train_model():
    seq_len = 20
    X, y = prepare_data(seq_len=seq_len)
    model = LSTMPredictor(input_size=4, hidden_size=64, num_layers=2)
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    print("[+] LSTM AI 모델 학습 시작...")
    model.train()
    for epoch in range(1, 101):
        optimizer.zero_grad()
        outputs = model(X)
        loss = criterion(outputs, y)
        loss.backward()
        optimizer.step()

        if epoch % 20 == 0:
            print(f"    Epoch [{epoch}/100], Loss: {loss.item():.4f}")

    save_path = os.path.join(WEIGHTS_DIR, "stock_model.pt")
    torch.save(model.state_dict(), save_path)
    print(f"[+] LSTM AI 모델 저장 완료: {save_path}")


if __name__ == "__main__":
    train_model()