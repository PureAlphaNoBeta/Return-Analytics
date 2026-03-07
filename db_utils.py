import pandas as pd
import sqlite3

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timeseries (
            Date DATE,
            Asset TEXT,
            Value REAL,
            Category TEXT,
            PRIMARY KEY (Date, Asset, Category)
        )
    ''')
    conn.commit()
    conn.close()

def clear_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS timeseries")
    conn.commit()
    conn.close()
    init_db(db_path)

def update_db_table(df_new, category, db_path):
    """
    Validates and uploads a wide dataframe to a normalized SQLite table.
    """
    if df_new.empty:
        return

    df_new = df_new.copy()
    df_new.index.name = 'Date'

    # Validation: Sort dates, remove duplicates, drop NaNs across entire row
    df_new = df_new.sort_index()
    df_new = df_new[~df_new.index.duplicated(keep='last')]
    df_new = df_new.dropna(how='all')

    # Melt wide to long
    df_long = df_new.reset_index().melt(id_vars=['Date'], var_name='Asset', value_name='Value')
    df_long['Category'] = category
    df_long = df_long.dropna(subset=['Value'])

    conn = sqlite3.connect(db_path)
    # Upload to a temporary table
    df_long.to_sql('temp_timeseries', conn, if_exists='replace', index=False)

    # Merge into main table using INSERT OR REPLACE (SQLite)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO timeseries (Date, Asset, Value, Category)
        SELECT Date, Asset, Value, Category FROM temp_timeseries
    ''')
    cursor.execute("DROP TABLE temp_timeseries")
    conn.commit()
    conn.close()

def get_data_by_category(category, db_path):
    """
    Retrieves data for a specific category and pivots it back to wide format.
    """
    conn = sqlite3.connect(db_path)
    try:
        query = f"SELECT Date, Asset, Value FROM timeseries WHERE Category = '{category}'"
        df_long = pd.read_sql(query, conn, parse_dates=['Date'])
        if df_long.empty:
             return pd.DataFrame()
        df_wide = df_long.pivot(index='Date', columns='Asset', values='Value')
        df_wide.index = pd.to_datetime(df_wide.index)
        return df_wide.sort_index()
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()