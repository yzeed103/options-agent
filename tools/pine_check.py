"""Static checks for a Pine v5 script (beyond syntax): duplicates, use-before-define / undefined names,
functions modifying globals, plotting/input/request calls in local scopes, loops over possibly empty arrays."""
import sys, re
from pynescript import ast as A

BUILTIN = set("""open high low close volume time time_close bar_index last_bar_index na true false hl2 hlc3 ohlc4 hlcc4
syminfo timeframe barstate color size shape location position text line box label table extend xloc yloc order format plot
barmerge ta math array str input request alert alertcondition indicator plotshape plotchar bgcolor barcolor fill hline
int float bool string nz na timestamp dayofweek hour minute year month dayofmonth display session currency scale
linefill matrix map strategy runtime log chart polyline adjustment dividends earnings splits""".split())
RESTRICT = {"plot", "plotshape", "plotchar", "bgcolor", "barcolor", "alertcondition", "indicator", "fill", "hline"}
errs, warns = [], []

def ln(n): return getattr(n, "lineno", "?")

def names_of(t):
    if isinstance(t, A.Name): return [t.id]
    if isinstance(t, A.Tuple): return [x.id for x in t.elts if isinstance(x, A.Name)]
    return []

def call_name(c):
    f = c.func
    if isinstance(f, A.Name): return f.id
    if isinstance(f, A.Attribute) and isinstance(f.value, A.Name): return f.value.id + "." + f.attr
    return ""

class Checker:
    def __init__(self): self.scopes = [set()]; self.funcs = set(); self.fdepth = 0; self.fscope_start = None; self.local = 0
    def declared(self, n): return any(n in s for s in self.scopes) or n in self.funcs or n in BUILTIN
    def declare(self, n, node):
        if self.local == 0 and self.fdepth == 0 and n in self.scopes[0]:
            errs.append(f"line {ln(node)}: '{n}' is already defined")
        self.scopes[-1].add(n)
    def block(self, body, extra=()):
        self.scopes.append(set(extra)); self.local += 1
        for st in body: self.visit(st)
        self.local -= 1; self.scopes.pop()
    def visit(self, n):
        t = type(n).__name__
        if t == "Script":
            for st in n.body: self.visit(st)
        elif t == "FunctionDef":
            self.funcs.add(n.name); self.fdepth += 1; save = self.fscope_start; self.fscope_start = len(self.scopes)
            self.block(n.body, [p.name for p in n.args]); self.fdepth -= 1; self.fscope_start = save
        elif t == "Assign":
            self.visit(n.value)
            for nm in names_of(n.target): self.declare(nm, n)
        elif t in ("ReAssign", "AugAssign"):
            self.visit(n.value)
            for nm in names_of(n.target):
                if not self.declared(nm): errs.append(f"line {ln(n)}: ':=' on undeclared '{nm}'")
                elif self.fdepth and not any(nm in s for s in self.scopes[self.fscope_start:]):
                    errs.append(f"line {ln(n)}: function modifies global variable '{nm}' (not allowed)")
        elif t == "If":
            self.visit(n.test); self.block(n.body)
            if n.orelse: self.block(n.orelse)
        elif t == "While":
            self.visit(n.test); self.block(n.body)
        elif t == "ForTo":
            self.visit(n.start); self.visit(n.end)
            if getattr(n, "step", None) is not None: self.visit(n.step)
            self.block(n.body, names_of(n.target))
        elif t == "ForIn":
            self.visit(n.iter); self.block(n.body, names_of(n.target))
        elif t == "Name":
            if isinstance(n.ctx, A.Load) and not self.declared(n.id):
                errs.append(f"line {ln(n)}: undeclared identifier '{n.id}'")
        elif t == "Call":
            cn = call_name(n)
            if (self.local or self.fdepth) and (cn in RESTRICT or cn.startswith("input") or cn.startswith("request.")):
                errs.append(f"line {ln(n)}: '{cn}' cannot be called in a local scope")
            self.visit(n.func)
            for a in n.args: self.visit(a.value)
        elif t == "Attribute":
            if isinstance(n.value, A.Name):
                if not self.declared(n.value.id): errs.append(f"line {ln(n)}: undeclared identifier '{n.value.id}'")
            else: self.visit(n.value)
        else:
            for f, v in A.iter_fields(n):
                if f in ("type", "annotations"): continue
                if isinstance(v, list):
                    for x in v:
                        if isinstance(x, A.AST): self.visit(x)
                elif isinstance(v, A.AST): self.visit(v)

src = open(sys.argv[1], encoding="utf-8").read()
tree = A.parse(src)
Checker().visit(tree)
# loops "for j = 0 to array.size(X) - 1" must be guarded by a size check on a previous line of the same block
lines = src.split("\n")
for i, l in enumerate(lines):
    m = re.search(r"for \w+ = 0 to array\.size\((\w+)\) - 1", l)
    if m:
        arr = m.group(1); ind = len(l) - len(l.lstrip()); guarded = False
        for k in range(i - 1, max(-1, i - 12), -1):
            pl = lines[k]
            if not pl.strip(): continue
            pind = len(pl) - len(pl.lstrip())
            if pind < ind and (f"array.size({arr}) > 0" in pl or f"array.size({arr}) >" in pl or "nZones > 0" in pl): guarded = True; break
            if pind < ind and pl.lstrip().startswith(("if ", "else")): break
        if not guarded: warns.append(f"line {i+1}: loop over array.size({arr}) - 1 without an explicit size>0 guard")
print("SYNTAX: OK (parsed)")
print("ERRORS:", len(errs)); [print("  ", e) for e in errs]
print("WARNINGS:", len(warns)); [print("  ", w) for w in warns]
