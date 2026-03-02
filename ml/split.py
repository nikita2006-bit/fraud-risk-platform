import pandas as pd

input_file = r"C:\Users\nikita\Documents\Fraud_Risk_Project\fraud-risk-platform\data\raw\PS_20174392719_1491204439457_log.csv"

df = pd.read_csv(input_file)
split_index = int(len(df) * 0.8)

train = df[:split_index]
test = df[split_index:]

train.to_csv("train.csv", index=False)
test.to_csv("test.csv", index=False)

print("Done")