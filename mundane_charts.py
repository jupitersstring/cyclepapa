"""
Mundane charts database — country foundings + stock-exchange foundings.

Two collections:
  COUNTRIES — national charts used in mundane astrology
  EXCHANGES — stock-exchange founding/first-trade dates

Format: ticker -> {date, label, ETF (for equity-market reference), notes}
Dates use the most commonly accepted mundane chart.
"""

# Country charts (most accepted in mundane astrology literature)
COUNTRIES = {
    "USA":      {"date":"1776-07-04","label":"USA Independence (Sibly)","etf":"SPY","capital":"Philadelphia"},
    "USA_GB":   {"date":"1776-07-04","label":"USA Gemini-rising (Brennan)","etf":"SPY"},
    "UK":       {"date":"1801-01-01","label":"UK Act of Union","etf":"EWU","capital":"London"},
    "GERMANY":  {"date":"1990-10-03","label":"Germany Reunification","etf":"EWG","capital":"Berlin"},
    "FRANCE":   {"date":"1958-10-04","label":"France Fifth Republic","etf":"EWQ","capital":"Paris"},
    "ITALY":    {"date":"1946-06-02","label":"Italy Republic","etf":"EWI","capital":"Rome"},
    "SPAIN":    {"date":"1978-12-06","label":"Spain Constitution","etf":"EWP","capital":"Madrid"},
    "JAPAN":    {"date":"1947-05-03","label":"Japan Constitution","etf":"EWJ","capital":"Tokyo"},
    "CHINA":    {"date":"1949-10-01","label":"PRC Founding","etf":"FXI","capital":"Beijing"},
    "INDIA":    {"date":"1947-08-15","label":"India Independence","etf":"INDA","capital":"New Delhi"},
    "RUSSIA":   {"date":"1991-12-25","label":"Russian Federation","etf":"RSX","capital":"Moscow"},
    "BRAZIL":   {"date":"1822-09-07","label":"Brazil Independence","etf":"EWZ","capital":"Brasilia"},
    "MEXICO":   {"date":"1810-09-16","label":"Mexico Independence","etf":"EWW","capital":"Mexico City"},
    "CANADA":   {"date":"1867-07-01","label":"Canadian Confederation","etf":"EWC","capital":"Ottawa"},
    "AUSTRALIA":{"date":"1901-01-01","label":"Australian Federation","etf":"EWA","capital":"Canberra"},
    "S_KOREA":  {"date":"1948-08-15","label":"South Korea Founding","etf":"EWY","capital":"Seoul"},
    "HONG_KONG":{"date":"1997-07-01","label":"HK Handover to PRC","etf":"EWH","capital":"Hong Kong"},
    "SWITZERLAND":{"date":"1848-09-12","label":"Swiss Federal Constitution","etf":"EWL","capital":"Bern"},
    "NETHERLANDS":{"date":"1815-03-16","label":"Netherlands UK","etf":"EWN","capital":"Amsterdam"},
    "S_AFRICA": {"date":"1994-04-27","label":"S Africa Post-Apartheid","etf":"EZA","capital":"Pretoria"},
    "ISRAEL":   {"date":"1948-05-14","label":"Israel Founding","etf":"EIS","capital":"Jerusalem"},
    "TAIWAN":   {"date":"1912-01-01","label":"ROC Founding","etf":"EWT","capital":"Taipei"},
    "TURKEY":   {"date":"1923-10-29","label":"Turkey Republic","etf":"TUR","capital":"Ankara"},
    "POLAND":   {"date":"1989-04-04","label":"Poland Round-Table","etf":"EPOL","capital":"Warsaw"},
    "ARGENTINA":{"date":"1816-07-09","label":"Argentina Independence","etf":"ARGT","capital":"Buenos Aires"},
    "EU":       {"date":"1993-11-01","label":"EU Maastricht in force","etf":"VGK","capital":"Brussels"},
    "EURO":     {"date":"1999-01-01","label":"Euro currency","etf":"FXE"},
    "SAUDI":    {"date":"1932-09-23","label":"Saudi Arabia unification","etf":"KSA","capital":"Riyadh"},
    "UAE":      {"date":"1971-12-02","label":"UAE Federation","etf":"UAE","capital":"Abu Dhabi"},
    "INDONESIA":{"date":"1945-08-17","label":"Indonesia Independence","etf":"EIDO","capital":"Jakarta"},
    "VIETNAM":  {"date":"1945-09-02","label":"Vietnam Independence","etf":"VNM","capital":"Hanoi"},
    "PHILIPPINES":{"date":"1946-07-04","label":"Philippines Independence","etf":"EPHE","capital":"Manila"},
    "THAILAND": {"date":"1932-06-24","label":"Thailand Constitution","etf":"THD","capital":"Bangkok"},
    "MALAYSIA": {"date":"1957-08-31","label":"Malaysia Independence","etf":"EWM","capital":"Kuala Lumpur"},
    "SINGAPORE":{"date":"1965-08-09","label":"Singapore Independence","etf":"EWS","capital":"Singapore"},
}

# Stock exchange charts (founding or first-trade dates)
EXCHANGES = {
    "NYSE":     {"date":"1792-05-17","label":"NYSE Buttonwood Agreement","etf":"NYC","tradeable":"DIA","capital":"New York"},
    "NASDAQ":   {"date":"1971-02-08","label":"NASDAQ founded","etf":"QQQ","capital":"New York"},
    "LSE":      {"date":"1801-03-03","label":"LSE Modern formation","etf":"EWU","capital":"London"},
    "TSE":      {"date":"1878-05-15","label":"Tokyo Stock Exchange","etf":"EWJ","capital":"Tokyo"},
    "HKEX":     {"date":"1986-04-02","label":"HKEX unified","etf":"EWH","capital":"Hong Kong"},
    "SSE":      {"date":"1990-11-26","label":"Shanghai Stock Exchange","etf":"FXI","capital":"Shanghai"},
    "SZSE":     {"date":"1990-12-01","label":"Shenzhen Stock Exchange","etf":"ASHS","capital":"Shenzhen"},
    "BSE":      {"date":"1875-07-09","label":"Bombay Stock Exchange","etf":"INDA","capital":"Mumbai"},
    "NSE":      {"date":"1994-11-03","label":"National Stock Exchange India","etf":"INDA","capital":"Mumbai"},
    "TSX":      {"date":"1861-11-06","label":"Toronto Stock Exchange","etf":"EWC","capital":"Toronto"},
    "ASX":      {"date":"1987-04-01","label":"ASX (modern unified)","etf":"EWA","capital":"Sydney"},
    "EURONEXT": {"date":"2000-09-22","label":"Euronext founded","etf":"FEZ","capital":"Paris/Amsterdam"},
    "DBAG":     {"date":"1992-12-15","label":"Deutsche Boerse","etf":"EWG","capital":"Frankfurt"},
    "SIX":      {"date":"1995-08-22","label":"SIX Swiss Exchange","etf":"EWL","capital":"Zurich"},
    "B3":       {"date":"1890-08-23","label":"BOVESPA founded","etf":"EWZ","capital":"Sao Paulo"},
    "BMV":      {"date":"1894-10-31","label":"Bolsa Mexicana","etf":"EWW","capital":"Mexico City"},
    "KRX":      {"date":"1956-03-03","label":"Korea Exchange","etf":"EWY","capital":"Seoul"},
    "TADAWUL":  {"date":"2007-03-19","label":"Tadawul Saudi","etf":"KSA","capital":"Riyadh"},
    "MOEX":     {"date":"2011-12-19","label":"Moscow Exchange","etf":"RSX","capital":"Moscow"},
    "JSE":      {"date":"1887-11-08","label":"Johannesburg Stock Exchange","etf":"EZA","capital":"Johannesburg"},
    "TWSE":     {"date":"1962-02-09","label":"Taiwan Stock Exchange","etf":"EWT","capital":"Taipei"},
    "BIST":     {"date":"1986-01-03","label":"Borsa Istanbul","etf":"TUR","capital":"Istanbul"},
}

# Sector mapping for mundane charts (for macro_regime — country charts treat
# as broad-market equity index, exchange charts the same)
MUNDANE_MODERN_SECTOR = "INDEX"  # generic macro tag
