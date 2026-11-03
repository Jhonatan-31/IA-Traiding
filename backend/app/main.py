"""Public Binance market monitoring, paper-only, no private API keys or live trades."""
import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from contextlib import asynccontextmanager
import httpx
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI

DATABASE_URL=os.environ['DATABASE_URL']
BASE='https://data-api.binance.vision/api/v3'
LIMIT=max(1,min(500,int(os.environ.get('SCAN_LIMIT','25'))))
PERIOD=max(120,int(os.environ.get('SCAN_EVERY_SECONDS','3600')))
START=Decimal('1000')
FEE=Decimal('0.001')
SLIP=Decimal('0.001')


def db():
    return psycopg.connect(DATABASE_URL,row_factory=dict_row)


def setup():
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS account(id INTEGER PRIMARY KEY,cash NUMERIC NOT NULL)')
        c.execute('INSERT INTO account(id,cash) VALUES(1,%s) ON CONFLICT DO NOTHING',(START,))
        c.execute('''CREATE TABLE IF NOT EXISTS positions(symbol TEXT PRIMARY KEY,qty NUMERIC NOT NULL,cost NUMERIC NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS trades(id BIGSERIAL PRIMARY KEY, at TIMESTAMPTZ DEFAULT NOW(), symbol TEXT NOT NULL,side TEXT NOT NULL, qty NUMERIC NOT NULL,price NUMERIC NOT NULL,candle_ms BIGINT NOT NULL, UNIQUE(symbol,side,candle_ms))''')
        c.execute('''CREATE TABLE IF NOT EXISTS scans(id BIGSERIAL PRIMARY KEY,at TIMESTAMPTZ DEFAULT NOW(), markets INT,errors INT,equity NUMERIC)''')
        c.execute('''CREATE TABLE IF NOT EXISTS prices(symbol TEXT PRIMARY KEY,price NUMERIC NOT NULL, at TIMESTAMPTZ DEFAULT NOW())''')


def signal(bars):
    if len(bars)<51:return 'HOLD'
    x=[Decimal(str(r[4])) for r in bars]
    a=sum(x[-10:])/10;b=sum(x[-50:])/50
    pa=sum(x[-11:-1])/10;pb=sum(x[-51:-1])/50
    if pa<=pb and a>b:return 'BUY'
    if pa>=pb and a<b:return 'SELL'
    return 'HOLD'


async def get(client,path,**params):
    r=await client.get(BASE+path,params=params)
    if r.status_code in (418,429):raise RuntimeError('API rate limited: pause collector')
    r.raise_for_status()
    return r.json()


async def cycle(client):
    info=await get(client,'/exchangeInfo')
    candidates={s['symbol'] for s in info['symbols'] if s.get('status')=='TRADING' and s.get('quoteAsset')=='USDT' and s.get('isSpotTradingAllowed')}
    tickers=await get(client,'/ticker/24hr')
    eligible=sorted(((Decimal(str(t.get('quoteVolume',0))),t['symbol']) for t in tickers if t['symbol'] in candidates and Decimal(str(t.get('quoteVolume',0)))>=Decimal('1000000')),reverse=True)
    selected=[s for _,s in eligible[:LIMIT]]
    with db() as c:
        held=[r['symbol'] for r in c.execute('SELECT symbol FROM positions')]
    selected=list(dict.fromkeys(selected+held))
    errors=0; scanned=0
    for symbol in selected:
        try:
            rows=await get(client,'/klines',symbol=symbol,interval='1h',limit=55)
            now=int(datetime.now(timezone.utc).timestamp()*1000)
            bars=[r for r in rows if int(r[6])<now]
            if len(bars)<51:continue
            end=int(bars[-1][6]);price=Decimal(str(bars[-1][4]));side=signal(bars)
            with db() as c:
                c.execute('INSERT INTO prices(symbol,price) VALUES(%s,%s) ON CONFLICT(symbol) DO UPDATE SET price=excluded.price,at=NOW()', (symbol,price))
                past=c.execute('SELECT 1 FROM trades WHERE symbol=%s AND side=%s AND candle_ms=%s',(symbol,side,end)).fetchone()
                position=c.execute('SELECT * FROM positions WHERE symbol=%s',(symbol,)).fetchone()
                if side=='BUY' and not past and not position:
                    n=c.execute('SELECT COUNT(*) AS n FROM positions').fetchone()['n'];cash=c.execute('SELECT cash FROM account WHERE id=1').fetchone()['cash']
                    budget=min(Decimal('25'),cash)
                    if n<10 and budget>=10:
                        fill=price*(1+SLIP);qty=(budget*(1-FEE))/fill
                        c.execute('UPDATE account SET cash=cash-%s WHERE id=1',(budget,))
                        c.execute('INSERT INTO positions VALUES(%s,%s,%s)',(symbol,qty,budget))
                        c.execute('INSERT INTO trades(symbol,side,qty,price,candle_ms) VALUES(%s,%s,%s,%s,%s)',(symbol,'BUY',qty,fill,end))
                elif side=='SELL' and not past and position:
                    qty=position['qty'];fill=price*(1-SLIP);proceeds=qty*fill*(1-FEE)
                    c.execute('UPDATE account SET cash=cash+%s WHERE id=1',(proceeds,))
                    c.execute('DELETE FROM positions WHERE symbol=%s',(symbol,))
                    c.execute('INSERT INTO trades(symbol,side,qty,price,candle_ms) VALUES(%s,%s,%s,%s,%s)',(symbol,'SELL',qty,fill,end))
            scanned+=1
        except (httpx.HTTPError,ValueError,KeyError,IndexError) as e:
            errors+=1
            print('MARKET_ERROR',symbol,str(e),flush=True)
        await asyncio.sleep(.15)
    # Update all holdings with public ticker prices; unknown values lead to null equity.
    allprices=await get(client,'/ticker/price')
    lookup={x['symbol']:Decimal(str(x['price'])) for x in allprices}
    with db() as c:
        holdings=list(c.execute('SELECT * FROM positions'))
        cash=c.execute('SELECT cash FROM account WHERE id=1').fetchone()['cash']
        equity=cash+sum(p['qty']*lookup[p['symbol']] for p in holdings) if all(p['symbol'] in lookup for p in holdings) else None
        c.execute('INSERT INTO scans(markets,errors,equity) VALUES(%s,%s,%s)',(scanned,errors,equity))
    print('PAPER_ONLY markets',scanned,'errors',errors,'equity',equity,flush=True)


async def work():
    async with httpx.AsyncClient(timeout=25,headers={'User-Agent':'ResearchPaperBot/0.3'}) as client:
        while True:
            try:await cycle(client)
            except Exception as exc:print('COLLECTOR_ERROR',type(exc).__name__,str(exc),flush=True)
            await asyncio.sleep(PERIOD)


@asynccontextmanager
async def lifespan(app):
    for attempt in range(30):
        try:setup();break
        except psycopg.OperationalError:
            if attempt==29:raise
            await asyncio.sleep(2)
    yield

app=FastAPI(title='AI Trading Bot - PAPER ONLY',lifespan=lifespan)


def serial(rows):
    def normalize(x):
        if isinstance(x,Decimal):return float(x)
        if isinstance(x,datetime):return x.isoformat()
        if isinstance(x,dict):return {k:normalize(v) for k,v in x.items()}
        if isinstance(x,list):return [normalize(v) for v in x]
        return x
    return normalize(rows)


@app.get('/api/overview')
def overview():
    with db() as c:
        cash=c.execute('SELECT cash FROM account WHERE id=1').fetchone()['cash']
        scan=c.execute('SELECT * FROM scans ORDER BY id DESC LIMIT 1').fetchone()
        pos=c.execute('SELECT COUNT(*) AS n FROM positions').fetchone()['n']
        trades=c.execute('SELECT COUNT(*) AS n FROM trades').fetchone()['n']
    return serial({'mode':'PAPER_ONLY','cash':cash,'latest':scan,'positions':pos,'trades':trades})


@app.get('/api/trades')
def trades():
    with db() as c:return serial(list(c.execute('SELECT * FROM trades ORDER BY id DESC LIMIT 50')))


@app.get('/api/positions')
def positions():
    with db() as c:return serial(list(c.execute('SELECT p.*,pr.price,p.qty*pr.price AS market_value FROM positions p LEFT JOIN prices pr USING(symbol) ORDER BY symbol')))


@app.get('/api/scans')
def scans():
    with db() as c:return serial(list(c.execute('SELECT * FROM (SELECT * FROM scans ORDER BY id DESC LIMIT 100) x ORDER BY id')))


@app.get('/api/health')
def health():return {'status':'ok','mode':'PAPER_ONLY'}
