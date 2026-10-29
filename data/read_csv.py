import pandas as pd

df = pd.read_csv("golden_it_support_tickets.csv")

# Check eval_split distribution
print("=== eval_split value counts ===")
print(df['eval_split'].value_counts())

print("\n=== scenario_key by eval_split ===")
print(df.groupby(['eval_split', 'scenario_key']).size().reset_index(name='count'))

print("\n=== Total rows per split ===")
print(df['eval_split'].value_counts().sum(), "total rows")