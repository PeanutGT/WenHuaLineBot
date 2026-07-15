import pandas as pd
import json

df = pd.read_excel('課表.xlsx')
df = df.astype(str)

data = {
    'columns': df.columns.tolist(),
    'data': df.head(5).to_dict('records')
}

with open('schedule.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
