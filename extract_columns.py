import pandas as pd
import json

try:
    df = pd.read_excel('excels/學生資料.xlsx')
    data = {
        'columns': df.columns.tolist(),
        'row1': df.head(1).to_dict('records')
    }
    with open('excels_meta.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
except Exception as e:
    with open('excels_meta.json', 'w', encoding='utf-8') as f:
        json.dump({"error": str(e)}, f, ensure_ascii=False, indent=2)
