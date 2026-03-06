with open("app.py", "r") as f:
    content = f.read()

content = content.replace(
    "df_hm['Year'] = df_hm.index.year",
    "df_hm['Year'] = df_hm.index.year.astype(str)"
)

with open("app.py", "w") as f:
    f.write(content)
