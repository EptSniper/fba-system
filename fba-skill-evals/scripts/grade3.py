#!/usr/bin/env python3
import json, re, os
BASE="/sessions/loving-dazzling-davinci/mnt/outputs"
def has(t,*p): return any(re.search(x,t,re.I) for x in p)
def snip(t,p):
    m=re.search(p,t,re.I)
    if not m: return "(not found)"
    s=max(0,m.start()-25); e=min(len(t),m.end()+25)
    return "…"+t[s:e].replace("\n"," ").strip()+"…"

def grade(skill,eid,t):
    r=[]
    def add(n,ok,ev): r.append({"text":n,"passed":bool(ok),"evidence":ev})
    if skill=="selleramp":
        if eid==0:
            add("Gives SAS settings checklist (inbound + thresholds)", has(t,r"inbound") and has(t,r"\bROI\b|profit"), snip(t,r"inbound"))
            add("Catches the sales-tax double-count trap (bake into cost, not %)", has(t,r"tax.{0,40}(cost|price)",r"bake",r"double[- ]count",r"not.{0,15}%.{0,15}field"), snip(t,r"tax|bake|double"))
            add("Cites 30% ROI / $3 profit gates", has(t,r"30\s*%") and has(t,r"\$?3(\.0+)?\s*(/|per|profit)|\$3\b"), snip(t,r"30\s*%"))
            add("Notes true landed cost must include shipping", has(t,r"shipping",r"landed"), snip(t,r"shipping|landed"))
        elif eid==1:
            add("Flags ROI 28% as below the 30% gate", has(t,r"28%?.{0,30}(below|under|short|miss|fail|<)",r"below.{0,10}30",r"under.{0,10}30",r"fails?.{0,15}30",r"28.{0,10}vs.{0,10}30"), snip(t,r"28|30\s*%"))
            add("Notes cost $15 exceeds Max Cost $14", has(t,r"15.{0,30}(above|over|exceed|more than).{0,10}14",r"max cost.{0,20}14",r"land.{0,10}below.{0,10}14",r"\$1\s?4\b.{0,40}\$?15"), snip(t,r"max cost|14"))
            add("Verdict borderline / reject (not a clean buy)", has(t,r"borderline",r"\bpass\b",r"reject",r"too thin",r"not.{0,8}(good|buy)",r"marginal",r"skip"), snip(t,r"borderline|pass|thin|marginal|reject"))
            add("Hands off (keepa/deal-analyst) — SAS isn't a buy order", has(t,r"deal-analyst",r"keepa",r"verify",r"confirm",r"not a buy"), snip(t,r"deal-analyst|keepa|verify"))
        else:
            add("Explains Max Cost as the reverse calculator / most you can pay", has(t,r"max cost",r"reverse",r"most you can pay",r"highest.{0,10}cost"), snip(t,r"max cost|reverse|most you"))
            add("Needs FBA fee / size-weight to compute", has(t,r"fba fee",r"size",r"weight",r"fulfillment fee"), snip(t,r"fba fee|size|weight"))
            add("Ties it to the 30% ROI target", has(t,r"30\s*%",r"\bROI\b"), snip(t,r"30\s*%|ROI"))
            add("Mentions stacking / landing below the number", has(t,r"stack",r"land.{0,10}below",r"under.{0,10}(that|max)"), snip(t,r"stack|below|under"))
    else: # sourcing
        if eid==0:
            add("Recommends reverse sourcing / storefront stalking for a beginner", has(t,r"storefront stalk",r"reverse sourc"), snip(t,r"storefront|reverse"))
            add("Deal-first (source where the sale/cashback is)", has(t,r"deal-first",r"on sale",r"cashback",r"\bsale\b",r"stack"), snip(t,r"deal-first|cashback|sale|stack"))
            add("Produces a concrete plan / steps (not vague)", has(t,r"plan",r"step",r"lead",r"\|"), snip(t,r"plan|step|lead"))
            add("Hands to deal-analyst / verify, no auto-buy", has(t,r"deal-analyst",r"verify",r"confirm",r"selleramp"), snip(t,r"deal-analyst|verify|selleramp"))
        elif eid==1:
            add("Recommends Keepa Product Finder for a known brand", has(t,r"product finder",r"keepa.{0,15}finder"), snip(t,r"product finder"))
            add("Gives the filter set (rank, Amazon OOS, offer count)", has(t,r"sales rank|0.{0,3}200",r"out of stock|oos|amazon.{0,10}out",r"offer count|new offer"), snip(t,r"out of stock|offer count|sales rank"))
            add("Mentions storefront stalking OR instant-reject flags too", has(t,r"storefront",r"reject",r"red flag",r"rising offer",r"buy box"), snip(t,r"storefront|reject|red flag"))
            add("Hands to deal-analyst / verify", has(t,r"deal-analyst",r"verify",r"confirm",r"selleramp"), snip(t,r"deal-analyst|verify|selleramp"))
        else:
            add("Endorses the deal-first angle around the live BOGO", has(t,r"bogo",r"deal-first",r"\byes\b",r"worth"), snip(t,r"bogo|deal-first|worth"))
            add("Stacking (BOGO + Circle + cashback) to manufacture margin", has(t,r"stack",r"cashback",r"manufactur",r"circle"), snip(t,r"stack|cashback|manufactur"))
            add("Each ASIN must still pass the gates / deal-analyst", has(t,r"deal-analyst",r"gate",r"verify",r"selleramp",r"check each"), snip(t,r"deal-analyst|gate|verify"))
            add("No blanket buy (lead = hypothesis / verify each)", has(t,r"hypothesis",r"not a buy",r"verify each",r"check each",r"each (product|asin|item)",r"don.t buy"), snip(t,r"hypothesis|verify each|each "))
    return r

TIM={
 "selleramp":{0:[(47284,92.520),(42287,88.359)],1:[(40181,63.702),(37387,84.405)],2:[(42188,90.348),(62203,86.703)]},
 "sourcing":{0:[(43482,113.009),(33882,75.640)],1:[(39445,86.167),(56381,107.807)],2:[(41903,117.258),(55850,101.061)]},
}
PROMPTS={
 "selleramp":{0:"what SAS settings before I start? weird ROI numbers",1:"SAS: profit $4.20, ROI 28%, breakeven $19.50, max cost $14, sell $26, cost $15 — good?",2:"buy box $32, most I can pay to still hit my ROI?"},
 "sourcing":{0:"brand new, $500, no idea what to sell — where to begin sourcing today?",1:"want to source Crayola — find winners in that brand efficiently?",2:"Target toy BOGO this week + Target Circle — worth a sourcing run?"},
}
WS={"selleramp":"fba-selleramp-analyst-workspace","sourcing":"fba-sourcing-scout-workspace"}
for skill,ws in WS.items():
    it=os.path.join(BASE,ws,"iteration-1")
    for eid in (0,1,2):
        ed=os.path.join(it,f"eval-{eid}")
        json.dump({"eval_id":eid,"prompt":PROMPTS[skill][eid]},open(os.path.join(ed,"eval_metadata.json"),"w"),indent=2)
        for ci,config in enumerate(("with_skill","without_skill")):
            rd=os.path.join(ed,config,"run-1")
            t=open(os.path.join(rd,"outputs","analysis.md"),encoding="utf-8").read()
            json.dump({"eval_id":eid,"prompt":PROMPTS[skill][eid]},open(os.path.join(rd,"eval_metadata.json"),"w"),indent=2)
            exps=grade(skill,eid,t); p=sum(1 for e in exps if e["passed"]); tot=len(exps)
            json.dump({"summary":{"pass_rate":round(p/tot,4),"passed":p,"failed":tot-p,"total":tot},"expectations":exps},open(os.path.join(rd,"grading.json"),"w"),indent=2)
            tok,sec=TIM[skill][eid][ci]
            json.dump({"total_tokens":tok,"total_duration_seconds":sec},open(os.path.join(rd,"timing.json"),"w"),indent=2)
    print(f"=== {skill} ===")
    for eid in (0,1,2):
        for config in ("with_skill","without_skill"):
            g=json.load(open(os.path.join(it,f"eval-{eid}",config,"run-1","grading.json")))
            s=g["summary"]; print(f"  eval-{eid} {config:14s}: {s['passed']}/{s['total']}")
