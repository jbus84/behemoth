import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import polars as pl
import numpy as np
import os
import time

# --- CONFIGURATION ---
SEQ_LEN = 30       # Lookback 30 steps (30 * 1m = 30 mins)
PRED_HORIZON = 1   # Predict next step (Next 5m Candle)
BATCH_SIZE = 1024
EPOCHS = 10
LR = 0.001
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
print(f"Using Device: {DEVICE}")

# --- DATASET ---
class MacroGraphDataset(Dataset):
    def __init__(self, parquet_file, seq_len=30, split="train"):
        print(f"Loading {parquet_file}...")
        df = pl.read_parquet(parquet_file)
        
        # Nodes: NSX, SPX, EUR, GBP, JPY, CHF, AUD, CAD, XAU
        # Features: Ret10s, Ret60s, Vol5m, Spread
        
        # Sort by timestamp just in case
        df = df.sort("timestamp")
        
        # Extract Feature Tensor [T, Nodes, Features]
        # We need to construct this carefully.
        # Columns are like: "NSXUSD_ret_10s", "NSXUSD_ret_60s"...
        
        nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
        features = ['ret_1m', 'ret_15m', 'ret_1h', 'ret_4h', 'vol_30m', 'dist_ma_200', 'spread']
        
        num_nodes = len(nodes)
        num_feats = len(features)
        total_rows = len(df)
        
        # Pre-allocate tensor
        self.data = torch.zeros((total_rows, num_nodes, num_feats), dtype=torch.float32)
        
        feature_cols = []
        for n in nodes:
            for f in features:
                feature_cols.append(f"{n}_{f}")
                
        # Fill Tensor (Polars -> Numpy -> Torch)
        # It's faster to grab all cols as numpy array and reshape
        flat_data = df.select(feature_cols).to_numpy() # [T, N*F]
        self.data = torch.tensor(flat_data, dtype=torch.float32).view(total_rows, num_nodes, num_feats)
        
        # --- FEATURE SCALING (Fix for OOS Stability) ---
        # Scale Returns (cols 0, 1) by 10,000 to match BPS units of Vol/Spread
        # This is a constant scalar, safe for OOS (stateless)
        self.data[:, :, 0] *= 10000.0 # ret_10s
        self.data[:, :, 1] *= 10000.0 # ret_60s
        
        # Targets
        # Direction: Sign of target_nsx_60s
        # Volatility: Abs of target_nsx_60s
        # Cost: NSXUSD_spread (at T+1? No, we want to filter based on current cost usually, but task said future cost... let's use current cost at T as proxy or shifted?)
        # Task said "Predict Future Spread". Dataset has "target_nsx_60s".
        # We don't have "target_spread_60s" explicitly in create_graph_dataset, 
        # BUT we have "NSXUSD_spread" valid at time T. We can use that or shift it.
        # For simplicity/robustness, let's predict *current* spread regime or next step spread. 
        # Actually create_graph_dataset didn't shift spread. Let's use NSXUSD_spread next step? 
        # Simpler: We'll output current NSX spread as "Cost" target to learn cost sensitivity? 
        # No, let's just use the NSXUSD_spread column shifted by -1 as target if we modify code, but for now
        # let's use the returns.
        
        target_ret = df.select("target_nsx_15m").to_numpy().flatten()
        target_ret = torch.tensor(target_ret, dtype=torch.float32)
        
        self.target_dir = (target_ret > 0).float() # 1=Up, 0=Down
        self.target_vol = target_ret.abs() * 10000 # Convert to bps
        
        # Approx cost target (current spread)
        self.target_cost = torch.tensor(df.select("NSXUSD_spread").to_numpy().flatten(), dtype=torch.float32)
        
        # Split
        split_idx = int(total_rows * 0.8)
        if split == "train":
            self.data = self.data[:split_idx]
            self.target_dir = self.target_dir[:split_idx]
            self.target_vol = self.target_vol[:split_idx]
            self.target_cost = self.target_cost[:split_idx]
        else:
            self.data = self.data[split_idx:]
            self.target_dir = self.target_dir[split_idx:]
            self.target_vol = self.target_vol[split_idx:]
            self.target_cost = self.target_cost[split_idx:]
            
        self.seq_len = seq_len
        self.valid_len = len(self.data) - seq_len
        
        print(f"[{split.upper()}] Data Shape: {self.data.shape} | Samples: {self.valid_len}")

    def __len__(self):
        return self.valid_len

    def __getitem__(self, idx):
        # Sliding Window
        # X: [SeqLen, Nodes, Feats]
        x = self.data[idx : idx + self.seq_len]
        
        # Y: Target at end of window (idx + seq_len)
        y_dir = self.target_dir[idx + self.seq_len - 1]
        y_vol = self.target_vol[idx + self.seq_len - 1]
        y_cost = self.target_cost[idx + self.seq_len - 1]
        
        return x, y_dir, y_vol, y_cost

# --- MODEL (ST-GNN) ---
class MacroSTGNN(nn.Module):
    def __init__(self, num_nodes=9, in_feats=7, lstm_dim=64, gat_dim=32, heads=4):
        super().__init__()
        
        # 1. Temporal Encoder (Shared LSTM across nodes)
        self.lstm = nn.LSTM(in_feats, lstm_dim, batch_first=True)
        
        # 2. GraphSAGE Layer (Simplified)
        # SAGE: node_new = W * [node_old || mean(neighbors)]
        # Since our graph is fully connected (Macro 10), "mean(neighbors)" is just "mean(all_nodes)" excluding self ideally,
        # but for efficiency we can use "mean(all_nodes)" and let the linear layer sort it out.
        
        self.sage_fc_self = nn.Linear(lstm_dim, lstm_dim)
        self.sage_fc_neigh = nn.Linear(lstm_dim, lstm_dim)
        self.sage_act = nn.ReLU()
        
        # 3. Output Heads (Readout from Target Node = Index 0 = NSXUSD)
        self.fc_shared = nn.Linear(lstm_dim * 2, 64) # Concatenation of Self + SAGE Update? Or just SAGE output?
        # Standard SAGE output is same dim. Let's start with simple Readout.
        # But we want to capture "Network Effect".
        # Let's execute SAGE update first.
        
        self.act = nn.ReLU()
        
        # Task A: Direction
        self.head_dir = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1)
        )
        
        # Task B: Volatility
        self.head_vol = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1)
        )
        
        # Task C: Cost
        self.head_cost = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1)
        )
        
        self.num_nodes = num_nodes
        self.lstm_dim = lstm_dim

    def forward(self, x):
        # x: [Batch, SeqLen, Nodes, Feats]
        B, T, N, F = x.shape
        
        # Merge Batch and Nodes for LSTM: [B*N, T, F]
        x_flat = x.view(B * N, T, F)
        
        # LSTM
        _, (h_n, _) = self.lstm(x_flat) # h_n: [1, B*N, LSTM_Dim]
        
        # Reshape to [B, N, LSTM_Dim]
        node_embs = h_n.squeeze(0).view(B, N, self.lstm_dim)
        
        # --- GraphSAGE ---
        # 1. Aggregate Neighbors (Mean of all nodes)
        # [B, LSTM_Dim]
        global_context = node_embs.mean(dim=1) 
        
        # 2. Update Target Node (Index 0 = NSXUSD)
        target_node = node_embs[:, 0, :] # [B, LSTM_Dim]
        
        # SAGE Rule: W_self * Node + W_neigh * GlobalContext
        sage_out = self.sage_act(self.sage_fc_self(target_node) + self.sage_fc_neigh(global_context))
        
        # Readout
        shared = self.act(self.fc_shared(torch.cat([sage_out, target_node], dim=1)))
        
        pred_dir = self.head_dir(shared)
        pred_vol = self.head_vol(shared)
        pred_cost = self.head_cost(shared)
        
        return pred_dir, pred_vol, pred_cost

# --- TRAINING ---
def train_model():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path):
        print("Dataset not found!")
        return

    train_ds = MacroGraphDataset(dataset_path, split="train")
    test_ds = MacroGraphDataset(dataset_path, split="test")
    
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True) # Shuffle for training
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False)
    
    model = MacroSTGNN().to(DEVICE)
    optimizer = optim.AdamW(model.parameters(), lr=LR)
    
    criterion_dir = nn.BCEWithLogitsLoss()
    criterion_reg = nn.MSELoss()
    
    print("\n>>> STARTING TRAINING (MPS/GPU) <<<")
    
    for epoch in range(EPOCHS):
        model.train()
        total_loss = 0
        
        start_time = time.time()
        
        for i, (x, y_dir, y_vol, y_cost) in enumerate(train_loader):
            x = x.to(DEVICE)
            y_dir = y_dir.to(DEVICE).unsqueeze(1)
            y_vol = y_vol.to(DEVICE).unsqueeze(1)
            y_cost = y_cost.to(DEVICE).unsqueeze(1)
            
            optimizer.zero_grad()
            
            p_dir, p_vol, p_cost = model(x)
            
            # Loss = Dir + Vol + Cost
            loss_dir = criterion_dir(p_dir, y_dir)
            loss_vol = criterion_reg(p_vol, y_vol)
            loss_cost = criterion_reg(p_cost, y_cost)
            
            loss = loss_dir + loss_vol + loss_cost
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            
            if i % 100 == 0:
                print(f"Epoch {epoch+1} | Step {i} | Loss: {loss.item():.4f}", end="\r")
                
        # Evaluate
        model.eval()
        val_acc = 0
        val_count = 0
        total_pnl = 0
        trades_count = 0
        
        # Calibration Stats
        total_pred_vol = 0
        total_real_vol = 0
        
        # Balance Stats
        total_pos_preds = 0
        total_pos_targets = 0
        
        with torch.no_grad():
            for x, y_dir, y_vol, y_cost in test_loader:
                x = x.to(DEVICE)
                y_dir = y_dir.to(DEVICE).unsqueeze(1)
                y_vol = y_vol.to(DEVICE).unsqueeze(1)
                y_cost = y_cost.to(DEVICE).unsqueeze(1)
                
                p_dir, p_vol, p_cost = model(x)
                
                # Accuracy (Direction Head)
                preds = (torch.sigmoid(p_dir) > 0.5).float()
                val_acc += (preds == y_dir).sum().item()
                val_count += len(y_dir)
                
                # Check Class Balance
                total_pos_preds += preds.sum().item()
                total_pos_targets += y_dir.sum().item()
                
                # --- PnL Simulation (Multi-Head Rule) ---
                sig_trend = torch.sigmoid(p_dir)
                
                # Rule: Conviction > 0.6 AND Predicted Vol > 1.5 * Spread Cost
                # We use y_cost (Current Spread) as the cost baseline
                
                # Trend Trade (Long)
                mask_trend = (sig_trend > 0.6) & (p_vol > y_cost * 1.5)
                
                # Revert Trade (Short)
                mask_revert = (sig_trend < 0.4) & (p_vol > y_cost * 1.5)
                
                # Calculate Realized Return (Signed BPS)
                # target_nsx_60s magnitude is y_vol. Direction is y_dir (1=Up, 0=Down).
                # Signed Ret = y_vol * (2*y_dir - 1)
                actual_ret = y_vol * (2 * y_dir - 1)
                
                # PnL = Direction * Return - Spread
                pnl_trend = mask_trend.float() * (actual_ret - y_cost)
                pnl_revert = mask_revert.float() * (-actual_ret - y_cost)
                
                batch_pnl = pnl_trend.sum() + pnl_revert.sum()
                batch_trades = mask_trend.sum() + mask_revert.sum()
                
                total_pnl += batch_pnl.item()
                trades_count += batch_trades.item()
                
                # Calibration (Filtered Trades only)
                mask_all = mask_trend | mask_revert
                if mask_all.any():
                    total_pred_vol += p_vol[mask_all].sum().item()
                    total_real_vol += y_vol[mask_all].sum().item()

        avg_pnl = total_pnl / trades_count if trades_count > 0 else 0
        avg_pred_vol = total_pred_vol / trades_count if trades_count > 0 else 0
        avg_real_vol = total_real_vol / trades_count if trades_count > 0 else 0
        
        pos_pred_pct = total_pos_preds / val_count * 100
        pos_target_pct = total_pos_targets / val_count * 100
        
        # Baseline: If we guessed the majority class
        baseline_acc = max(pos_target_pct, 100 - pos_target_pct)
        
        epoch_time = time.time() - start_time
        print(f"\nEpoch {epoch+1} Done. | Time: {epoch_time:.1f}s | Train Loss: {total_loss/len(train_loader):.4f}")
        print(f"   >> Test Acc: {val_acc/val_count*100:.2f}% (Baseline: {baseline_acc:.2f}%) | Trades: {trades_count}")
        print(f"   >> Avg PnL: {avg_pnl:.3f} bps | Vol Cal: Pred {avg_pred_vol:.2f} vs Real {avg_real_vol:.2f}")
        print(f"   >> Balance: Preds {pos_pred_pct:.1f}% Up vs Targets {pos_target_pct:.1f}% Up")
        
    # Save
    torch.save(model.state_dict(), "st_gnn_model.pth")
    print("Model Saved.")

if __name__ == "__main__":
    train_model()
