import sys; sys.path.insert(0,'.')
import numpy as np
from vzones.intraday.data import load_csv, rth
AGG=dict(open="first",high="max",low="min",close="last",volume="sum")
raw=rth(load_csv("data/intraday/SPY_5m.csv"))[["open","high","low","close","volume"]]; raw.index=raw.index.tz_localize(None)
def prof(b,ROWS=200,lo=None,hi=None):
    lo=b.low.min() if lo is None else lo; hi=b.high.max() if hi is None else hi; st=(hi-lo)/ROWS; pv=np.zeros(ROWS)
    for r in b.itertuples():
        q0,q1=int(np.clip((r.low-lo)//st,0,ROWS-1)),int(np.clip((r.high-lo)//st,0,ROWS-1))
        for q in range(q0,q1+1):
            ql=lo+q*st; pv[q]+=r.volume*max(0,min(r.high,ql+st)-max(r.low,ql))/max(r.high-r.low,1e-9)
    pi=int(np.argmax(pv)); a0=a1=pi; acc=pv[pi]
    while acc<.7*pv.sum() and (a0>0 or a1<ROWS-1):
        u=pv[a1+1] if a1<ROWS-1 else -1; d=pv[a0-1] if a0>0 else -1
        if u>=d: a1+=1; acc+=u
        else: a0-=1; acc+=d
    return lo+(pi+.5)*st, lo+(a1+1)*st, lo+a0*st, st
days=raw.resample("1D").agg(AGG).dropna().index
for a,b in ((-40,-20),(-25,-5),(-15,None)):
    seg=raw[(raw.index>=days[a])&((raw.index<days[b]) if b else True)]
    lo,hi=seg.low.min(),seg.high.max()
    out={tf:prof(seg.resample(tf).agg(AGG).dropna(),lo=lo,hi=hi) for tf in ("5min","15min","60min")}
    st=out["5min"][3]
    print(days[a].date(), "row=%.3f"%st, {tf:"POC %.2f VAH %.2f VAL %.2f"%v[:3] for tf,v in out.items()})
    for tf in ("15min","60min"):
        print("   %s vs 5m shift in rows: POC %.0f VAH %.0f VAL %.0f"%(tf,*[(out[tf][k]-out["5min"][k])/st for k in range(3)]))
