"""Cross-check after the gate failed: lag measured as (price - average) / trend step in the planted trends (no drift trick), each version vs the EMA of HA close with the same trend lag."""
import sys, numpy as np
sys.path.insert(0, r"C:\project\options-agent"); sys.path.insert(0, r"C:\project\options-agent\tools")
from vzones import conviction_ma as CM
from conviction_eval import planted, side_flips
S=60
D=[planted(s, inject=False) for s in range(S)]
def tl(f):
    v=[]
    for o,h,l,c,lab,m in D:
        M=f(o,h,l,c); st=m["sig"]*0.25
        a=slice(m["up0"]+60,m["up0"]+150); b=slice(m["down0"]+60,m["down0"]+150)
        v.append((np.mean(c[a]-M[a])+np.mean(M[b]-c[b]))/2/st)
    return np.median(v)
def fl(f): return np.mean([side_flips(f(o,h,l,c),lab) for o,h,l,c,lab,m in D])
ha=lambda o,h,l,c: CM.heikin_ashi(o,h,l,c)[3]
emas={n:(tl(lambda o,h,l,c,n=n: CM.ema(ha(o,h,l,c),n)), fl(lambda o,h,l,c,n=n: CM.ema(ha(o,h,l,c),n))) for n in range(2,40)}
for n in (2,5,8,14,20): print("EMA",n,"trend lag %.2f flips %.2f"%emas[n])
pts=[dict(law="A",g=0.3,keep=0.6,p=1.0),dict(law="A",g=0.15,keep=0.6,p=2.0),dict(law="A",g=0.15,keep=0.4,p=2.0),
     dict(law="A",g=0.15,keep=0.6,p=1.0),dict(law="A",g=0.15,keep=0.4,p=1.0),dict(law="B",g=0.3,keep=0.6,p=1.0),dict(law="C",g=0.3,keep=0.6,p=1.0)]
for kw in pts:
    f=lambda o,h,l,c,kw=kw: CM.conviction_ma(o,h,l,c,L_fast=8,L_slow=60,**kw)[0]
    L,F=tl(f),fl(f)
    n=min(emas,key=lambda n:abs(emas[n][0]-L))
    print(kw,"trend lag %.2f flips %.2f | EMA(%d) lag %.2f flips %.2f | fewer %.0f%%"%(L,F,n,emas[n][0],emas[n][1],100*(emas[n][1]-F)/emas[n][1]))
f=lambda o,h,l,c: CM.streak_ema(o,h,l,c,8,60); L,F=tl(f),fl(f); n=min(emas,key=lambda n:abs(emas[n][0]-L))
print("StreakEMA trend lag %.2f flips %.2f | EMA(%d) flips %.2f"%(L,F,n,emas[n][1]))
